# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Cockpit question → GraphRAGOrchestrator.answer on a real database.

Real cockpit_actions_pending and query_log tables (and the real budget query);
retrieval and the model are stand-ins, so no model is called and nothing is
paid. Each test uses its own tenant so today's budget starts at zero.
"""
from __future__ import annotations

import json
import uuid

import pytest

from tests.lab.conftest import needs_engine

pytestmark = needs_engine


@pytest.fixture()
def cockpit(lab_url, conn, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", lab_url)
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ID", tenant)

    from exocortex import graph_rag

    graph_rag.cache_clear()
    calls: list[str] = []

    def fake_call_llm(question, fused_hits):
        calls.append(question)
        return "Odpowiedź z atrapy.", {"input_tokens": 3500, "output_tokens": 400,
                                       "_cost_usd": 0.0033}

    hits = [{"id": str(uuid.uuid4()), "body": "treść", "metadata": {"title": f"T{i}"}}
            for i in range(3)]
    monkeypatch.setattr(graph_rag, "get_embedding", lambda q: [0.01] * 1024)
    monkeypatch.setattr(graph_rag, "vector_search", lambda *a, **k: hits)
    monkeypatch.setattr(graph_rag, "graph_expand", lambda *a, **k: {})
    monkeypatch.setattr(graph_rag, "call_llm", fake_call_llm)

    marker = uuid.uuid4().hex[:8]
    created: list[int] = []

    def add(question):
        row = conn.execute(
            "INSERT INTO cockpit_actions_pending (audience_name, page_id, property_name,"
            " notion_edited_at, notion_value, dedup_hash)"
            " VALUES ('lab', %s, 'Zapytaj mózg', now(), %s::jsonb, %s) RETURNING id",
            (f"page-{marker}", json.dumps(question), uuid.uuid4().hex),
        ).fetchone()
        created.append(row["id"])
        return row["id"]

    def state(row_id):
        return conn.execute("SELECT status, resolved_value FROM cockpit_actions_pending WHERE id = %s",
                            (row_id,)).fetchone()

    def logged():
        return conn.execute("SELECT question, source, status, retrieval_method, error_reason, latency_ms,"
                            " tokens_in, tokens_out, cost_usd FROM query_log WHERE tenant_id = %s"
                            " ORDER BY asked_at",
                            (tenant,)).fetchall()

    yield add, state, logged, calls, graph_rag
    conn.execute("DELETE FROM cockpit_actions_pending WHERE id = ANY(%s)", (created,))
    conn.execute("DELETE FROM query_log WHERE tenant_id = %s", (tenant,))


def _worker(questions=50, cost=1.00):
    from exocortex.workers.cockpit_ask import AskLimits, CockpitAskWorker

    return CockpitAskWorker(limits=AskLimits(max_questions_per_day=questions,
                                             max_cost_usd_per_day=cost, timeout_s=30))


def test_one_question_one_query_log_row(cockpit):
    add, state, logged, _calls, _ = cockpit
    row_id = add("Co Ola mówi o Q3?")

    outcomes = [o for o in _worker().process_pending() if o["row_id"] == row_id]

    assert outcomes[0]["status"] == "ok"
    rows = logged()
    assert len(rows) == 1
    assert rows[0]["source"] == "notion_cockpit_ask"
    assert rows[0]["retrieval_method"] == "hybrid"
    assert rows[0]["error_reason"] is None
    assert rows[0]["status"] == "logged"
    assert (rows[0]["tokens_in"], rows[0]["tokens_out"]) == (3500, 400)
    assert float(rows[0]["cost_usd"]) == pytest.approx(0.0033)
    assert rows[0]["latency_ms"] is not None
    st = state(row_id)
    assert st["status"] == "answered"
    assert st["resolved_value"]["answer"] == "Odpowiedź z atrapy."
    assert st["resolved_value"]["query_log_id"] == outcomes[0]["query_log_id"]


def test_limit_and_engine_error_on_real_tables(cockpit):
    add, state, logged, calls, graph_rag = cockpit
    first, second = add("Pierwsze pytanie"), add("Drugie pytanie")

    outcomes = {o["row_id"]: o for o in _worker(questions=1).process_pending()}

    assert outcomes[first]["status"] == "ok"
    assert outcomes[second]["code"] == "daily_limit"
    assert state(second)["status"] == "error"
    assert "1/1" in state(second)["resolved_value"]["error"]
    assert len(calls) == 1
    rows = logged()
    assert [r["question"] for r in rows] == ["Pierwsze pytanie", "Drugie pytanie"]
    assert rows[0]["error_reason"] is None
    assert rows[1]["error_reason"].startswith("daily_limit: Dzienny limit pytań z kokpitu wyczerpany: 1/1")
    assert rows[1]["retrieval_method"] is None

    def broken(question, fused_hits):
        raise RuntimeError("no provider configured")

    graph_rag.call_llm = broken  # restored by monkeypatch in the fixture
    third = add("Trzecie pytanie")
    # the rejected question does not use up the budget: one more fits under 2/day
    outcomes = {o["row_id"]: o for o in _worker(questions=2).process_pending()}

    assert outcomes[third]["code"] == "engine_error"
    assert state(third)["status"] == "error"
    rows = logged()
    assert len(rows) == 3
    assert rows[2]["error_reason"] == "RuntimeError: no provider configured"
    assert rows[2]["retrieval_method"] is None
    assert rows[2]["status"] == "logged"
