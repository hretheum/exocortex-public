# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/github.py — F6.3 GitHub issue/PR digest.

from __future__ import annotations

from exocortex.processors._common import (
    already_processed,
    call_tool,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'github.v1'

SYSTEM_PROMPT = """\
You digest a GitHub issue or pull request page into structured fields for a
personal knowledge OS. Focus on decisions and action items — what should the
reader do or remember?

Action items follow this format (re-used from F2.3 meeting parser):
  ### {Owner}
  - [ ] (HH:MM) Task description #tag

Use 'Nieprzypisane' as owner when no clear owner is stated.
"""

TOOL_SCHEMA = {
    'name': 'digest_github',
    'description': 'Digest a GitHub issue/PR.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'problem_statement': {'type': 'string', 'description': '2-3 sentence summary in Polish.'},
            'decisions': {'type': 'array', 'items': {'type': 'string'}},
            'action_items': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'owner': {'type': 'string'},
                        'task': {'type': 'string'},
                        'tags': {'type': 'array', 'items': {'type': 'string'}},
                    },
                    'required': ['owner', 'task'],
                    'additionalProperties': False,
                },
            },
            'participants': {'type': 'array', 'items': {'type': 'string'}},
            'status': {'type': 'string', 'enum': ['open', 'closed', 'merged', 'draft']},
        },
        'required': ['problem_statement', 'status'],
        'additionalProperties': False,
    },
}


def digest(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}
    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    body = (meta.get('raw_payload') or meta.get('excerpt') or '').strip()
    if not body or len(body) < 50:
        return {'status': 'error', 'reason': 'no_body', 'source_id': source_id}

    user_prompt = (
        f'TITLE: {source.get("title") or ""}\n'
        f'URL: {source["uri"]}\n\n'
        f'BODY:\n{body[:8000]}'
    )
    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=1024,
                                  _use_case='second_brain.F6_github_processor')
    cost = estimate_cost_usd(usage)

    parts = [
        f'# {source.get("title") or "(untitled)"}',
        f'URL: {source["uri"]}',
        f'Status: {tool_input["status"]}',
        '',
        '## Streszczenie',
        tool_input['problem_statement'],
    ]
    if tool_input.get('decisions'):
        parts.append('\n## Decyzje')
        for d in tool_input['decisions']:
            parts.append(f'- {d}')
    if tool_input.get('action_items'):
        parts.append('\n## Action items')
        # Group by owner.
        from collections import defaultdict
        by_owner = defaultdict(list)
        for ai in tool_input['action_items']:
            by_owner[ai['owner']].append(ai)
        for owner, items in by_owner.items():
            parts.append(f'\n### {owner}')
            for ai in items:
                tag_str = ' ' + ' '.join(f'#{t}' for t in (ai.get('tags') or []))
                parts.append(f'- [ ] (00:00) {ai["task"]}{tag_str}')

    thought_id = emit_thought_for_source(
        source_id=source_id,
        body='\n'.join(parts),
        thought_type='github_issue_digest',
        domain='work',
        metadata={'title': source.get('title'), 'uri': source['uri'],
                  'github_status': tool_input['status']},
        extracted_tags={
            'extracted_at': _iso_now(),
            'extracted_by': PROCESSOR_NAME,
            '_entities_person': tool_input.get('participants') or [],
        },
    )
    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'cost_usd': round(cost, 6),
           'action_items': len(tool_input.get('action_items') or [])}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


process = digest
