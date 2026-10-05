# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Database helpers for lab jobs.

Lab code takes an explicit connection (autocommit, dict rows) instead of the
engine's global pool, so every function can be tested against a throwaway
database. Graph writes go to the engine's tables (``raw_sources``,
``thoughts``, ``edges``) and, when the database has Apache AGE, to the AGE
graph as well, exactly like the engine's own dual write.
"""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb


def connect(url: str | None = None) -> psycopg.Connection[DictRow]:
    conn = psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row)
    has_age = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'age'").fetchone() is not None
    if has_age:
        conn.execute("LOAD 'age'")
        conn.execute('SET search_path = public, "$user", ag_catalog')
    conn.info_has_age = has_age  # type: ignore[attr-defined]
    return conn


def tenant_id() -> str:
    value = os.environ.get("TENANT_ID") or os.environ.get("EXOCORTEX_TENANT_ID")
    if not value:
        raise KeyError("TENANT_ID is not set")
    return value


def _vector(embedding: list[float] | None) -> str | None:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]" if embedding else None


def capture_source(conn, tenant: str, *, source_type: str, uri: str, title: str | None,
                   metadata: dict[str, Any]) -> tuple[str, bool]:
    """Upsert a raw source after the allowlist check; (id, changed).

    The same gate as the Capture API (F2.2): a source that is not on the
    allowlist raises SourceNotAllowed and is logged, before anything is
    written. ``changed`` is true for a new row or new content.
    """
    from exocortex.source_allowlist import require_capture

    require_capture(source_type, uri)
    row = conn.execute(
        """
        INSERT INTO raw_sources (tenant_id, uri, title, source_name, source_type, metadata)
        VALUES (%s, %s, %s, 'lab', %s, %s::jsonb)
        ON CONFLICT (tenant_id, source_type, uri) DO UPDATE SET
            title = EXCLUDED.title, metadata = EXCLUDED.metadata, ingested_at = NOW()
        WHERE raw_sources.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        RETURNING id
        """,
        (tenant, uri, title, source_type, json.dumps(metadata, default=str)),
    ).fetchone()
    if row:
        return str(row["id"]), True
    existing = conn.execute(
        "SELECT id FROM raw_sources WHERE tenant_id = %s AND source_type = %s AND uri = %s",
        (tenant, source_type, uri),
    ).fetchone()
    return str(existing["id"]), False


def upsert_thought(conn, tenant: str, *, source_id: str | None, thought_type: str, body: str,
                   metadata: dict[str, Any], key: str | None = None,
                   embedding: list[float] | None = None) -> tuple[str, bool]:
    """Insert or update a lab node; (id, created).

    A node is identified by (source_id, thought_type) or, when ``key`` is
    given, by (thought_type, metadata->>'key'). Updating keeps an existing
    embedding unless a new one is passed and clears it when the body changed.
    """
    meta = dict(metadata)
    if key is not None:
        meta["key"] = key
        found = conn.execute(
            "SELECT id, body FROM thoughts WHERE tenant_id = %s AND thought_type = %s AND metadata->>'key' = %s",
            (tenant, thought_type, key),
        ).fetchone()
    else:
        found = conn.execute(
            "SELECT id, body FROM thoughts WHERE tenant_id = %s AND thought_type = %s AND source_id = %s",
            (tenant, thought_type, source_id),
        ).fetchone()
    if found is None:
        row = conn.execute(
            """INSERT INTO thoughts (tenant_id, source_id, body, thought_type, author, metadata, embedding)
               VALUES (%s, %s, %s, %s, 'agent:lab', %s, %s) RETURNING id""",
            (tenant, source_id, body, thought_type, Jsonb(meta), _vector(embedding)),
        ).fetchone()
        return str(row["id"]), True
    tid = str(found["id"])
    if embedding is not None:
        conn.execute("UPDATE thoughts SET body = %s, metadata = %s, embedding = %s, source_id = %s WHERE id = %s",
                     (body, Jsonb(meta), _vector(embedding), source_id, tid))
    elif found["body"] != body:
        conn.execute("UPDATE thoughts SET body = %s, metadata = %s, embedding = NULL, source_id = %s WHERE id = %s",
                     (body, Jsonb(meta), source_id, tid))
    else:
        conn.execute("UPDATE thoughts SET metadata = %s, source_id = %s WHERE id = %s",
                     (Jsonb(meta), source_id, tid))
    return tid, False


def insert_edge(conn, tenant: str, src_id: str, src_type: str, dst_id: str, dst_type: str, edge_type: str) -> None:
    """Idempotent edge, written to the AGE graph too when the database has AGE."""
    conn.execute(
        """INSERT INTO edges (tenant_id, src_id, src_type, dst_id, dst_type, type, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, 'lab')
           ON CONFLICT (tenant_id, src_id, dst_id, type) DO NOTHING""",
        (tenant, src_id, src_type, dst_id, dst_type, edge_type),
    )
    if getattr(conn, "info_has_age", False):
        from exocortex.db.graph import _age_upsert_edge

        _age_upsert_edge(conn, src_id, src_type, dst_id, dst_type, edge_type,
                         props={"tenant_id": tenant, "created_by": "lab"})
