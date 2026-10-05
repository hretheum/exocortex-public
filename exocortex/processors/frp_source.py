# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/frp_source.py — F6.3 FRP source scoring (3-axis).
#
# Inputs: rss-frp or frp-source raw_sources rows (SF stories from Clarkesworld,
# 365tomorrows, Solarpunk Magazine, etc.).
#
# Outputs:
#   - 3-axis score (accessibility, horizon, consequence) in raw_sources.metadata
#   - suggested reflection prompt key from docs/reflection-prompts.md
#   - INSERT content_queue row (status='unscored' → 'scored')
#   - acquired_from edge (thought ← raw_source) — yes, we still emit a thought
#     stub for searchability via pgvector.

from __future__ import annotations

from datetime import UTC
from typing import Any

from exocortex.processors._common import (
    TENANT_ID,
    already_processed,
    call_tool,
    conn,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'frp_source.v1'

SYSTEM_PROMPT = """\
You score a science-fiction story for use in the Futures Reading Protocol
(FRP), a personal practice that uses fiction as a stimulus for cross-frame
self-reflection.

Three axes (each 0-3 integer):

  ACCESSIBILITY — how readable is this for a working professional with
  ~30 minutes of focus?
  0 = dense / inaccessible, 1 = requires effort, 2 = approachable,
  3 = breezy short story.

  HORIZON — how distant is the story setting from now?
  0 = present / contemporary, 1 = near-future (~5 yrs),
  2 = mid-future (~20 yrs), 3 = far-future / post-singularity.

  CONSEQUENCE — what's at stake for the protagonist?
  0 = trivial / day in the life, 1 = personal stakes, 2 = group / community,
  3 = civilizational / existential.

Total = sum of three (range 0-9).

Plus a `suggested_prompt_key` from the FRP library. Use one of:
  P1.1, P1.2, P1.3 — frame integration (professional/social/personal)
  P2.1, P2.2, P2.3 — cross-frame (what does frame B say about frame A?)
  P3.1, P3.2 — gradient detection (what's the spread between current and depicted state?)

Rules: ground each score in concrete evidence. Don't invent details not in
the text. Be honest if the text is too short to score reliably.
"""

TOOL_SCHEMA = {
    'name': 'score_frp_source',
    'description': 'Score an FRP source on 3 axes + suggest a reflection prompt.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'accessibility': {'type': 'integer', 'minimum': 0, 'maximum': 3},
            'horizon': {'type': 'integer', 'minimum': 0, 'maximum': 3},
            'consequence': {'type': 'integer', 'minimum': 0, 'maximum': 3},
            'reasoning': {
                'type': 'string',
                'description': '2-3 sentence justification (Polish), citing concrete textual evidence.',
            },
            'suggested_prompt_key': {
                'type': 'string',
                'enum': ['P1.1', 'P1.2', 'P1.3', 'P2.1', 'P2.2', 'P2.3', 'P3.1', 'P3.2'],
            },
            'frame': {
                'type': 'string',
                'enum': ['A', 'B', 'C'],
                'description': 'A=professional, B=social, C=personal — which frame does this best illuminate?',
            },
            'themes': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['accessibility', 'horizon', 'consequence', 'reasoning', 'suggested_prompt_key', 'frame'],
        'additionalProperties': False,
    },
}


def score(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    body = (meta.get('raw_payload') or meta.get('excerpt') or source.get('title') or '').strip()
    if not body or len(body) < 30:
        # RSS feeds often expose only the lead — score anyway, mark low confidence.
        out: dict[str, Any] = {'status': 'error', 'reason': 'no_body', 'source_id': source_id}
        return out

    body_kind = meta.get('body_kind') or ('full' if len(body) >= 1500 else 'excerpt')
    body_cap = 12000 if body_kind == 'full' else 8000
    kind_hint = (
        'Full text — score with confidence on all axes.'
        if body_kind == 'full' else
        'Excerpt only (first ~150 words) — score conservatively, especially HORIZON and CONSEQUENCE.'
    )

    user_prompt = (
        f'TITLE: {source.get("title") or ""}\n'
        f'AUTHOR: {source.get("author_name") or "(unknown)"}\n'
        f'SOURCE: {source.get("source_name") or ""}\n'
        f'URL: {source["uri"]}\n'
        f'BODY_KIND: {body_kind} ({len(body)} chars). {kind_hint}\n\n'
        f'TEXT:\n{body[:body_cap]}'
    )

    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=512,
                                  _use_case='second_brain.F6_frp_source_processor')
    cost = estimate_cost_usd(usage)

    score_summary = (
        f'**FRP score**: accessibility={tool_input["accessibility"]}/3, '
        f'horizon={tool_input["horizon"]}/3, '
        f'consequence={tool_input["consequence"]}/3. '
        f'**Frame**: {tool_input["frame"]}. '
        f'**Suggested prompt**: {tool_input["suggested_prompt_key"]}.\n\n'
        f'{tool_input["reasoning"]}'
    )

    body_for_thought = (
        f'# {source.get("title") or "(untitled)"}\n'
        f'Source: {source.get("source_name") or "?"} — {source["uri"]}\n\n'
        f'## Score\n{score_summary}\n\n'
        f'## Tekst (excerpt)\n{body[:1500]}'
    )

    extracted_tags = {
        'extracted_at': _iso_now(),
        'extracted_by': PROCESSOR_NAME,
        'topic': [{'value': str(t), 'confidence': 0.8, 'new': True}
                  for t in (tool_input.get('themes') or [])],
        '_frp_score': {
            'accessibility': tool_input['accessibility'],
            'horizon': tool_input['horizon'],
            'consequence': tool_input['consequence'],
            'frame': tool_input['frame'],
            'suggested_prompt_key': tool_input['suggested_prompt_key'],
            'body_kind': body_kind,
            'body_chars': len(body),
        },
    }

    thought_id = emit_thought_for_source(
        source_id=source_id,
        body=body_for_thought,
        thought_type='frp_source_scored',
        domain='frp',
        metadata={
            'title': source.get('title'),
            'uri': source['uri'],
            'frp_score': extracted_tags['_frp_score'],
        },
        extracted_tags=extracted_tags,
    )

    # content_queue row — keeps backward compat with FRP F7 query helpers.
    # status='queued' is the initial state per content_queue_status_check
    # (allowed: queued/reading/used/skipped). The 3-axis score persists to
    # dedicated columns (score_accessibility/horizon/consequence) used by
    # reading-queue renderer; score_total is GENERATED ALWAYS (sum of three).
    # ai_tags retains full payload for downstream tooling (frame,
    # suggested_prompt_key, body_kind).
    with conn() as c:
        c.execute(
            'INSERT INTO content_queue ('
            '  tenant_id, source_id, status, ai_tags, '
            '  score_accessibility, score_horizon, score_consequence'
            ') VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s) '
            'ON CONFLICT DO NOTHING',
            (TENANT_ID, source_id, 'queued',
             _json(extracted_tags['_frp_score']),
             tool_input['accessibility'], tool_input['horizon'],
             tool_input['consequence']),
        )

    out = {
        'status': 'ok',
        'source_id': source_id,
        'thought_id': thought_id,
        'frp_score': extracted_tags['_frp_score'],
        'cost_usd': round(cost, 6),
    }
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat()


def _json(d: Any) -> str:
    import json
    return json.dumps(d)


process = score
