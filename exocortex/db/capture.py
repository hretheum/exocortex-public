# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# db/capture.py — Database-level operations for the capture API.
#
# Extracted from capture_api.py (F31-ARCH-03) to keep the FastAPI handler
# layer free of raw SQL. All functions accept an explicit cursor (DI) —
# the HTTP layer owns transaction boundaries, not the DB layer.

from __future__ import annotations

import json
from typing import Any

from exocortex.db import query as _db_query


def fetch_today_context(tenant_id: str) -> dict[str, Any]:
    """Today's meetings with client/project links."""
    try:
        rows = _db_query(
            """
            SELECT t.id, t.metadata->>'slug' AS slug, t.metadata->>'title' AS title,
                   t.extracted_tags,
                   array_agg(DISTINCT ec.canonical_name)
                       FILTER (WHERE e.type = 'classified_as_client') AS clients,
                   array_agg(DISTINCT ep.canonical_name)
                       FILTER (WHERE e.type = 'classified_as_project') AS projects
            FROM thoughts t
            LEFT JOIN edges e ON e.src_id = t.id
                AND e.type IN ('classified_as_client', 'classified_as_project')
            LEFT JOIN entities ec ON ec.id = e.dst_id AND e.type = 'classified_as_client'
            LEFT JOIN entities ep ON ep.id = e.dst_id AND e.type = 'classified_as_project'
            WHERE t.tenant_id = %s
              AND t.thought_type = 'work_meeting_note'
              AND t.created_at::date = CURRENT_DATE
            GROUP BY t.id, t.metadata
            ORDER BY t.created_at
            """,
            tenant_id,
        )
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return {'meetings': []}

    meetings = []
    for r in rows:
        title = r.get('title') or ''
        clients = [c for c in (r.get('clients') or []) if c]
        projects = [p for p in (r.get('projects') or []) if p]
        meetings.append({
            'title': title,
            'client': clients[0] if clients else None,
            'project': projects[0] if projects else None,
            'time': '',
        })
    return {'meetings': meetings}


def get_recent_activity(tenant_id: str) -> dict[str, Any]:
    """Action items with due dates for the activity feed."""
    try:
        rows = _db_query(
            """
            SELECT metadata->>'action_items' as body, created_at
            FROM thoughts
            WHERE tenant_id = %s
              AND thought_type = 'work_meeting_note'
              AND metadata->>'action_items' IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 20
            """,
            tenant_id,
        )
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return {'top_overdue': []}

    items = []
    for r in rows:
        body = r.get('body') or ''
        for line in body.split('\n'):
            line = line.strip()
            if line.startswith(('- [ ]', '- [x]')):
                items.append({
                    'content': line,
                    'due_date': str(r.get('created_at', '')),
                })
        if len(items) >= 20:
            break
    return {'top_overdue': items[:20]}


def get_stats() -> dict[str, int]:
    """Public stats — thought and edge counts."""
    from exocortex.db import query_one as _q
    try:
        thoughts = _q("SELECT count(*) as n FROM thoughts")
        edges = _q("SELECT count(*) as n FROM edges")
        return {
            'thoughts': thoughts['n'] if thoughts else 0,
            'edges': edges['n'] if edges else 0,
        }
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return {'thoughts': 0, 'edges': 0}


def insert_raw_source(cursor, source_type: str, uri: str, metadata: dict,
                      raw_text: str) -> dict | None:
    """Insert/upsert a raw source and return the row dict, or None on conflict."""
    meta_json = json.dumps(metadata, default=str)
    cursor.execute(
        """INSERT INTO raw_sources (source_type, uri, metadata, raw_text)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (source_type, uri)
           DO UPDATE SET metadata   = EXCLUDED.metadata,
                         raw_text   = EXCLUDED.raw_text,
                         created_at = NOW()
           RETURNING id, source_type, uri, metadata, raw_text, created_at""",
        (source_type, uri, meta_json, raw_text),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        'id': str(row[0]),
        'source_type': row[1],
        'uri': row[2],
        'metadata': row[3],
        'raw_text': row[4],
        'created_at': str(row[5]) if row[5] else None,
    }


def was_new_row(cursor, source_type: str, uri: str) -> bool:
    """Check whether the just-inserted row was new (not an ON CONFLICT update)."""
    cursor.execute(
        "SELECT id FROM raw_sources WHERE source_type = %s AND uri = %s",
        (source_type, uri),
    )
    row = cursor.fetchone()
    return row is not None
