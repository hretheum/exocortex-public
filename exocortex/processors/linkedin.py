# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/linkedin.py — F6.3 LinkedIn post enrichment.

from __future__ import annotations

from exocortex.processors._common import (
    already_processed,
    call_tool,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'linkedin.v1'

SYSTEM_PROMPT = """\
You enrich a LinkedIn post for a personal knowledge OS. Focus on career
signals: hiring, layoffs, funding, partnership, product-launch, conference,
opinion. Identify the author + their company.
"""

TOOL_SCHEMA = {
    'name': 'enrich_linkedin_post',
    'input_schema': {
        'type': 'object',
        'properties': {
            'summary_pl': {'type': 'string'},
            'signals': {'type': 'array', 'items': {'type': 'string'}},
            'author_name': {'type': 'string'},
            'company': {'type': 'string'},
            'topic_tags': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['summary_pl'],
        'additionalProperties': False,
    },
}


def enrich(source_id: str, *, force: bool = False) -> dict:
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
        f'POST:\n{body[:5000]}'
    )
    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=512,
                                  _use_case='second_brain.F6_linkedin_processor')
    cost = estimate_cost_usd(usage)

    parts = [f'# {source.get("title") or "LinkedIn post"}',
             f'URL: {source["uri"]}']
    if tool_input.get('author_name') or tool_input.get('company'):
        parts.append(f'**{tool_input.get("author_name") or "?"}** '
                     f'@ {tool_input.get("company") or "?"}')
    parts.append('\n## Streszczenie')
    parts.append(tool_input['summary_pl'])
    if tool_input.get('signals'):
        parts.append('\n## Sygnały')
        parts.extend(f'- {s}' for s in tool_input['signals'])

    thought_id = emit_thought_for_source(
        source_id=source_id, body='\n'.join(parts),
        thought_type='linkedin_post', domain='work',
        metadata={'title': source.get('title'), 'uri': source['uri'],
                  'company': tool_input.get('company')},
        extracted_tags={
            'extracted_at': _iso_now(),
            'extracted_by': PROCESSOR_NAME,
            'topic': [{'value': str(t), 'confidence': 0.8, 'new': True}
                      for t in (tool_input.get('topic_tags') or [])],
            '_entities_person': [tool_input['author_name']]
                                if tool_input.get('author_name') else [],
            '_entities_organization': [tool_input['company']]
                                      if tool_input.get('company') else [],
        },
    )
    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'signals': tool_input.get('signals') or [],
           'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


process = enrich
