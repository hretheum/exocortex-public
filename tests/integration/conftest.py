# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Integration-test conftest.

Unlike ``tests/unit/conftest.py`` (which mocks every missing dep so pure-Python
registry tests run with zero infra), integration tests need REAL infrastructure
— a live Postgres+pgvector+AGE instance reachable on ``PG_HOST:PG_PORT``.

If the database is unreachable we skip the whole module rather than fail —
this lets contributors run ``pytest`` locally without spinning up docker, and
keeps the unit-test job in CI fast.  The dedicated ``e2e-smoke`` CI job
explicitly brings the stack up so the skip never triggers there.
"""
from __future__ import annotations

import os

import pytest


def _db_reachable() -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    dsn = os.environ.get("DATABASE_URL") or (
        f"postgresql://{os.environ.get('PG_USER', 'exocortex')}:"
        f"{os.environ.get('PG_PASSWORD', 'exocortex')}@"
        f"{os.environ.get('PG_HOST', 'localhost')}:"
        f"{os.environ.get('PG_PORT', '5432')}/"
        f"{os.environ.get('PG_DATABASE', 'exocortex')}"
    )
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if _db_reachable():
        return
    skip = pytest.mark.skip(
        reason="integration: no reachable Postgres on PG_HOST/PG_PORT — "
        "bring docker-compose up first (`docker compose up -d db`)."
    )
    for item in items:
        item.add_marker(skip)
