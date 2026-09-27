# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# exocortex/processors/vault_backlog.py — F33.2 vault-backlog processor.
#
# For the ~835 backlog/roadmap items under `_source/backlog/*` — TaskNotes-
# style atomic tickets, not prose. Deterministic, no LLM: the value is in the
# structured frontmatter (status, blockedBy, effort, area), not the text.
# Embedding covers only title + description, on purpose — embedding the raw
# body would make every ticket look alike to semantic search (they're mostly
# metadata) and would drown proper vault-note prose in nightly synthesis.
#
# blockedBy resolves to other backlog items by their frontmatter `id` field
# (bare ticket IDs like "P2-028", not [[wikilinks]] — confirmed against real
# data during F33 build). Forward references (blocker not ingested yet) are
# skipped, not errors — running the batch a second time after the full
# first-fill re-resolves them, since by then every id exists. See
# docs/deployment/pierwsze-zasilenie.md for the two-pass procedure.

from __future__ import annotations
from typing import Any, Optional

from exocortex.processors._common import (
    TENANT_ID, already_processed, fetch_source, mark_processed,
    _insert_edge, _upsert_entity,
)
from exocortex.db import Jsonb, conn, get_embedding, query_one

PROCESSOR_NAME = 'vault_backlog.v1'


def _strip_wikilink(value: Any) -> Optional[str]:
    """'[[globex]]' -> 'globex'. Passes through plain strings unchanged."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if v.startswith('[[') and v.endswith(']]'):
        v = v[2:-2].split('|', 1)[0].strip()
    return v or None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _resolve_backlog_id(ticket_id: str) -> Optional[str]:
    """Find the thought for another backlog item by its frontmatter `id`."""
    row = query_one(
        "SELECT t.id FROM thoughts t "
        "WHERE t.tenant_id = %s AND t.thought_type = 'backlog_item' "
        "AND t.metadata->>'ticket_id' = %s LIMIT 1",
        TENANT_ID, ticket_id,
    )
    return str(row['id']) if row else None


def process(source_id: str, *, force: bool = False) -> dict[str, Any]:
    if not force and already_processed(source_id, PROCESSOR_NAME):
        return {'status': 'skipped', 'reason': 'already_processed', 'source_id': source_id}

    source = fetch_source(source_id)
    if not source:
        return {'status': 'error', 'reason': 'source_not_found', 'source_id': source_id}

    meta = source.get('metadata') or {}
    fm = meta.get('frontmatter') or {}
    vault_path = meta.get('vault_path') or source.get('uri') or ''

    ticket_id = str(fm.get('id') or vault_path.rsplit('/', 1)[-1].removesuffix('.md'))
    title = str(fm.get('title') or ticket_id)
    description = str(fm.get('description') or fm.get('subject') or '')
    embed_text = f'{title}\n{description}'.strip()

    blocked_by = _as_list(fm.get('blockedBy'))
    area = _strip_wikilink(fm.get('area'))
    completed = fm.get('completed')
    structured_meta = {
        'domain': 'work',
        'ticket_id': ticket_id,
        'vault_path': vault_path,
        'blocked_by_ids': blocked_by,
        'area': area,
        'status': fm.get('status'),
        'priority': fm.get('priority'),
        'phase': fm.get('phase'),
        'sprint': fm.get('sprint'),
        'completed': completed if completed else None,
        'effort_hours': fm.get('effort_hours') or fm.get('estimate_hours'),
        'bau_hours': fm.get('bau_hours'),
        'cost_category': fm.get('cost_category'),
    }

    embedding = get_embedding(embed_text) if embed_text else None
    emb_literal = (
        '[' + ','.join(repr(float(x)) for x in embedding) + ']' if embedding else None
    )

    with conn() as c:
        existing = c.execute(
            "SELECT id FROM thoughts WHERE tenant_id = %s AND source_id = %s "
            "AND thought_type = 'backlog_item' LIMIT 1",
            (TENANT_ID, source_id),
        ).fetchone()
        if existing:
            tid = str(existing['id'])
            c.execute(
                'UPDATE thoughts SET body = %s, metadata = %s, embedding = %s WHERE id = %s',
                (embed_text, Jsonb(structured_meta), emb_literal, tid),
            )
        else:
            row = c.execute(
                'INSERT INTO thoughts (tenant_id, source_id, body, thought_type, '
                'author, metadata, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s) '
                'RETURNING id',
                (TENANT_ID, source_id, embed_text, 'backlog_item', 'agent:processor',
                 Jsonb(structured_meta), emb_literal),
            ).fetchone()
            tid = str(row['id'])

        _insert_edge(c, {
            'tenant_id': TENANT_ID,
            'src_id': tid, 'src_type': 'thought',
            'dst_id': source_id, 'dst_type': 'raw_source',
            'type': 'acquired_from',
            'created_by': 'processor:vault_backlog',
        })

        area_edge = False
        if area:
            project_id = str(_upsert_entity(c, area, 'project', TENANT_ID))
            area_edge = _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': tid, 'src_type': 'thought',
                'dst_id': project_id, 'dst_type': 'project',
                'type': 'classified_as_project',
                'created_by': 'processor:vault_backlog',
            }) is not None

    blocked_edges = 0
    for blocker_ticket_id in blocked_by:
        blocker_thought_id = _resolve_backlog_id(blocker_ticket_id)
        if blocker_thought_id is None:
            continue  # forward reference — resolves on a second pass
        with conn() as c:
            if _insert_edge(c, {
                'tenant_id': TENANT_ID,
                'src_id': tid, 'src_type': 'thought',
                'dst_id': blocker_thought_id, 'dst_type': 'thought',
                'type': 'blocked_by',
                'created_by': 'processor:vault_backlog',
            }) is not None:
                blocked_edges += 1

    output = {
        'status': 'ok', 'source_id': source_id, 'ticket_id': ticket_id,
        'thought_id': tid, 'area_edge': area_edge,
        'blocked_by_found': len(blocked_by), 'blocked_by_resolved': blocked_edges,
    }
    mark_processed(source_id, PROCESSOR_NAME, output)
    return output
