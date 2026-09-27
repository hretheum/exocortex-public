# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/twitter.py — F6.3 Twitter/X thread claim extraction.

from __future__ import annotations
from exocortex.processors._common import (
    already_processed, call_tool, emit_thought_for_source, estimate_cost_usd,
    fetch_source, mark_processed,
)

PROCESSOR_NAME = 'twitter.v1'

SYSTEM_PROMPT = """\
You analyze a Twitter/X thread. For each thread, extract the central claims
(what is the thread arguing?) and notable counter-arguments from replies if
visible. Identify entities (people, companies, products) mentioned.
"""

TOOL_SCHEMA = {
    'name': 'extract_thread',
    'input_schema': {
        'type': 'object',
        'properties': {
            'central_claims': {'type': 'array', 'items': {'type': 'string'}},
            'counter_arguments': {'type': 'array', 'items': {'type': 'string'}},
            'entities_person': {'type': 'array', 'items': {'type': 'string'}},
            'entities_organization': {'type': 'array', 'items': {'type': 'string'}},
            'topic_tags': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['central_claims'],
        'additionalProperties': False,
    },
}


def extract_claims(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}
    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    body = (meta.get('raw_payload') or meta.get('excerpt') or '').strip()
    if not body or len(body) < 30:
        return {'status': 'error', 'reason': 'no_body', 'source_id': source_id}

    user_prompt = (
        f'AUTHOR: {source.get("author_name") or ""}\n'
        f'URL: {source["uri"]}\n\n'
        f'THREAD:\n{body[:6000]}'
    )
    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=1024,
                                  _use_case='second_brain.F6_twitter_processor')
    cost = estimate_cost_usd(usage)

    parts = [f'# {source.get("title") or "Twitter thread"}',
             f'URL: {source["uri"]}', '', '## Centralne tezy']
    parts.extend(f'- {c}' for c in tool_input['central_claims'])
    if tool_input.get('counter_arguments'):
        parts.append('\n## Kontrargumenty')
        parts.extend(f'- {c}' for c in tool_input['counter_arguments'])

    thought_id = emit_thought_for_source(
        source_id=source_id, body='\n'.join(parts),
        thought_type='twitter_thread', domain='work',
        metadata={'title': source.get('title'), 'uri': source['uri']},
        extracted_tags={
            'extracted_at': _iso_now(),
            'extracted_by': PROCESSOR_NAME,
            'topic': [{'value': str(t), 'confidence': 0.8, 'new': True}
                      for t in (tool_input.get('topic_tags') or [])],
            '_entities_person': tool_input.get('entities_person') or [],
        },
    )
    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'claims': len(tool_input['central_claims']),
           'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


process = extract_claims
