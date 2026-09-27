# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/article.py — F6.3 article processor.
#
# Two entry points:
#   tag_and_summarize(source_id) — full LLM enrichment (article, web-clipping)
#   tag_only(source_id)          — privacy-first, no LLM (personal-article)

from __future__ import annotations
import re

from exocortex.processors._common import (
    already_processed, call_tool, emit_thought_for_source,
    estimate_cost_usd, fetch_source, mark_processed, taxonomy_vocab_block,
)

PROCESSOR_NAME = 'article.v1'

SYSTEM_PROMPT = """\
You enrich articles with structured tags and a short summary for a personal
knowledge OS. Tags must come from this controlled vocabulary (you may also
emit `new` tags as suggestions, marked is_new=true):
""" + taxonomy_vocab_block() + """\

Rules:
- summary in Polish (the user's working language), 2-4 sentences, factual.
- pick 3-7 tags total across the 5 axes that genuinely fit the article.
- only set client when the article is concretely about that client's work,
  not just mentioning the brand.
- entities_person — full names if present (e.g. "Andrzej Kowalski"), not
  email addresses or @handles.
- if uncertain, prefer fewer tags over guessing.
"""

TOOL_SCHEMA = {
    'name': 'enrich_article',
    'description': 'Return summary + 5-axis tags + extracted entities for the article.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'summary_pl': {'type': 'string', 'description': '2-4 sentence Polish summary.'},
            'tags': {
                'type': 'object',
                'properties': {
                    'client': {'type': 'array', 'items': {'type': 'string'}},
                    'project': {'type': 'array', 'items': {'type': 'string'}},
                    'activity': {'type': 'array', 'items': {'type': 'string'}},
                    'topic': {'type': 'array', 'items': {'type': 'string'}},
                    'status': {'type': 'array', 'items': {'type': 'string'}},
                },
                'additionalProperties': False,
            },
            'entities_person': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Full names of people mentioned.',
            },
            'entities_organization': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Companies, institutions mentioned.',
            },
            'is_new_tags': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Tags emitted that are NOT in the vocabulary above (suggestions).',
            },
        },
        'required': ['summary_pl', 'tags'],
        'additionalProperties': False,
    },
}


# ─────────────────────────── Source body extraction ───────────────────────────

def _source_body(source: dict) -> str:
    """Read the article body from raw_sources.metadata.

    Capture API stores HTML→markdown extraction in metadata.raw_payload (cap 64
    KiB) and a 150-word excerpt in metadata.excerpt. We prefer the full
    extraction; fall back to excerpt; last resort = title.
    """
    meta = source.get('metadata') or {}
    body = meta.get('raw_payload') or meta.get('excerpt') or source.get('title') or ''
    # Strip stray HTML if anything slipped through.
    body = re.sub(r'<[^>]+>', '', body)
    return body.strip()


# ─────────────────────────── Public API ───────────────────────────

def tag_and_summarize(source_id: str, *, force: bool = False) -> dict:
    """Full LLM enrichment for article-like sources."""
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    body = _source_body(source)
    if not body or len(body) < 50:
        # Body too short — emit a stub thought (title only) and short-circuit LLM.
        title = source.get('title') or '(untitled)'
        emit_thought_for_source(
            source_id=source_id,
            body=f'Article: {title}\nURL: {source["uri"]}',
            thought_type='article_stub',
            domain=(source.get('metadata') or {}).get('domain') or 'work',
            metadata={'title': title, 'uri': source['uri']},
        )
        out = {'status': 'ok', 'mode': 'stub_no_body', 'source_id': source_id}
        mark_processed(source_id, PROCESSOR_NAME, out)
        return out

    user_prompt = (
        f'TITLE: {source.get("title") or "(untitled)"}\n'
        f'URL: {source["uri"]}\n'
        f'AUTHOR: {source.get("author_name") or "(unknown)"}\n'
        f'PUBLISHED: {source.get("published_at") or "(unknown)"}\n\n'
        f'BODY:\n{body[:8000]}'  # ~2k tokens cap
    )

    tool_input, usage = call_tool(
        SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=1024,
        _use_case='second_brain.F6_article_processor',
    )

    summary = tool_input.get('summary_pl') or ''
    tags = tool_input.get('tags') or {}
    entities_person = tool_input.get('entities_person') or []
    entities_org = tool_input.get('entities_organization') or []
    is_new = tool_input.get('is_new_tags') or []

    extracted_tags = {
        'extracted_at': _iso_now(),
        'extracted_by': PROCESSOR_NAME,
        'client': [{'value': v, 'confidence': 0.9, 'new': v in is_new}
                   for v in (tags.get('client') or [])],
        'project': [{'value': v, 'confidence': 0.85, 'new': v in is_new}
                    for v in (tags.get('project') or [])],
        'activity': [{'value': v, 'confidence': 0.85, 'new': v in is_new}
                     for v in (tags.get('activity') or [])],
        'topic': [{'value': v, 'confidence': 0.85, 'new': v in is_new}
                  for v in (tags.get('topic') or [])],
        'status': [{'value': v, 'confidence': 0.85, 'new': v in is_new}
                   for v in (tags.get('status') or [])],
        '_entities_person': entities_person,
        '_entities_organization': entities_org,
    }

    domain = ((source.get('metadata') or {}).get('domain')
              or _infer_domain_from_tags(tags) or 'work')

    body_for_thought = (
        f'# {source.get("title") or "(untitled)"}\n'
        f'URL: {source["uri"]}\n\n'
        f'## Streszczenie\n{summary}\n\n'
        f'## Treść (excerpt)\n{body[:2000]}'
    )

    thought_id = emit_thought_for_source(
        source_id=source_id,
        body=body_for_thought,
        thought_type='article',
        domain=domain,
        metadata={
            'title': source.get('title'),
            'uri': source['uri'],
            'summary_pl': summary,
        },
        extracted_tags=extracted_tags,
    )

    cost = estimate_cost_usd(usage)
    out = {
        'status': 'ok',
        'mode': 'llm',
        'source_id': source_id,
        'thought_id': thought_id,
        'tags_count': sum(len(tags.get(a) or []) for a in
                          ('client', 'project', 'activity', 'topic', 'status')),
        'is_new_tags': is_new,
        'cost_usd': round(cost, 6),
        'usage': usage,
    }
    mark_processed(source_id, PROCESSOR_NAME, {k: v for k, v in out.items() if k != 'usage'})
    return out


def tag_only(source_id: str, *, force: bool = False) -> dict:
    """Privacy-first variant: no LLM, deterministic tag extraction from frontmatter
    + entity heuristics. For source_type=personal-article."""
    if not force and already_processed(source_id, PROCESSOR_NAME + '-tagonly'):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    fm = (meta.get('frontmatter') or {})
    fm_tags = fm.get('tags') or []
    body = (meta.get('raw_payload') or meta.get('excerpt') or source.get('title') or '').strip()

    extracted_tags = {
        'extracted_at': _iso_now(),
        'extracted_by': PROCESSOR_NAME + '-tagonly',
        'topic': [{'value': str(t), 'confidence': 0.7, 'new': True} for t in fm_tags],
    }

    body_for_thought = (
        f'# {source.get("title") or "(untitled)"}\n'
        f'URL: {source["uri"]}\n\n'
        f'## Treść (excerpt)\n{body[:2000]}'
    )
    thought_id = emit_thought_for_source(
        source_id=source_id,
        body=body_for_thought,
        thought_type='article',
        domain='priv',
        metadata={'title': source.get('title'), 'uri': source['uri']},
        extracted_tags=extracted_tags,
    )

    out = {
        'status': 'ok',
        'mode': 'tagonly_no_llm',
        'source_id': source_id,
        'thought_id': thought_id,
        'tags_count': len(fm_tags),
        'cost_usd': 0.0,
    }
    mark_processed(source_id, PROCESSOR_NAME + '-tagonly', out)
    return out


# ─────────────────────────── Helpers ───────────────────────────

def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _infer_domain_from_tags(tags: dict) -> str | None:
    """Cheap heuristic: if a client tag fires, it's work; if cooking activity, cook; etc."""
    if tags.get('client'):
        return 'work'
    activity = set(tags.get('activity') or [])
    topic = set(tags.get('topic') or [])
    if activity & {'cooking', 'baking', 'recipe-development'} or topic & {'cuisine', 'recipe'}:
        return 'cook'
    if activity & {'3d-printing', 'modeling'} or topic & {'fdm', 'sla', 'filament'}:
        return '3d'
    return None


# Public alias used by scorer routing.
process = tag_and_summarize
