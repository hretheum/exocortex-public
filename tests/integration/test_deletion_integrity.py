# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""zadanie-13 — integracyjne testy schema/40_deletion_integrity.sql.

Runs against a REAL Postgres (see tests/integration/conftest.py — skipped
automatically if PG_HOST/PG_PORT is unreachable), bo trigger PL/pgSQL i CHECK
constraint nie dają się sensownie sfałszować fake-cursorem (jak
tests/unit/test_migrations.py robi dla samego runnera migracji).

Każdy test tworzy własne, unikalne wiersze (uuid w body/run_id) i sprząta po
sobie w bloku finally — baza jest współdzielona (dev/CI), więc testy muszą
być bezpieczne do wielokrotnego i równoległego uruchomienia, nie tylko
jednorazowego."""
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

from psycopg.types.json import Jsonb  # noqa: E402

from exocortex.db import conn, query  # noqa: E402

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


# ─────────────────────── Część 1 — integralność krawędzi ───────────────────


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
    """Brief zadania 13: 'usunięcie myśli zabiera jej krawędzie w obu
    kierunkach — te, w których jest źródłem, i te, w których jest celem'."""
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
    """Część 2: potwierdzenie (nie zmiana) — CASCADE istniał już przed
    zadaniem 13, ta migracja go nie dotyka."""
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


# ─────────────────────── Część 3 — ADR-008: cytat wymagany ─────────────────


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
    """ADR-008 dotyczy wyłącznie treści wygenerowanej przez model — te cztery
    typy są przepisane z plików i nie mają nowego wymogu."""
    tid = _insert_thought(thought_type, f"{thought_type} {uuid.uuid4()}", metadata={})
    assert query("SELECT id FROM thoughts WHERE id = %s", tid)
    _delete_thought(tid)


# ─────────────────────── Część 4 — usuwanie wsadowe przebiegu ──────────────


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
    assert _edge_count(doc) == 0  # trigger posprzątał krawędzie za jednym poleceniem, bez osobnego DELETE FROM edges
    _delete_thought(doc)


# ─────────────────────── Część 2 — semantyka miękkiego usunięcia źródła ────


def test_soft_deleting_source_does_not_touch_thought_chunks_or_edges() -> None:
    """Ratyfikowana decyzja (zadanie 13, część 2): miękkie usunięcie źródła
    (`raw_sources.deleted_at`) zostaje stanem na zawsze — nigdy nie kaskaduje
    do myśli, fragmentów ani krawędzi. Zamierzone od F32
    (schema/33_capture_lifecycle.sql), tu potwierdzone testem zamiast
    pozostawione jako "odrębna sprawa" bez dowodu."""
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
    assert query("SELECT id FROM thoughts WHERE id = %s", doc)  # myśl zostaje
    assert query("SELECT COUNT(*) n FROM thought_chunks WHERE thought_id = %s", doc)[0]["n"] == 1  # fragmenty zostają
    assert _edge_count(doc) == 1  # krawędzie zostają

    _delete_thought(doc)
    _delete_thought(other)
    with conn() as c:
        c.execute("DELETE FROM raw_sources WHERE id = %s", (src,))
