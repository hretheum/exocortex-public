"""Tests for F31.3.4 CockpitAskWorker → GraphRAGOrchestrator.answer.

No real model and no database: the model is a stand-in (`fake_call_llm`) and
every SQL statement goes to an in-memory recorder (`FakeDb`). The same path on
a real Postgres is covered by tests/lab/test_cockpit_ask_db.py.
"""
from __future__ import annotations

import inspect
import os
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

os.environ.setdefault('TENANT_ID', '00000000-0000-0000-0000-000000000001')

from exocortex import graph_rag
from exocortex.graph_rag import Answer, Source
from exocortex.workers.cockpit_ask import (
    QUERY_SOURCE,
    AskLimits,
    CockpitAskWorker,
)

LIMITS = AskLimits(max_questions_per_day=20, max_cost_usd_per_day=0.25, timeout_s=5)

# DeepInfra Qwen pricing from config/llm_routing.yaml (the route F5_graphrag
# falls into via second_brain.*), USD per Mtok.
PRICE_IN, PRICE_OUT = 0.54, 3.40


class FakeDb:
    """Records SQL; answers the pending-rows and today's-usage queries."""

    def __init__(self, pending: list[dict[str, Any]]) -> None:
        self.pending = pending
        self.query_log: list[dict[str, Any]] = []
        self.marks: list[tuple[str, Any, Any]] = []  # (status, resolved_value, row_id)

    def query(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        assert 'FROM cockpit_actions_pending' in sql
        return self.pending

    def execute(self, sql: str, *params: Any) -> int:
        assert 'UPDATE cockpit_actions_pending' in sql
        self.marks.append(params)
        return 1

    def query_one(self, sql: str, *params: Any) -> dict[str, Any] | None:
        if 'INSERT INTO query_log' in sql:
            cols = [c.strip() for c in sql.split('(', 1)[1].split(')', 1)[0].split(',')]
            self.query_log.append(dict(zip(cols, params, strict=True)))
            return {'id': f'ql-{len(self.query_log)}'}
        if 'FROM query_log' in sql:
            tenant, source = params
            rows = [r for r in self.query_log if r['source'] == source and r['tenant_id'] == tenant]
            return {'questions': len(rows),
                    'cost_usd': sum(r['cost_usd'] or 0 for r in rows)}
        raise AssertionError(f'unexpected SQL: {sql}')

    def statuses(self) -> list[str]:
        return [m[0] for m in self.marks]


def _row(row_id: int, value: Any) -> dict[str, Any]:
    return {'id': row_id, 'audience_name': 'sb', 'page_id': f'p{row_id}',
            'property_name': 'Zapytaj mózg', 'notion_value': value}


def _hits(n: int = 8) -> list[dict[str, Any]]:
    return [{'id': f'{i:08d}-0000-0000-0000-000000000000',
             'body': 'Notatka o planach na Q3. ' * 60,  # > 1500 chars, prompt truncates
             'metadata': {'title': f'Notatka {i}'}, 'thought_type': 'note', 'sim': 0.9 - i / 100}
            for i in range(n)]


model_calls: list[str] = []


def fake_call_llm(question: str, fused_hits: list[dict]) -> tuple[str, dict]:
    """Model stand-in: token counts from the real prompts (chars / 4, as
    tests/fakes/fake_llm_server.py), cost from the routed provider's pricing."""
    model_calls.append(question)
    prompt = graph_rag.build_system_prompt() + graph_rag._build_user_prompt(question, fused_hits)
    tokens_in, tokens_out = len(prompt) // 4, 400
    return 'Odpowiedź: [[notatka-0]] mówi o Q3.', {
        'input_tokens': tokens_in, 'output_tokens': tokens_out,
        'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0,
        '_cost_usd': (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1_000_000,
    }


@pytest.fixture()
def engine(monkeypatch):
    """Real GraphRAGOrchestrator.answer with retrieval and the model stubbed."""
    graph_rag.cache_clear()
    model_calls.clear()
    monkeypatch.setattr(graph_rag, 'get_embedding', lambda q: [0.1] * 8)
    monkeypatch.setattr(graph_rag, 'vector_search', lambda *a, **k: _hits())
    monkeypatch.setattr(graph_rag, 'graph_expand', lambda *a, **k: {})
    monkeypatch.setattr(graph_rag, 'call_llm', fake_call_llm)
    return monkeypatch


def _run(db: FakeDb, *, limits: AskLimits = LIMITS, ask_fn=None) -> list[dict[str, Any]]:
    with patch('exocortex.workers.cockpit_ask.query', side_effect=db.query), \
         patch('exocortex.workers.cockpit_ask.execute', side_effect=db.execute), \
         patch('exocortex.workers.cockpit_ask.query_one', side_effect=db.query_one), \
         patch('exocortex.db.query_one', side_effect=db.query_one):
        return CockpitAskWorker(ask_fn=ask_fn, limits=limits).process_pending()


# ── answers ──────────────────────────────────────────────────────────────────

def test_question_gets_graph_rag_answer_and_one_query_log_row(engine):
    db = FakeDb([_row(42, 'Co Ola mówi o Q3?')])
    outcomes = _run(db)

    assert model_calls == ['Co Ola mówi o Q3?']
    assert len(db.query_log) == 1, 'one cockpit question = one query_log row'
    logged = db.query_log[0]
    assert logged['source'] == QUERY_SOURCE
    assert logged['question'] == 'Co Ola mówi o Q3?'
    assert logged['retrieval_method'] == 'hybrid'
    assert logged['cost_usd'] > 0 and logged['tokens_in'] > 0 and logged['tokens_out'] == 400
    assert isinstance(logged['latency_ms'], int)

    assert outcomes == [{'row_id': 42, 'status': 'ok', 'query_log_id': 'ql-1',
                         'latency_ms': logged['latency_ms'], 'cost_usd': logged['cost_usd'],
                         'retrieved_count': 8}]
    status, resolved, row_id = db.marks[0]
    assert (status, row_id) == ('answered', 42)
    assert '"answer": "Odpowiedź: [[notatka-0]] mówi o Q3."' in resolved
    assert '"query_log_id": "ql-1"' in resolved


def test_cache_hit_still_one_row_per_question(engine):
    db = FakeDb([_row(1, 'Co Ola mówi o Q3?'), _row(2, 'Co Ola mówi o Q3?')])
    outcomes = _run(db)

    assert [o['status'] for o in outcomes] == ['ok', 'ok']
    assert len(model_calls) == 1, 'second question is a cache hit'
    assert [r['retrieval_method'] for r in db.query_log] == ['hybrid', 'cache']
    assert db.query_log[1]['cost_usd'] == 0.0


def test_worker_does_not_write_query_log_itself():
    """The orchestrator is the only query_log writer; the worker only reads it."""
    source = Path(inspect.getsourcefile(CockpitAskWorker)).read_text(encoding='utf-8')
    assert 'INSERT INTO query_log' not in source
    assert 'log_query' not in source


# ── engine errors → status='error', never an exception ───────────────────────

def test_model_error_is_status_error_with_one_query_log_row(engine):
    def broken_llm(question, fused_hits):
        raise RuntimeError('all providers failed: ANTHROPIC_API_KEY not set')

    engine.setattr(graph_rag, 'call_llm', broken_llm)
    db = FakeDb([_row(7, 'Pytanie bez modelu')])
    outcomes = _run(db)

    assert outcomes[0]['status'] == 'error'
    assert outcomes[0]['code'] == 'engine_error'
    assert 'ANTHROPIC_API_KEY not set' in outcomes[0]['reason']
    assert db.statuses() == ['error']
    assert '"code": "engine_error"' in db.marks[0][1]
    assert len(db.query_log) == 1, 'a failed question is still exactly one row'
    assert db.query_log[0]['retrieval_method'] == 'error'


def test_embedding_failure_is_status_error(engine):
    engine.setattr(graph_rag, 'get_embedding', lambda q: None)
    db = FakeDb([_row(8, 'Pytanie')])
    outcomes = _run(db)

    assert outcomes[0]['status'] == 'error'
    assert 'embedding failed' in outcomes[0]['reason']
    assert model_calls == []
    assert len(db.query_log) == 1


def test_timeout_is_status_error():
    release = threading.Event()

    def slow_ask(question):
        release.wait(5)
        raise AssertionError('unreachable in this test')

    db = FakeDb([_row(9, 'Wolne pytanie')])
    try:
        outcomes = _run(db, ask_fn=slow_ask,
                        limits=AskLimits(max_questions_per_day=5, max_cost_usd_per_day=1, timeout_s=0.05))
    finally:
        release.set()

    assert outcomes[0]['status'] == 'error'
    assert outcomes[0]['code'] == 'timeout'
    assert '0.05 s' in outcomes[0]['reason']
    assert db.statuses() == ['error']


# ── daily limit ──────────────────────────────────────────────────────────────

def test_question_limit_stops_answering(engine):
    db = FakeDb([_row(i, f'Pytanie {i}') for i in range(1, 5)])
    outcomes = _run(db, limits=AskLimits(max_questions_per_day=2, max_cost_usd_per_day=10, timeout_s=5))

    assert [o['status'] for o in outcomes] == ['ok', 'ok', 'error', 'error']
    assert {o.get('code') for o in outcomes[2:]} == {'daily_limit'}
    assert 'Dzienny limit pytań z kokpitu wyczerpany: 2/2' in outcomes[2]['reason']
    assert len(model_calls) == 2, 'no model call after the limit'
    assert len(db.query_log) == 2


def test_cost_limit_stops_answering(engine):
    db = FakeDb([_row(i, f'Pytanie {i}') for i in range(1, 4)])
    # one answer costs a few tenths of a cent on the stand-in; a tiny budget is gone after one
    outcomes = _run(db, limits=AskLimits(max_questions_per_day=100, max_cost_usd_per_day=0.0001,
                                         timeout_s=5))

    assert [o['status'] for o in outcomes] == ['ok', 'error', 'error']
    assert outcomes[1]['code'] == 'daily_limit'
    assert 'limit kosztu' in outcomes[1]['reason']
    assert len(model_calls) == 1


def test_zero_limit_disables_questions(engine):
    db = FakeDb([_row(1, 'Pytanie')])
    outcomes = _run(db, limits=AskLimits(max_questions_per_day=0, max_cost_usd_per_day=1, timeout_s=5))

    assert outcomes[0]['code'] == 'daily_limit'
    assert model_calls == [] and db.query_log == []


def test_limits_default_from_settings(monkeypatch, tmp_path):
    from exocortex.settings import reset_settings

    monkeypatch.setenv('EXOCORTEX_VAULT_PATH', str(tmp_path))
    monkeypatch.delenv('EXOCORTEX_COCKPIT_ASK_MAX_QUESTIONS_PER_DAY', raising=False)
    monkeypatch.setenv('EXOCORTEX_COCKPIT_ASK_MAX_COST_USD_PER_DAY', '0.10')
    reset_settings()
    try:
        limits = AskLimits.from_settings()
    finally:
        reset_settings()
    assert limits == AskLimits(max_questions_per_day=20, max_cost_usd_per_day=0.10, timeout_s=120.0)


# ── unchanged guardrails (G17–G19) ───────────────────────────────────────────

def test_empty_question_is_noop():
    """G19 — empty notion_value → 0 query_log rows, no budget read, row skipped."""
    db = FakeDb([_row(1, ''), _row(2, '   '), _row(3, None), _row(4, [])])
    asked: list[str] = []

    def ask_fn(question):
        asked.append(question)
        return Answer(question=question, response='x', sources=[], cost_usd=0, latency_ms=0)

    outcomes = _run(db, ask_fn=ask_fn)

    assert asked == []
    assert db.query_log == []
    assert [o['status'] for o in outcomes] == ['skipped'] * 4
    assert all(o['reason'] == 'empty_input' for o in outcomes)
    assert db.statuses() == ['skipped'] * 4


def test_custom_ask_fn_answer_is_stored():
    db = FakeDb([_row(5, 'Pytanie')])

    def ask_fn(question):
        return Answer(question=question, response='Tak.', cost_usd=0.001, latency_ms=12,
                      sources=[Source(thought_id='t1', title='T', body_excerpt='', score=1.0)],
                      query_log_id='ql-x')

    outcomes = _run(db, ask_fn=ask_fn)
    assert outcomes[0] == {'row_id': 5, 'status': 'ok', 'query_log_id': 'ql-x',
                           'latency_ms': 12, 'cost_usd': 0.001, 'retrieved_count': 1}


def test_worker_importable_and_no_hardcoded_secrets():
    """G17 — worker imports cleanly + 0 hardcoded secrets in source."""
    source = Path(inspect.getsourcefile(CockpitAskWorker)).read_text(encoding='utf-8')

    for needle in ('ntn_', 'sk-ant', 'sk-proj'):
        assert needle not in source, f'hardcoded secret pattern {needle!r} found'

    for forbidden in ('import anthropic', 'import openai', 'from anthropic',
                      'from openai'):
        assert forbidden not in source, f'forbidden LLM import: {forbidden}'
