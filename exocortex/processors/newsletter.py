# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/newsletter.py — F8.8 newsletter synthesis processor.
#
# Routed from scorer.py for source_type=newsletter (Gmail "Read Later" label).
# Distinct from article.py because newsletters have different structure:
#   - sender = newsletter brand (substack/beehiiv/AI report etc.)
#   - body is a curated digest, often with multiple linked items
#   - we want tldr + key insights + topics + cited_sources for downstream
#     wiki/news/ MOC compilation (F8.8.5)
#
# Output schema (persisted in extracted_tags + thought metadata):
#   tldr            — 1 paragraph PL summary
#   key_insights    — 3-5 {insight, evidence} bullet pairs
#   topics          — short tags from F3 vocab (or :new)
#   cited_sources   — [{name, url, type=company|paper|product|person}]

from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from exocortex.processors._common import (
    TENANT_ID, already_processed, call_tool, conn, emit_thought_for_source,
    estimate_cost_usd, fetch_source, mark_processed,
)
from exocortex.db import _insert_edge, _upsert_entity

PROCESSOR_NAME = 'newsletter.v1'

# F8.8.x.H2.3 — newsletter taxonomy guardrails. Below-threshold is_new
# topics get logged here for periodic review; canonical vocab is loaded
# once at module-import (cheap, ~9 KB yaml). Re-import to refresh.
_REJECTED_NEW_TOPICS_LOG = Path(__file__).resolve().parent.parent.parent / \
    'data' / 'discovery' / 'rejected_new_topics.tsv'
IS_NEW_MIN_CONFIDENCE = 0.85
_canonical_vocab_cache: Optional[str] = None


def _load_canonical_topic_vocab() -> str:
    """Render `config/news_topic_clusters.yaml` as a compact vocab block
    for system-prompt embedding. Cached at module level (called once per
    process). Returns empty string when the yaml is missing — graceful
    degrade, no constraint applied.
    """
    global _canonical_vocab_cache
    if _canonical_vocab_cache is not None:
        return _canonical_vocab_cache

    cfg_path = Path(__file__).resolve().parent.parent.parent / 'config' / \
        'news_topic_clusters.yaml'
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
    except FileNotFoundError:
        _canonical_vocab_cache = ''
        return _canonical_vocab_cache
    except Exception:
        _canonical_vocab_cache = ''
        return _canonical_vocab_cache

    lines: list[str] = []
    for cl in cfg.get('clusters') or []:
        label = cl.get('label') or cl.get('slug') or '?'
        topics = [str(t) for t in (cl.get('topics') or [])]
        if not topics:
            continue
        lines.append(f"- **{label}**: {', '.join(topics)}")
    _canonical_vocab_cache = '\n'.join(lines)
    return _canonical_vocab_cache

SYSTEM_PROMPT = """\
You synthesize a personal-use digest from a single newsletter email. The user
is a senior product / design leader who consumes branżowe AI/tech newsletters
to track new tools, papers, products, and trends.

FIRST, judge `industry_relevant`: does this newsletter genuinely cover the user's
professional domains — AI, tech, software, design, product — or adjacent industry
trends/analysis? Pure consumer marketing, D2C sales blasts, promotions, or
off-topic lifestyle content with no educational or industry signal is NOT relevant.
For those set `industry_relevant=false` + a one-sentence `relevance_reason`; the
digest fields below are then ignored (fill them minimally). Otherwise set
`industry_relevant=true` and produce the full synthesis.

Output a concise structured synthesis:

  tldr           — one short paragraph (3-5 sentences, Polish), the take-away
                   for someone who has 30 seconds to skim.
  key_insights   — 3-5 bullet pairs {insight, evidence}. `insight` is the
                   non-obvious claim; `evidence` is the concrete sentence/
                   fragment from the newsletter that justifies it.
  topics         — 3-7 short tags (lowercase-kebab) per `topics` schema below.
                   STRONGLY PREFER reusing the canonical vocabulary listed
                   below. Singletons cause noise — when in doubt, pick the
                   closest canonical tag instead of inventing a new one.

CANONICAL TOPIC VOCABULARY (news axis, F8.8.x.H2):

""" + _load_canonical_topic_vocab() + """\

  Rules for `topics`:
    • Each entry is `{value, confidence, is_new, is_new_justification?}`.
    • `is_new=true` is allowed ONLY when:
        (a) NO canonical tag above fits the concept, AND
        (b) your `confidence` ≥ 0.85, AND
        (c) you provide `is_new_justification` — one short sentence
            explaining why no canonical tag works.
    • Any `is_new=true` entry that fails (a)-(c) will be rejected
      downstream.

  cited_sources  — every concrete linked thing the newsletter mentions
                   (companies, products, papers, people, frameworks).
                   `type` ∈ company|product|paper|person|framework|article.
                   Skip generic mentions ("OpenAI" only when the issue is
                   about a specific OpenAI launch, not in passing).

Tone of tldr/insights: factual, non-promotional. The newsletter is marketing
copy; your job is to extract signal.
"""

TOOL_SCHEMA = {
    'name': 'synthesize_newsletter',
    'description': (
        'Return a structured digest of one newsletter email — tldr + key '
        'insights + topics + cited sources.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'industry_relevant': {
                'type': 'boolean',
                'description': (
                    'True if the newsletter covers AI / tech / software / design '
                    '/ product or adjacent industry trends; False for pure '
                    'consumer marketing, D2C sales, promotions or off-topic '
                    'content with no educational/industry signal.'
                ),
            },
            'relevance_reason': {
                'type': 'string',
                'description': 'One short sentence justifying industry_relevant.',
            },
            'tldr': {
                'type': 'string',
                'description': '3-5 sentence Polish summary.',
            },
            'key_insights': {
                'type': 'array',
                'minItems': 1,
                'maxItems': 7,
                'items': {
                    'type': 'object',
                    'properties': {
                        'insight': {'type': 'string'},
                        'evidence': {'type': 'string'},
                    },
                    'required': ['insight', 'evidence'],
                    'additionalProperties': False,
                },
            },
            'topics': {
                'type': 'array',
                'minItems': 1,
                'maxItems': 7,
                'items': {
                    'type': 'object',
                    'properties': {
                        'value': {
                            'type': 'string',
                            'description': 'lowercase-kebab tag.',
                        },
                        'confidence': {
                            'type': 'number',
                            'minimum': 0.0,
                            'maximum': 1.0,
                        },
                        'is_new': {
                            'type': 'boolean',
                            'description': 'true if NO canonical tag fits.',
                        },
                        'is_new_justification': {
                            'type': 'string',
                            'description': 'REQUIRED when is_new=true: one '
                                           'sentence why no canonical tag works.',
                        },
                    },
                    'required': ['value', 'confidence', 'is_new'],
                    'additionalProperties': False,
                },
            },
            'cited_sources': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string'},
                        'url': {
                            'type': 'string',
                            'description': 'Direct URL if present in the email; '
                                           'empty string if only the name is mentioned.',
                        },
                        'type': {
                            'type': 'string',
                            'enum': ['company', 'product', 'paper', 'person',
                                     'framework', 'article'],
                        },
                    },
                    'required': ['name', 'type'],
                    'additionalProperties': False,
                },
            },
            'newsletter_metadata': {
                'type': 'object',
                'properties': {
                    'newsletter_name': {
                        'type': 'string',
                        'description': 'Short brand name (e.g. "The AI Report"), '
                                       'inferred from the body or sender.',
                    },
                    'issue_subject': {'type': 'string'},
                },
                'additionalProperties': False,
            },
        },
        'required': [
            'industry_relevant', 'tldr', 'key_insights', 'topics', 'cited_sources',
        ],
        'additionalProperties': False,
    },
}


# ─────────────────────────── Body extraction ───────────────────────────

def _source_body(source: dict) -> str:
    """Read the newsletter body. capture_api stores extracted markdown
    (HTML → trafilatura) in metadata.extracted text via metadata.raw_payload.

    Newsletters are mostly HTML, so capture_api's _extract_text() returns
    decent markdown. metadata.raw_payload still has the raw HTML for fallback.
    """
    meta = source.get('metadata') or {}
    # capture_api auto-extracts markdown when raw_payload is HTML; the
    # extracted text overwrites raw_payload only if you read excerpt — but
    # raw_payload remains the original. We want the cleaned text. excerpt is
    # only 150 words. Trafilatura's full extract isn't persisted as a
    # separate field — it lives behind the excerpt computation. Fall back
    # to raw_payload + strip HTML (cheap regex) so the LLM gets the body.
    body = meta.get('raw_payload') or meta.get('excerpt') or source.get('title') or ''
    # Strip HTML tags + collapse whitespace.
    body = re.sub(r'<style[^>]*>.*?</style>', ' ', body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'<script[^>]*>.*?</script>', ' ', body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = re.sub(r'&nbsp;', ' ', body)
    body = re.sub(r'&amp;', '&', body)
    body = re.sub(r'&lt;', '<', body)
    body = re.sub(r'&gt;', '>', body)
    body = re.sub(r'&quot;', '"', body)
    body = re.sub(r'\s+', ' ', body)
    return body.strip()


# ─────────────────────────── Public API ───────────────────────────

def synthesize(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    body = _source_body(source)
    if not body or len(body) < 100:
        out = {'status': 'error', 'reason': 'no_body', 'source_id': source_id}
        return out

    meta = source.get('metadata') or {}
    user_prompt = (
        f'NEWSLETTER: {meta.get("sender_name") or meta.get("sender_email") or "(unknown)"}\n'
        f'SENDER_EMAIL: {meta.get("sender_email") or "(unknown)"}\n'
        f'SUBJECT: {source.get("title") or "(no subject)"}\n'
        f'DATE: {source.get("published_at") or meta.get("date_header") or "(unknown)"}\n'
        f'LIST_ID: {meta.get("list_id") or "(none)"}\n\n'
        f'BODY (HTML stripped, ~3000-tok cap):\n{body[:12000]}'
    )

    tool_input, usage = call_tool(
        SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=2048,
        _use_case='second_brain.F6_newsletter_processor',
    )

    # Skip pure marketing / off-topic newsletters so the digest stays branżowe.
    # mark_processed (not a page) so the scorer won't re-spend tokens on the same
    # issue. Only an explicit False skips; a missing field (older output) counts
    # as relevant.
    if tool_input.get('industry_relevant') is False:
        out = {
            'status': 'skipped',
            'reason': 'not_industry_relevant',
            'detail': tool_input.get('relevance_reason') or '',
            'source_id': source_id,
            'cost_usd': round(estimate_cost_usd(usage), 6),
        }
        mark_processed(source_id, PROCESSOR_NAME, out)
        return out

    tldr = tool_input.get('tldr') or ''
    key_insights = tool_input.get('key_insights') or []
    raw_topics = tool_input.get('topics') or []
    cited_sources = tool_input.get('cited_sources') or []
    nl_meta = tool_input.get('newsletter_metadata') or {}

    # F8.8.x.H2.3 — normalise + validate topic objects. Reject is_new=true
    # entries that fail confidence/justification gate; downstream `topics`
    # (plain list[str]) and `is_new_topics` keep their old contract.
    topics, is_new_topics, rejected = _validate_topics(raw_topics, source_id)

    extracted_tags = {
        'extracted_at': _iso_now(),
        'extracted_by': PROCESSOR_NAME,
        'topic': [
            {
                'value': str(t['value']),
                'confidence': float(t.get('confidence') or 0.85),
                'new': bool(t.get('is_new')),
            }
            for t in _accepted_topic_objects(raw_topics, rejected)
        ],
        '_newsletter': {
            'tldr': tldr,
            'key_insights': key_insights,
            'cited_sources': cited_sources,
            'newsletter_name': nl_meta.get('newsletter_name'),
            'issue_subject': nl_meta.get('issue_subject') or source.get('title'),
            'sender_email': meta.get('sender_email'),
        },
    }

    body_for_thought = _format_thought_body(
        title=source.get('title') or '(untitled)',
        uri=source['uri'],
        sender=meta.get('sender_name') or meta.get('sender_email'),
        date=source.get('published_at') or meta.get('date_header'),
        tldr=tldr,
        key_insights=key_insights,
        topics=topics,
        cited_sources=cited_sources,
    )

    thought_id = emit_thought_for_source(
        source_id=source_id,
        body=body_for_thought,
        thought_type='newsletter_synthesis',
        domain='news',
        metadata={
            'title': source.get('title'),
            'uri': source['uri'],
            'tldr': tldr,
            'newsletter_name': nl_meta.get('newsletter_name'),
            'sender_email': meta.get('sender_email'),
            'cited_sources_count': len(cited_sources),
            'topics_count': len(topics),
        },
        extracted_tags=extracted_tags,
    )

    # F8.8.6 — full edges: cites + tagged_with + from_source. The newsletter
    # brand entity (substack/beehiiv brand) is keyed on the newsletter name
    # so multiple issues from the same source link to one entity (citation
    # graph value). mentions_person is NOT used here — F4.6.1 reserves it
    # for meeting attendance; person-cited sources stay as `cites` edges.
    edges_emitted = _emit_newsletter_edges(
        thought_id=thought_id,
        topics=topics,
        cited_sources=cited_sources,
        newsletter_name=nl_meta.get('newsletter_name'),
        sender_email=meta.get('sender_email'),
    )

    cost = estimate_cost_usd(usage)
    out = {
        'status': 'ok',
        'source_id': source_id,
        'thought_id': thought_id,
        'topics_count': len(topics),
        'cited_sources_count': len(cited_sources),
        'edges_emitted': edges_emitted,
        'is_new_topics': is_new_topics,
        'rejected_new_topics_count': len(rejected),
        'cost_usd': round(cost, 6),
        'usage': usage,
    }
    mark_processed(
        source_id, PROCESSOR_NAME,
        {k: v for k, v in out.items() if k != 'usage'},
    )
    return out


# Scorer dispatch alias.
process = synthesize


# ─────────────────────────── Helpers ───────────────────────────

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_topic_obj(t: Any) -> Optional[dict]:
    """Defensive normalizer — claude-haiku occasionally returns plain
    strings even with strict tool schema. Coerce to canonical dict.
    """
    if isinstance(t, dict):
        value = (t.get('value') or '').strip()
        if not value:
            return None
        return {
            'value': value.lower(),
            'confidence': float(t.get('confidence') or 0.0),
            'is_new': bool(t.get('is_new')),
            'is_new_justification': (t.get('is_new_justification') or '').strip(),
        }
    if isinstance(t, str):
        v = t.strip().lower()
        if not v:
            return None
        return {
            'value': v,
            'confidence': 0.85,
            'is_new': False,
            'is_new_justification': '',
        }
    return None


def _validate_topics(
    raw_topics: list[Any], source_id: str,
) -> tuple[list[str], list[str], list[dict]]:
    """Walk LLM topic objects, drop is_new=true entries that fail the
    confidence/justification gate, log rejections to TSV.

    Returns (accepted_topic_strings, accepted_is_new_strings, rejected_dicts).
    `accepted_topic_strings` is the plain list[str] downstream code expects.
    """
    accepted: list[str] = []
    accepted_new: list[str] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for raw in raw_topics:
        obj = _coerce_topic_obj(raw)
        if obj is None or obj['value'] in seen:
            continue
        seen.add(obj['value'])
        if obj['is_new']:
            confidence_ok = obj['confidence'] >= IS_NEW_MIN_CONFIDENCE
            justification_ok = bool(obj['is_new_justification'])
            if not (confidence_ok and justification_ok):
                rejected.append({
                    'topic': obj['value'],
                    'confidence': obj['confidence'],
                    'reason': (
                        'low_confidence' if not confidence_ok
                        else 'missing_justification'
                    ),
                })
                continue
            accepted_new.append(obj['value'])
        accepted.append(obj['value'])
    if rejected:
        _log_rejected_new_topics(source_id, rejected)
    return accepted, accepted_new, rejected


def _accepted_topic_objects(
    raw_topics: list[Any], rejected: list[dict],
) -> list[dict]:
    """Return only the topic objects that survived validation, preserving
    order and confidence/is_new flags. Used to populate extracted_tags.topic.
    """
    rejected_set = {r['topic'] for r in rejected}
    out: list[dict] = []
    seen: set[str] = set()
    for raw in raw_topics:
        obj = _coerce_topic_obj(raw)
        if obj is None or obj['value'] in seen or obj['value'] in rejected_set:
            continue
        seen.add(obj['value'])
        out.append(obj)
    return out


def _log_rejected_new_topics(source_id: str, rejected: list[dict]) -> None:
    """Append rejection rows to data/discovery/rejected_new_topics.tsv.

    Periodic review: if a topic surfaces repeatedly in this log, it's a
    candidate for `scripts/cluster_news_topics.py --update` to absorb into
    canonical vocab.
    """
    try:
        _REJECTED_NEW_TOPICS_LOG.parent.mkdir(parents=True, exist_ok=True)
        new_file = not _REJECTED_NEW_TOPICS_LOG.exists()
        with _REJECTED_NEW_TOPICS_LOG.open('a', encoding='utf-8') as f:
            if new_file:
                f.write('timestamp\tsource_id\ttopic\tconfidence\treason\n')
            ts = _iso_now()
            for r in rejected:
                f.write(
                    f"{ts}\t{source_id}\t{r['topic']}\t"
                    f"{r['confidence']:.2f}\t{r['reason']}\n"
                )
    except Exception:
        # Logging failure must not break processing.
        pass


def _slugify(s: str) -> str:
    """Lowercase-kebab canonical_name for entity dedup. Keeps newsletter
    entities mergeable across issues (same product/company → one entity)."""
    s = (s or '').strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:80] or 'unknown'


def _emit_newsletter_edges(*, thought_id: str, topics: list,
                           cited_sources: list,
                           newsletter_name: Any = None,
                           sender_email: Any = None) -> dict[str, int]:
    """Emit `tagged_with` (thought→topic entity), `cites` (thought→cited
    source entity), and `from_source` (thought→newsletter brand entity).

    Idempotent — `_insert_edge` uses ON CONFLICT DO NOTHING + AGE MERGE.
    Re-runs on the same source produce zero new rows.

    Returns counts by edge type for telemetry.
    """
    counts = {'tagged_with': 0, 'cites': 0, 'from_source': 0}
    if not thought_id:
        return counts
    with conn() as c:
        # tagged_with: one edge per topic.
        for t in topics:
            slug = _slugify(t)
            if not slug:
                continue
            entity_id = _upsert_entity(c, slug, 'topic', TENANT_ID)
            res = _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': thought_id,
                'src_type': 'thought',
                'dst_id': entity_id,
                'dst_type': 'entity',
                'type': 'tagged_with',
                'confidence': 0.85,
                'created_by': PROCESSOR_NAME,
            })
            if res is not None:
                counts['tagged_with'] += 1

        # cites: one edge per cited_source. canonical_name = slug(name).
        # Entity type = the LLM-supplied {company|product|paper|person|
        # framework|article}. Same name used twice in different issues
        # collapses into one entity (intentional — that's the value of
        # tracking citations).
        for cs in cited_sources:
            # Defensive: LLM occasionally returns list[str] for cited_sources
            # despite the strict tool schema. Treat string as bare name w/
            # unknown type.
            if isinstance(cs, str):
                name = cs
                etype = 'unknown'
            elif isinstance(cs, dict):
                name = cs.get('name') or ''
                etype = cs.get('type') or 'unknown'
            else:
                continue
            slug = _slugify(name)
            if not slug:
                continue
            entity_id = _upsert_entity(c, slug, etype, TENANT_ID)
            res = _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': thought_id,
                'src_type': 'thought',
                'dst_id': entity_id,
                'dst_type': 'entity',
                'type': 'cites',
                'confidence': 0.8,
                'created_by': PROCESSOR_NAME,
            })
            if res is not None:
                counts['cites'] += 1

        # from_source: one edge to newsletter brand entity.
        # Brand canonical_name preference order:
        #   1. newsletter_name from LLM extraction (cleanest — "The AI Report")
        #   2. sender_email domain (fallback — "mail.beehiiv.com")
        # Same brand across issues = one entity → wiki/news/by-source/{slug}.md
        # rendered z all issues group by from_source edge traversal.
        brand_name = (newsletter_name or '').strip()
        if not brand_name and sender_email:
            # Use the email domain as fallback brand identifier.
            brand_name = sender_email.split('@', 1)[-1] if '@' in sender_email else sender_email
        if brand_name:
            slug = _slugify(brand_name)
            if slug:
                entity_id = _upsert_entity(c, slug, 'newsletter', TENANT_ID)
                res = _insert_edge(c, {
                    'tenant_id': TENANT_ID,
                    'src_id': thought_id,
                    'src_type': 'thought',
                    'dst_id': entity_id,
                    'dst_type': 'entity',
                    'type': 'from_source',
                    'confidence': 0.95,
                    'created_by': PROCESSOR_NAME,
                })
                if res is not None:
                    counts['from_source'] += 1
    return counts


def _format_thought_body(*, title: str, uri: str, sender: Any, date: Any,
                          tldr: str, key_insights: list, topics: list,
                          cited_sources: list) -> str:
    """Render a markdown body for the synthesis thought.

    Used both for embedding (F2.5 resolve_title) and as the raw seed for
    F8.8.5 wiki_compiler `compile_news_module` atomic newsletter pages.
    """
    lines = [
        f'# {title}',
        f'Source: {sender or "?"}',
        f'Date: {date or "?"}',
        f'URL: {uri}',
        '',
        '## TL;DR',
        tldr or '_(empty)_',
        '',
        '## Key insights',
    ]
    if key_insights:
        for it in key_insights:
            # Defensive: LLM occasionally returns list[str] instead of
            # list[{insight, evidence}] despite the strict tool schema.
            if isinstance(it, str):
                lines.append(f'- **{it}**')
                continue
            if not isinstance(it, dict):
                continue
            lines.append(f'- **{it.get("insight", "?")}**')
            ev = it.get('evidence')
            if ev:
                lines.append(f'  *evidence:* {ev}')
    else:
        lines.append('_(none)_')
    lines.append('')
    lines.append('## Topics')
    if topics:
        lines.append(', '.join(f'`{t}`' for t in topics))
    else:
        lines.append('_(none)_')
    lines.append('')
    lines.append('## Cited sources')
    if cited_sources:
        for s in cited_sources:
            if isinstance(s, str):
                lines.append(f'- {s}')
                continue
            if not isinstance(s, dict):
                continue
            name = s.get('name', '?')
            url = s.get('url') or ''
            stype = s.get('type') or '?'
            if url:
                lines.append(f'- [{name}]({url}) ({stype})')
            else:
                lines.append(f'- {name} ({stype})')
    else:
        lines.append('_(none)_')
    return '\n'.join(lines)
