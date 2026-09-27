# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
# exocortex/processors/claude_session.py — distil a Claude Code session.
#
# Input: a `claude-session` raw_source whose body is the ALREADY-REDACTED
# dialogue (user prompts + assistant prose) produced by
# exocortex/sources/claude_sessions.py. This processor never re-reads the
# original .jsonl — the redacted body in the database is the only text it sees.
#
# Output: a `claude_session` thought under domain `sb` (second-brain / meta):
# what the session did, the decisions made, the mistakes hit AND why (the most
# valuable, most perishable part), and which areas of the codebase it touched.

from __future__ import annotations

from exocortex.processors._common import (
    already_processed,
    call_tool,
    emit_thought_for_source,
    estimate_cost_usd,
    fetch_source,
    mark_processed,
)

PROCESSOR_NAME = 'claude_session.v1'

SYSTEM_PROMPT = """\
Dostajesz zapis rozmowy z sesji Claude Code (tylko dialog: prompty użytkownika
i proza odpowiedzi — bez wyników narzędzi). Wyciągnij trwałą wartość tej sesji
po polsku:
- summary_pl: 2-4 zdania, co ta sesja realnie osiągnęła.
- decisions: konkretne decyzje podjęte w sesji (nie kroki techniczne).
- mistakes: pomyłki popełnione w trakcie WRAZ Z PRZYCZYNĄ — to jest
  najcenniejsze, bo to wiedza, która inaczej wyparuje. Puste, jeśli sesja
  przebiegła bez pomyłek.
- touched: obszary/pliki/moduły, których sesja dotknęła.
Nie zmyślaj. Jeśli czegoś nie ma w dialogu, zostaw pustą listę.
"""

TOOL_SCHEMA = {
    'name': 'distil_session',
    'description': 'Extract durable value from a Claude Code session transcript.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'summary_pl': {'type': 'string'},
            'decisions': {'type': 'array', 'items': {'type': 'string'}},
            'mistakes': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'what': {'type': 'string'},
                        'cause': {'type': 'string'},
                    },
                    'required': ['what'],
                    'additionalProperties': False,
                },
            },
            'touched': {'type': 'array', 'items': {'type': 'string'}},
        },
        'required': ['summary_pl'],
        'additionalProperties': False,
    },
}

# Long sessions: the dialogue of even a 32 MB session is ~415 KB, still too much
# for one call. Cap the text sent to the model; the head of a session carries
# the goal and the tail carries the outcome, so keep both ends.
_MAX_BODY_CHARS = 48_000


_CLIP_MARKER = '\n\n[... środek sesji pominięty dla długości ...]\n\n'


def _clip(body: str) -> str:
    """Keep both ends within _MAX_BODY_CHARS INCLUDING the marker — the head
    carries the session's goal, the tail its outcome."""
    if len(body) <= _MAX_BODY_CHARS:
        return body
    half = (_MAX_BODY_CHARS - len(_CLIP_MARKER)) // 2
    return body[:half] + _CLIP_MARKER + body[-half:]


def _render_body(title: str, uri: str, ti: dict) -> str:
    parts = [f'# {title}', f'Sesja: {uri}', '', ti.get('summary_pl', '').strip()]
    decisions = [str(d).strip() for d in (ti.get('decisions') or []) if str(d).strip()]
    if decisions:
        parts += ['', '## Decyzje'] + [f'- {d}' for d in decisions]
    mistakes = [m for m in (ti.get('mistakes') or []) if isinstance(m, dict) and m.get('what')]
    if mistakes:
        parts += ['', '## Pomyłki i przyczyny']
        for m in mistakes:
            cause = str(m.get('cause') or '').strip()
            line = f'- {str(m["what"]).strip()}'
            if cause:
                line += f' — *przyczyna:* {cause}'
            parts.append(line)
    touched = [str(t).strip() for t in (ti.get('touched') or []) if str(t).strip()]
    if touched:
        parts += ['', '## Dotknięte obszary'] + [f'- {t}' for t in touched]
    return '\n'.join(parts)


def process(source_id: str, *, force: bool = False) -> dict:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if source is None:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    body = (meta.get('raw_payload') or '').strip()
    if not body:
        return {'status': 'error', 'reason': 'empty_body', 'source_id': source_id}

    title = source.get('title') or f'Sesja {source_id[:8]}'
    uri = source.get('uri') or ''

    tool_input, usage = call_tool(
        SYSTEM_PROMPT,
        f'TYTUŁ: {title}\n\nDIALOG:\n{_clip(body)}',
        TOOL_SCHEMA, max_tokens=1536,
        _use_case='second_brain.F_claude_session_processor',
    )
    cost = estimate_cost_usd(usage)

    thought_body = _render_body(title, uri, tool_input)
    extracted_tags = {
        'extracted_by': PROCESSOR_NAME,
        'topic': [{'value': str(t), 'confidence': 0.8, 'new': False}
                  for t in (tool_input.get('touched') or [])[:8]],
    }

    thought_id = emit_thought_for_source(
        source_id=source_id,
        body=thought_body,
        thought_type='claude_session',
        domain='sb',
        metadata={
            'title': title,
            'uri': uri,
            'session_id': meta.get('session_id'),
            'redaction_verdict': meta.get('redaction_verdict'),
            'decision_count': len(tool_input.get('decisions') or []),
            'mistake_count': len([m for m in (tool_input.get('mistakes') or [])
                                  if isinstance(m, dict) and m.get('what')]),
        },
        extracted_tags=extracted_tags,
    )

    out = {'status': 'ok', 'source_id': source_id, 'thought_id': thought_id,
           'cost_usd': round(cost, 6)}
    mark_processed(source_id, PROCESSOR_NAME, out)
    return out
