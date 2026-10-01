# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/db/ingest.py — high-level ingestion and edge emission helpers.

from __future__ import annotations

import logging
import re as _re_uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb

from .embeddings import get_embedding
from .graph import _insert_edge
from .pool import conn, insert_returning, query, query_one, update_where

logger = logging.getLogger(__name__)

# UUID v4 (and v1/v3/v5) canonical form. Used to filter out LLM hallucinations
# in synthesis content where source_thought_id was supposed to be a UUID but
# the model wrote a meeting title (e.g. "eFX demo") instead.
_UUID_RE = _re_uuid.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)


def _is_uuid(value: Any) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _split_participants(raw_participants: list[str] | None) -> list[str]:
    """Defensive normalizer for `metadata.participants`. Sometimes Fireflies
    sends one comma-separated string instead of a list of emails (F4.6.5 backlog).
    Strips whitespace, drops empties."""
    out: list[str] = []
    for entry in (raw_participants or []):
        if not entry:
            continue
        if ',' in entry:
            out.extend(e.strip() for e in entry.split(',') if e.strip())
        else:
            out.append(entry.strip())
    return out


def _upsert_entity(c, canonical_name: str, entity_type: str, tenant_id: str) -> str:
    """Find-or-create entity. Returns entity_id as str.

    psycopg3 returns uuid columns as uuid.UUID, not str — every caller feeds
    this straight into _insert_edge()'s src_id/dst_id, which _validate_uuid()
    regex-matches as a string. Without str() here, EVERY entity edge in the
    codebase (person/client/project/ingredient/material/topic/newsletter)
    raised TypeError and silently failed (scorer/ingest catch-and-log, never
    crash) — found auditing the F33/meeting-ingest refactor 2026-07-29, fixed
    at the source instead of patching each of the ~15 call sites.
    """
    existing = c.execute(
        'SELECT id FROM entities WHERE tenant_id = %s AND canonical_name = %s',
        (tenant_id, canonical_name),
    ).fetchone()
    if existing:
        return str(existing['id'])
    created = c.execute(
        'INSERT INTO entities (tenant_id, canonical_name, type) VALUES (%s, %s, %s) RETURNING *',
        (tenant_id, canonical_name, entity_type),
    ).fetchone()
    return str(created['id'])


# ─────────────────────────── High-level ingestion ───────────────────────────

def ingest_source(url: str, tenant_id: str, force_reingest: bool = False) -> dict:
    """Upsert raw_source + content_queue. Returns {'content_id', 'source_id'}."""
    if not force_reingest:
        existing = query_one(
            'SELECT id FROM raw_sources WHERE tenant_id = %s AND uri = %s',
            tenant_id, url,
        )
        if existing:
            source_id = existing['id']
            cq = query_one(
                'SELECT id FROM content_queue WHERE source_id = %s LIMIT 1',
                source_id,
            )
            if cq:
                return {'content_id': cq['id'], 'source_id': source_id}

    source = insert_returning('raw_sources', {'tenant_id': tenant_id, 'uri': url})
    cq = insert_returning('content_queue', {
        'tenant_id': tenant_id,
        'source_id': source['id'],
        'status': 'used',
    })
    return {'content_id': cq['id'], 'source_id': source['id']}


def create_frp_session(content_id: str, frame: str, level: int,
                       context_note: str | None = None,
                       tenant_id: str | None = None) -> dict:
    """Insert FRP session row. Returns {'session_id'}."""
    session = insert_returning('frp_sessions', {
        'tenant_id': tenant_id,
        'content_id': content_id,
        'frame': frame,
        'level': level,
        'context_note': context_note,
    })
    return {'session_id': session['id']}


# F7.4 — entity types whose canonical_name lives in non-FRP domains.
_NON_FRP_ENTITY_TYPES = frozenset({
    'person', 'client', 'project',
    '3d_model', 'recipe', 'arxiv_paper',
})


def append_session_thought(session_id: str, thought_type: str, body: str,
                           entity_links: list[dict] | None = None,
                           tenant_id: str | None = None) -> dict:
    """Insert thought and attach to FRP session via session_contains edge."""
    with conn() as c:
        thought = c.execute(
            'INSERT INTO thoughts (tenant_id, body, thought_type, author, metadata, embedding) '
            'VALUES (%s, %s, %s, %s, %s, %s) RETURNING *',
            (tenant_id, body, thought_type, 'human:exocortex_user',
             Jsonb({'domain': 'frp'}), get_embedding(body)),
        ).fetchone()
        thought_id = thought['id']

        _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': session_id, 'src_type': 'frp_session',
            'dst_id': thought_id, 'dst_type': 'thought',
            'type': 'session_contains',
            'created_by': 'inbox_parser',
        })

        if entity_links:
            for link in entity_links:
                entity_type = link['entity_type']
                entity_id = _upsert_entity(c, link['entity_canonical_name'],
                                           entity_type, tenant_id)
                _insert_edge(c, {
                    'tenant_id': tenant_id,
                    'src_id': thought_id, 'src_type': 'thought',
                    'dst_id': entity_id, 'dst_type': 'entity',
                    'type': link['edge_type'],
                    'created_by': 'db_layer',
                })

                if entity_type in _NON_FRP_ENTITY_TYPES:
                    _insert_edge(c, {
                        'tenant_id': tenant_id,
                        'src_id': thought_id, 'src_type': 'thought',
                        'dst_id': entity_id, 'dst_type': 'entity',
                        'type': 'signals_domain',
                        'created_by': 'frp_signal',
                    })

    return {'thought_id': thought_id}


def complete_session(session_id: str, resonance: int, tags: dict,
                     signal_today: bool = False,
                     tenant_id: str | None = None) -> None:
    """Finalise FRP session: set resonance, schedule revisit (NOW+48h), update tags."""
    with conn() as c:
        c.execute(
            "UPDATE frp_sessions SET resonance = %s, "
            "revisit_due = (NOW() + INTERVAL '48 hours')::date, "
            "status = 'revisited' "
            "WHERE id = %s",
            (resonance, session_id),
        )

    session = query_one('SELECT content_id FROM frp_sessions WHERE id = %s', session_id)
    if session and session['content_id']:
        update_where('content_queue',
                     {'ai_tags': tags, 'status': 'used'},
                     'id = %s', session['content_id'])

    if signal_today:
        edges = query(
            'SELECT dst_id FROM edges WHERE tenant_id = %s AND src_id = %s '
            "AND src_type = 'frp_session' AND type = 'session_contains'",
            tenant_id, session_id,
        )
        for edge in edges:
            t = query_one('SELECT metadata FROM thoughts WHERE id = %s', edge['dst_id'])
            if t:
                meta = {**(t['metadata'] or {}), 'signal_today': 'true'}
                update_where('thoughts', {'metadata': meta}, 'id = %s', edge['dst_id'])


def find_session_by_date(session_ref: str, tenant_id: str) -> str:
    """Find FRP session by date string (YYYY-MM-DD). Returns session_id."""
    result = query_one(
        'SELECT id FROM frp_sessions WHERE tenant_id = %s '
        'AND created_at >= %s::timestamptz AND created_at <= %s::timestamptz '
        'LIMIT 1',
        tenant_id,
        f'{session_ref}T00:00:00+00:00',
        f'{session_ref}T23:59:59+00:00',
    )
    if not result:
        raise ValueError(f"No FRP session found for date: {session_ref}")
    return result['id']


def add_revisit(session_id: str, body: str,
                materializes_as_url: str | None = None,
                tenant_id: str | None = None) -> dict:
    """Add a revisit thought linked to the original session."""
    with conn() as c:
        thought = c.execute(
            'INSERT INTO thoughts (tenant_id, body, thought_type, author, metadata) '
            'VALUES (%s, %s, %s, %s, %s) RETURNING *',
            (tenant_id, body, 'frp_revisit', 'human:exocortex_user', Jsonb({'domain': 'frp'})),
        ).fetchone()
        thought_id = thought['id']

        _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thought_id, 'src_type': 'thought',
            'dst_id': session_id, 'dst_type': 'frp_session',
            'type': 'revisits',
            'created_by': 'inbox_parser',
        })

        c.execute(
            "UPDATE frp_sessions SET revisited_at = %s, status = 'revisited' WHERE id = %s",
            (datetime.now(UTC), session_id),
        )

        if materializes_as_url:
            source = c.execute(
                'INSERT INTO raw_sources (tenant_id, uri, source_type) '
                'VALUES (%s, %s, %s) RETURNING *',
                (tenant_id, materializes_as_url, 'frp_materialized'),
            ).fetchone()
            _insert_edge(c, {
                'tenant_id': tenant_id,
                'src_id': thought_id, 'src_type': 'thought',
                'dst_id': source['id'], 'dst_type': 'raw_source',
                'type': 'materializes_as',
                'created_by': 'inbox_parser',
            })

    return {'thought_id': thought_id}


def ingest_note(body: str, domain: str, thought_type: str,
                metadata: dict | None = None,
                entity_links: list[dict] | None = None,
                tenant_id: str | None = None) -> dict:
    """Insert a thought. Returns {'thought_id'}."""
    full_meta = {'domain': domain, **(metadata or {})}

    with conn() as c:
        thought = c.execute(
            'INSERT INTO thoughts (tenant_id, body, thought_type, author, metadata, embedding) '
            'VALUES (%s, %s, %s, %s, %s, %s) RETURNING *',
            (tenant_id, body, thought_type, 'human:exocortex_user',
             Jsonb(full_meta), get_embedding(body)),
        ).fetchone()
        thought_id = thought['id']

        if entity_links:
            for link in entity_links:
                entity_id = _upsert_entity(c, link['entity_canonical_name'],
                                           link['entity_type'], tenant_id)
                _insert_edge(c, {
                    'tenant_id': tenant_id,
                    'src_id': thought_id, 'src_type': 'thought',
                    'dst_id': entity_id, 'dst_type': 'entity',
                    'type': link['edge_type'],
                    'created_by': 'db_layer',
                })

    return {'thought_id': thought_id}


def ingest_print_log(print_data: dict, tenant_id: str | None = None) -> dict:
    """Ingest a 3D print log block."""
    lines = []
    for field in ('model', 'printer', 'material', 'result', 'notes'):
        if print_data.get(field):
            lines.append(f"{field.capitalize()}: {print_data[field]}")
    body = '\n'.join(lines) or str(print_data)

    entity_links = []
    if print_data.get('printer'):
        entity_links.append({'entity_canonical_name': print_data['printer'],
                             'entity_type': 'printer', 'edge_type': 'printed_on'})
    if print_data.get('material'):
        entity_links.append({'entity_canonical_name': print_data['material'],
                             'entity_type': 'material', 'edge_type': 'printed_with'})

    return ingest_note(
        body=body,
        domain='3d',
        thought_type='print_log',
        metadata={k: print_data[k] for k in ('printer', 'material', 'quality_score', 'duration_h')
                  if k in print_data},
        entity_links=entity_links or None,
        tenant_id=tenant_id,
    )


# ─────────────────────────── Edge emit helpers (F4.6.1) ───────────────────────────

def _emit_meeting_edges(c, thought_id: str, metadata: dict,
                        classification, tenant_id: str) -> dict:
    """Emit per-meeting edges in one open connection."""
    counts = {'attended_meeting': 0, 'classified_as_client': 0,
              'classified_as_project': 0}

    participants = _split_participants(metadata.get('participants'))
    for email in participants:
        person_id = _upsert_entity(c, email, 'person', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thought_id, 'src_type': 'thought',
            'dst_id': person_id, 'dst_type': 'person',
            'type': 'attended_meeting',
            'created_by': 'bulk_ingest_vault',
        })
        if res is not None:
            counts['attended_meeting'] += 1

    client_slug = getattr(classification, 'client', None)
    if client_slug:
        client_id = _upsert_entity(c, client_slug, 'client', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thought_id, 'src_type': 'thought',
            'dst_id': client_id, 'dst_type': 'client',
            'type': 'classified_as_client',
            'created_by': 'bulk_ingest_vault',
        })
        if res is not None:
            counts['classified_as_client'] += 1

    project_slug = getattr(classification, 'project', None)
    if project_slug:
        project_id = _upsert_entity(c, project_slug, 'project', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thought_id, 'src_type': 'thought',
            'dst_id': project_id, 'dst_type': 'project',
            'type': 'classified_as_project',
            'created_by': 'bulk_ingest_vault',
        })
        if res is not None:
            counts['classified_as_project'] += 1

    return counts


def emit_meeting_edges(thought_id: str, metadata: dict, classification,
                       tenant_id: str) -> dict:
    """Public wrapper: opens a connection and calls _emit_meeting_edges."""
    with conn() as c:
        return _emit_meeting_edges(c, thought_id, metadata, classification, tenant_id)


def _emit_synthesis_edges(c, synthesis_id: str, content: dict,
                          tenant_id: str) -> dict:
    """Emit per-synthesis edges in one open connection."""
    counts = {'decided_in': 0, 'addresses_problem': 0, 'mentions_person': 0,
              'skipped_invalid_uuid': 0}

    for d in (content.get('recent_decisions') or []):
        tid = d.get('source_thought_id')
        if not _is_uuid(tid):
            if tid:
                counts['skipped_invalid_uuid'] += 1
            continue
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': synthesis_id, 'src_type': 'synthesis',
            'dst_id': tid, 'dst_type': 'thought',
            'type': 'decided_in',
            'created_by': 'synthesizer',
        })
        if res is not None:
            counts['decided_in'] += 1

    for p in (content.get('open_problems') or []):
        tid = p.get('source_thought_id')
        if not _is_uuid(tid):
            if tid:
                counts['skipped_invalid_uuid'] += 1
            continue
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': synthesis_id, 'src_type': 'synthesis',
            'dst_id': tid, 'dst_type': 'thought',
            'type': 'addresses_problem',
            'created_by': 'synthesizer',
        })
        if res is not None:
            counts['addresses_problem'] += 1

    seen_persons: set[str] = set()
    for o in (content.get('ownership') or []):
        person = (o.get('person') or '').strip()
        if not person or person in seen_persons:
            continue
        seen_persons.add(person)
        person_id = _upsert_entity(c, person, 'person', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': synthesis_id, 'src_type': 'synthesis',
            'dst_id': person_id, 'dst_type': 'person',
            'type': 'mentions_person',
            'created_by': 'synthesizer',
        })
        if res is not None:
            counts['mentions_person'] += 1

    return counts


def emit_synthesis_edges(synthesis_id: str, content: dict, tenant_id: str) -> dict:
    """Public wrapper: opens a connection and calls _emit_synthesis_edges."""
    with conn() as c:
        return _emit_synthesis_edges(c, synthesis_id, content, tenant_id)


def _emit_thread_edges(c, thread_id: str, classification, *,
                       sender_email: str | None = None,
                       recipients: list[str] | None = None,
                       tenant_id: str) -> dict:
    """F6.4.5 — edges populating for an email_thread row."""
    counts = {'email_correspondent': 0,
              'classified_as_client': 0,
              'classified_as_project': 0}

    addresses = []
    if sender_email:
        addresses.append(sender_email)
    addresses.extend(_split_participants(recipients))
    seen: set[str] = set()
    for email in addresses:
        if not email or email in seen:
            continue
        seen.add(email)
        person_id = _upsert_entity(c, email, 'person', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thread_id, 'src_type': 'email_thread',
            'dst_id': person_id, 'dst_type': 'person',
            'type': 'email_correspondent',
            'created_by': 'email_classifier',
        })
        if res is not None:
            counts['email_correspondent'] += 1

    client_slug = getattr(classification, 'client', None)
    if client_slug:
        client_id = _upsert_entity(c, client_slug, 'client', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thread_id, 'src_type': 'email_thread',
            'dst_id': client_id, 'dst_type': 'client',
            'type': 'classified_as_client',
            'created_by': 'email_classifier',
        })
        if res is not None:
            counts['classified_as_client'] += 1

    project_slug = getattr(classification, 'project', None)
    if project_slug:
        project_id = _upsert_entity(c, project_slug, 'project', tenant_id)
        res = _insert_edge(c, {
            'tenant_id': tenant_id,
            'src_id': thread_id, 'src_type': 'email_thread',
            'dst_id': project_id, 'dst_type': 'project',
            'type': 'classified_as_project',
            'created_by': 'email_classifier',
        })
        if res is not None:
            counts['classified_as_project'] += 1

    return counts


def emit_thread_edges(thread_id: str, classification, *,
                      sender_email: str | None = None,
                      recipients: list[str] | None = None,
                      tenant_id: str) -> dict:
    """Public wrapper: opens a connection and calls _emit_thread_edges."""
    with conn() as c:
        return _emit_thread_edges(c, thread_id, classification,
                                  sender_email=sender_email,
                                  recipients=recipients,
                                  tenant_id=tenant_id)
