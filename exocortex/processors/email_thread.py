# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/processors/email_thread.py — F6.3 heavy email thread synthesizer.
#
# Triggered when:
#   1. F6.2.2 Gmail adapter upserts email_threads row + POSTs gmail-thread to /capture.
#   2. F6.3 scorer routes here.
#   3. We check email_threads.status — only synthesize when 'ready_for_synthesis'.
#
# Output: 5-section synthesis (overview/decisions/open_questions/action_items/
# participants) re-using F4 patterns. Persists as thought + summarizes_thread
# edge → email_threads row + sets email_threads.summary_thought_id +
# transitions status → synthesized.

from __future__ import annotations

from exocortex.processors._common import (
    TENANT_ID,
    _insert_edge,
    already_processed,
    call_tool,
    conn,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
    query_one,
    update_where,
)

PROCESSOR_NAME = 'email_thread.v1'

SYSTEM_PROMPT = """\
You synthesize an email thread for a personal knowledge OS. Output 5 sections
(Polish): overview, decisions, open_questions, action_items (per owner),
participants. Be concrete and grounded — only state what the messages
actually contain.
"""

TOOL_SCHEMA = {
    'name': 'synthesize_email_thread',
    'input_schema': {
        'type': 'object',
        'properties': {
            'overview': {'type': 'string', 'description': '2-3 sentence overview in Polish.'},
            'decisions': {'type': 'array', 'items': {'type': 'string'}},
            'open_questions': {'type': 'array', 'items': {'type': 'string'}},
            'action_items': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'owner': {'type': 'string'},
                        'task': {'type': 'string'},
                    },
                    'required': ['owner', 'task'],
                    'additionalProperties': False,
                },
            },
            'participants': {'type': 'array', 'items': {'type': 'string'}},
            'sender_domains': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['overview'],
        'additionalProperties': False,
    },
}


def synthesize(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    email_thread_id = meta.get('email_thread_id')
    gmail_thread_id = meta.get('gmail_thread_id')

    # Look up email_threads row to check FSM status.
    et_row = None
    if email_thread_id:
        et_row = query_one(
            'SELECT id, status, summary_thought_id, metadata '
            'FROM email_threads WHERE id = %s',
            email_thread_id,
        )
    elif gmail_thread_id:
        et_row = query_one(
            'SELECT id, status, summary_thought_id, metadata '
            'FROM email_threads WHERE tenant_id = %s AND gmail_thread_id = %s',
            TENANT_ID, gmail_thread_id,
        )

    if et_row is None:
        return {'status': 'error', 'reason': 'no_email_threads_row', 'source_id': source_id}

    if et_row['status'] not in ('ready_for_synthesis', 'synthesized') and not force:
        # Thread is still active — defer until it goes quiescent.
        return {'status': 'deferred', 'reason': 'thread_still_active',
                'source_id': source_id, 'thread_status': et_row['status']}

    # Build synthesis input from snippets.
    snippets = (meta.get('snippets') or [])
    msg_blocks: list[str] = []
    for s in snippets:
        msg_blocks.append(
            f'--- Message ({s.get("date") or "?"}) from {s.get("from") or "?"} ---\n'
            f'{s.get("snippet") or ""}'
        )
    if not msg_blocks:
        return {'status': 'error', 'reason': 'no_snippets', 'source_id': source_id}

    user_prompt = (
        f'SUBJECT: {source.get("title") or ""}\n'
        f'MESSAGE COUNT: {len(snippets)}\n\n'
        + '\n\n'.join(msg_blocks)[:12000]
    )
    tool_input, usage = call_tool(SYSTEM_PROMPT, user_prompt, TOOL_SCHEMA, max_tokens=2048,
                                  _use_case='second_brain.F6_email_thread_processor')
    cost = estimate_cost_usd(usage)

    # Render synthesis into the thought body (F4 5-section convention).
    parts = [
        f'# {source.get("title") or "Email thread"}',
        f'URL: {source["uri"]}', '',
        '## Overview', tool_input['overview'],
    ]
    if tool_input.get('decisions'):
        parts.append('\n## Decyzje')
        parts.extend(f'- {d}' for d in tool_input['decisions'])
    if tool_input.get('open_questions'):
        parts.append('\n## Otwarte pytania')
        parts.extend(f'- {q}' for q in tool_input['open_questions'])
    if tool_input.get('action_items'):
        parts.append('\n## Action items')
        from collections import defaultdict
        by_owner = defaultdict(list)
        for ai in tool_input['action_items']:
            by_owner[ai['owner']].append(ai['task'])
        for owner, tasks in by_owner.items():
            parts.append(f'\n### {owner}')
            parts.extend(f'- [ ] (00:00) {t}' for t in tasks)
    if tool_input.get('participants'):
        parts.append('\n## Uczestnicy')
        parts.extend(f'- {p}' for p in tool_input['participants'])

    thought_id = emit_thought_for_source(
        source_id=source_id, body='\n'.join(parts),
        thought_type='email_thread_synthesis', domain='work',
        metadata={
            'title': source.get('title'),
            'uri': source['uri'],
            'email_thread_id': str(et_row['id']),
            'gmail_thread_id': gmail_thread_id,
            'sender_domains': tool_input.get('sender_domains') or [],
        },
        extracted_tags={
            'extracted_at': _iso_now(),
            'extracted_by': PROCESSOR_NAME,
            '_entities_person': tool_input.get('participants') or [],
        },
    )

    # Edges: thought → email_thread (summarizes_thread) + transition status.
    with conn() as c:
        _insert_edge(c, {
            'tenant_id': TENANT_ID,
            'src_id': thought_id, 'src_type': 'thought',
            'dst_id': str(et_row['id']), 'dst_type': 'email_thread',
            'type': 'summarizes_thread',
            'created_by': 'processor:email_thread',
        })
    update_where(
        'email_threads',
        {'status': 'synthesized', 'summary_thought_id': thought_id},
        'id = %s', str(et_row['id']),
    )

    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'email_thread_id': str(et_row['id']),
           'action_items': len(tool_input.get('action_items') or []),
           'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


process = synthesize
