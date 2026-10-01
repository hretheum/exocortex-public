# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Integration tests for schema/40_deletion_integrity.sql.

Runs against a REAL Postgres (see tests/integration/conftest.py — skipped
automatically if PG_HOST/PG_PORT is unreachable), because a PL/pgSQL trigger
and a CHECK constraint cannot be meaningfully faked with a fake cursor (as
tests/unit/test_migrations.py does for the migration runner alone).

Each test creates its own unique rows (uuid in body/run_id) and cleans up
after itself in a finally block — the database is shared (dev/CI), so tests
must be safe to run repeatedly and in parallel, not just once."""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    f"postgresql://{os.environ.get('PG_USER', 'exocortex')}:"
    f"{os.environ.get('PG_PASSWORD', 'exocortex')}@"
    f"{os.environ.get('PG_HOST', 'localhost')}:"
    f"{os.environ.get('PG_PORT', '5432')}/"
    f"{os.environ.get('PG_DATABASE', 'exocortex')}",
)

from psycopg.types.json import Jsonb

from exocortex.db import conn, query

TENANT_ID = "00000000-0000-0000-0000-000000000001"


def _insert_thought(thought_type: str, body: str, metadata: dict | None = None) -> str:
    with conn() as c:
        row = c.execute(
            "INSERT INTO thoughts (tenant_id, body, thought_type, metadata) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (TENANT_ID, body, thought_type, Jsonb(metadata or {})),
        ).fetchone()
        return str(row["id"])


def _insert_edge(src_id: str, dst_id: str, edge_type: str = "related_to") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO edges (tenant_id, src_id, src_type, dst_id, dst_type, type) "
            "VALUES (%s, %s, 'thought', %s, 'thought', %s)",
            (TENANT_ID, src_id, dst_id, edge_type),
        )


def _edge_count(thought_id: str) -> int:
    return query(
        "SELECT COUNT(*) n FROM edges WHERE src_id = %s OR dst_id = %s",
        thought_id, thought_id,
    )[0]["n"]


def _delete_thought(thought_id: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM thoughts WHERE id = %s", (thought_id,))


# ─────────────────────── Part 1 — edge integrity ───────────────────────────


def test_delete_removes_edges_where_thought_is_src() -> None:
    a = _insert_thought("generic", f"src {uuid.uuid4()}")
    b = _insert_thought("generic", f"dst {uuid.uuid4()}")
    _insert_edge(a, b)
    assert _edge_count(a) == 1
    _delete_thought(a)
    assert _edge_count(a) == 0
    _delete_thought(b)


def test_delete_removes_edges_where_thought_is_dst() -> None:
    a = _insert_thought("generic", f"src {uuid.uuid4()}")
    b = _insert_thought("generic", f"dst {uuid.uuid4()}")
    _insert_edge(a, b)
    assert _edge_count(b) == 1
    _delete_thought(b)
    assert _edge_count(b) == 0
    _delete_thought(a)


def test_delete_removes_edges_in_both_directions_at_once() -> None:
    """Deleting a thought removes its edges in both directions — those where
    it is the source and those where it is the target."""
    a = _insert_thought("generic", f"a {uuid.uuid4()}")
    b = _insert_thought("generic", f"b {uuid.uuid4()}")
    _insert_edge(a, b)  # a -> b
    _insert_edge(b, a)  # b -> a
    assert _edge_count(a) == 2
    _delete_thought(a)
    assert _edge_count(a) == 0
    assert _edge_count(b) == 0
    _delete_thought(b)


def test_thought_chunks_still_cascade() -> None:
    """Part 2: a confirmation (not a change) — the CASCADE already existed
    before this migration, which does not touch it."""
    doc = _insert_thought("vault_note", f"doc {uuid.uuid4()}")
    with conn() as c:
        c.execute(
            "INSERT INTO thought_chunks (tenant_id, thought_id, chunk_index, body) "
            "VALUES (%s, %s, 0, 'chunk')",
            (TENANT_ID, doc),
        )
    before = query("SELECT COUNT(*) n FROM thought_chunks WHERE thought_id = %s", doc)[0]["n"]
    assert before == 1
    _delete_thought(doc)
    after = query("SELECT COUNT(*) n FROM thought_chunks WHERE thought_id = %s", doc)[0]["n"]
    assert after == 0


# ─────────────────────── Part 3 — ADR-008: quote required ──────────────────


def test_claim_without_quote_is_rejected() -> None:
    with pytest.raises(Exception, match="chk_claim_requires_quote"):
        _insert_thought("claim", f"claim {uuid.uuid4()}", metadata={})


def test_claim_with_empty_quote_is_rejected() -> None:
    with pytest.raises(Exception, match="chk_claim_requires_quote"):
        _insert_thought("claim", f"claim {uuid.uuid4()}", metadata={"quote": ""})


def test_claim_with_quote_is_accepted() -> None:
    cid = _insert_thought("claim", f"claim {uuid.uuid4()}", metadata={"quote": "zrodlowy fragment"})
    assert query("SELECT id FROM thoughts WHERE id = %s", cid)
    _delete_thought(cid)


@pytest.mark.parametrize("thought_type", ["vault_note", "backlog_item", "recipe", "work_meeting_note"])
def test_non_claim_types_do_not_require_quote(thought_type: str) -> None:
    """ADR-008 applies only to model-generated content — these four
    types are copied from files and get no new requirement."""
    tid = _insert_thought(thought_type, f"{thought_type} {uuid.uuid4()}", metadata={})
    assert query("SELECT id FROM thoughts WHERE id = %s", tid)
    _delete_thought(tid)


# ─────────────────────── Part 4 — batch deletion of a run ─────────────────


def test_batch_delete_by_run_id_leaves_no_orphans() -> None:
    run_id = f"run-{uuid.uuid4()}"
    doc = _insert_thought("vault_note", f"doc for {run_id}")
    claim_ids = [
        _insert_thought("claim", f"claim {i} for {run_id}", metadata={"run_id": run_id, "quote": f"q{i}"})
        for i in range(3)
    ]
    for cid in claim_ids:
        _insert_edge(cid, doc, edge_type="derived_from")

    assert query(
        "SELECT COUNT(*) n FROM thoughts WHERE thought_type='claim' AND metadata->>'run_id'=%s", run_id,
    )[0]["n"] == 3
    assert _edge_count(doc) == 3

    with conn() as c:
        c.execute(
            "DELETE FROM thoughts WHERE thought_type='claim' AND metadata->>'run_id'=%s", (run_id,),
        )

    assert query(
        "SELECT COUNT(*) n FROM thoughts WHERE thought_type='claim' AND metadata->>'run_id'=%s", run_id,
    )[0]["n"] == 0
    assert _edge_count(doc) == 0  # the trigger cleaned up the edges in one statement, no separate DELETE FROM edges
    _delete_thought(doc)


# ─────────────────────── Part 2 — soft-delete semantics of a source ───────


def test_soft_deleting_source_does_not_touch_thought_chunks_or_edges() -> None:
    """Ratified decision (part 2): a soft delete of a source
    (`raw_sources.deleted_at`) remains a state forever — it never cascades
    to thoughts, fragments or edges. Intended since F32
    (schema/33_capture_lifecycle.sql); confirmed here by a test instead of
    being left as a "separate issue" without proof."""
    with conn() as c:
        src = c.execute(
            "INSERT INTO raw_sources (tenant_id, uri, source_type) VALUES (%s, %s, %s) RETURNING id",
            (TENANT_ID, f"file:///tmp/deletion-integrity-{uuid.uuid4()}.md", "quick-note"),
        ).fetchone()["id"]
        doc = c.execute(
            "INSERT INTO thoughts (tenant_id, body, thought_type, source_id) "
            "VALUES (%s, %s, 'vault_note', %s) RETURNING id",
            (TENANT_ID, f"doc with source {uuid.uuid4()}", src),
        ).fetchone()["id"]
        c.execute(
            "INSERT INTO thought_chunks (tenant_id, thought_id, chunk_index, body) "
            "VALUES (%s, %s, 0, 'chunk')",
            (TENANT_ID, doc),
        )
    other = _insert_thought("generic", f"other {uuid.uuid4()}")
    _insert_edge(doc, other)

    with conn() as c:
        c.execute("UPDATE raw_sources SET deleted_at = NOW() WHERE id = %s", (src,))

    assert query("SELECT deleted_at FROM raw_sources WHERE id = %s", src)[0]["deleted_at"] is not None
    assert query("SELECT id FROM thoughts WHERE id = %s", doc)  # thought stays
    assert query("SELECT COUNT(*) n FROM thought_chunks WHERE thought_id = %s", doc)[0]["n"] == 1  # fragments stay
    assert _edge_count(doc) == 1  # edges stay

    _delete_thought(doc)
    _delete_thought(other)
    with conn() as c:
        c.execute("DELETE FROM raw_sources WHERE id = %s", (src,))
