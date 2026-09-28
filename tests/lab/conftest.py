# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Lab tests against a real Postgres.

LAB_TEST_DATABASE_URL names the database; without it the database tests
are skipped. With LAB_TEST_ENGINE_SCHEMA=1 the database already has every
migration (CI runs `exocortex migrate up`); otherwise only the lab's own
tables (schema/*_lab_*.sql) are applied, which is enough for everything
that does not touch the engine's graph.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("LAB_TEST_DATABASE_URL")
ENGINE = os.environ.get("LAB_TEST_ENGINE_SCHEMA") == "1"

needs_engine = pytest.mark.skipif(not ENGINE, reason="needs the engine schema (LAB_TEST_ENGINE_SCHEMA=1)")


@pytest.fixture(scope="session")
def lab_url():
    if not URL:
        pytest.skip("LAB_TEST_DATABASE_URL is not set")
    if not ENGINE:
        import psycopg

        with psycopg.connect(URL, autocommit=True) as c:
            for f in sorted((ROOT / "schema").glob("*_lab_*.sql")):
                c.execute(f.read_text(encoding="utf-8"))
    return URL


@pytest.fixture()
def conn(lab_url):
    from exocortex.lab.db import connect

    c = connect(lab_url)
    yield c
    c.close()


@pytest.fixture()
def slug():
    """A fresh experiment slug per test, so tests never share rows."""
    return "t-" + uuid.uuid4().hex[:10]


@pytest.fixture()
def tenant(monkeypatch):
    t = "00000000-0000-0000-0000-00000000100b"
    monkeypatch.setenv("TENANT_ID", t)
    return t
