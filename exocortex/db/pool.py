# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/db/pool.py — psycopg3 connection pool and query helpers.

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from exocortex.settings import get_database_url
from exocortex.settings import get_tenant_id as _settings_tenant_id

_pool: ConnectionPool | None = None


def _conninfo() -> str:
    # psycopg parses URL strings natively — no need to split into kv pairs.
    # Settings layer raises with an onboarding-friendly hint when unset.
    return get_database_url()


def get_tenant_id() -> str:
    """Return tenant id via pydantic settings (default: ``'default'``).

    Kept as a thin wrapper so existing callers (``from exocortex.db.pool
    import get_tenant_id``) keep working after the TENANT_ID migration.
    """
    return _settings_tenant_id()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_conninfo(),
            min_size=1,
            max_size=5,
            kwargs={'autocommit': True, 'row_factory': dict_row},
            open=True,
        )
    return _pool


@contextmanager
def conn() -> Iterator[Any]:
    """Pooled connection with AGE search_path set per session.

    public comes FIRST — ag_catalog only needs to be somewhere in the path
    for unqualified AGE calls (cypher(), create_graph(), ...) to resolve;
    it does not need to be first. Putting it first was the 2026-07-28
    incident: every unqualified CREATE TABLE in schema/*.sql silently
    landed in ag_catalog instead of public.
    """
    pool = get_pool()
    with pool.connection() as c:
        # AGE's cypher() needs the extension loaded into THIS backend
        # process, not just present in pg_extension — CREATE EXTENSION alone
        # doesn't guarantee it for every pooled connection, and a backend
        # that's never run an AGE statement raises a cryptic
        # "unhandled cypher(cstring) function call" instead of a clear
        # error. LOAD is idempotent (no-op if already loaded), so this is
        # safe to run on every checkout. Found via F33 (vault_note/
        # vault_backlog) hitting it on a freshly created connection pool
        # in local dev.
        c.execute("LOAD 'age'")
        c.execute('SET search_path = public, "$user", ag_catalog')
        yield c


def _adapt_value(v: Any) -> Any:
    """Adapt Python types for psycopg/pgvector."""
    if isinstance(v, dict):
        return Jsonb(v)
    if isinstance(v, list) and v and isinstance(v[0], (float, int)):
        return '[' + ','.join(repr(float(x)) for x in v) + ']'
    return v


def query(sql: str, *params: Any) -> list[dict]:
    with conn() as c:
        adapted = tuple(_adapt_value(p) for p in params)
        return c.execute(sql, adapted).fetchall()


def query_one(sql: str, *params: Any) -> dict | None:
    with conn() as c:
        adapted = tuple(_adapt_value(p) for p in params)
        return c.execute(sql, adapted).fetchone()


def execute(sql: str, *params: Any) -> int:
    with conn() as c:
        adapted = tuple(_adapt_value(p) for p in params)
        return c.execute(sql, adapted).rowcount


def insert_returning(table: str, data: dict, returning: str = '*') -> dict:
    cols = list(data.keys())
    placeholders = ', '.join(['%s'] * len(cols))
    sql = f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({placeholders}) RETURNING {returning}'
    return query_one(sql, *data.values())


def update_where(table: str, data: dict, where_sql: str, *where_params: Any,
                 returning: str | None = None) -> dict | int | None:
    """UPDATE with SET cols and arbitrary WHERE clause."""
    set_clause = ', '.join(f"{k} = %s" for k in data)
    sql = f'UPDATE {table} SET {set_clause} WHERE {where_sql}'
    if returning:
        sql += f' RETURNING {returning}'
        return query_one(sql, *data.values(), *where_params)
    return execute(sql, *data.values(), *where_params)
