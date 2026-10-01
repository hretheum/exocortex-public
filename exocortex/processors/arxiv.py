# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/arxiv.py — F6.3 arXiv paper relevance scorer.

from __future__ import annotations

from datetime import UTC

from exocortex.processors._common import (
    already_processed,
    call_tool,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'arxiv.v1'

SYSTEM_PROMPT = """\
You assess an arXiv paper for relevance to AI agents / LLMs / cognitive
architectures / multi-agent systems / agent infrastructure (the user's main
research interest). You produce a Polish abstract translation, key findings,
and a relevance score 1-10.
"""

TOOL_SCHEMA = {
    'name': 'assess_arxiv',
    'input_schema': {
        'type': 'object',
        'properties': {
            'abstract_pl': {'type': 'string', 'description': '3-5 sentence Polish abstract translation.'},
            'key_findings': {'type': 'array', 'items': {'type': 'string'}},
            'relevance_score': {'type': 'integer', 'minimum': 1, 'maximum': 10},
            'topic_tags': {'type': 'array', 'items': {'type': 'string'},
                           'description': 'From: llm, multi-agent, rag, evaluation, alignment, '
                                          'mech-interp, reasoning, planning, tool-use.'},
        },
        'required': ['abstract_pl', 'relevance_score'],
        'additionalProperties': False,
    },
}


def relevance(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}
    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    body = (meta.get('raw_payload') or meta.get('excerpt') or '').strip()
    if not body or len(body) < 100:
        return {'status': 'error', 'reason': 'no_body', 'source_id': source_id}

    user_prompt = (
        f'TITLE: {source.get("title") or ""}\n'
        f'URL: {source["uri"]}\n'
        f'AUTHORS: {source.get("author_name") or ""}\n\n'
        f'CONTENT:\n{body[:10000]}'
    )
    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=1024,
                                  _use_case='second_brain.F6_arxiv_processor')
    cost = estimate_cost_usd(usage)

    body_for_thought = (
        f'# {source.get("title") or "(untitled)"}\n'
        f'URL: {source["uri"]}\n'
        f'**Relevance: {tool_input["relevance_score"]}/10**\n\n'
        f'## Streszczenie\n{tool_input["abstract_pl"]}\n\n'
        f'## Key findings\n' +
        '\n'.join(f'- {f}' for f in (tool_input.get('key_findings') or []))
    )
    extracted_tags = {
        'extracted_at': _iso_now(),
        'extracted_by': PROCESSOR_NAME,
        'topic': [{'value': str(t), 'confidence': 0.85, 'new': False}
                  for t in (tool_input.get('topic_tags') or [])],
        '_relevance_score': tool_input['relevance_score'],
    }
    thought_id = emit_thought_for_source(
        source_id=source_id, body=body_for_thought,
        thought_type='arxiv_paper', domain='papers',
        metadata={'title': source.get('title'), 'uri': source['uri'],
                  'relevance_score': tool_input['relevance_score']},
        extracted_tags=extracted_tags,
    )
    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'relevance_score': tool_input['relevance_score'],
           'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime
    return datetime.now(UTC).isoformat()


process = relevance
