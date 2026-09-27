"""Tests for F31.3.4 CockpitAskWorker (G17–G19)."""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest


def _patch_db(pending_rows, log_insert_id='ql-1'):
    """Patch the three db helpers used by the worker.

    Returns (pending_query_mock, execute_mock, query_one_mock).
    """
    query_calls: list[tuple] = []

    def fake_query(sql, *params):
        query_calls.append((sql, params))
        if 'FROM cockpit_actions_pending' in sql:
            return pending_rows
        return []

    execute_calls: list[tuple] = []

    def fake_execute(sql, *params):
        execute_calls.append((sql, params))
        return 1

    query_one_calls: list[tuple] = []

    def fake_query_one(sql, *params):
        query_one_calls.append((sql, params))
        if 'INSERT INTO query_log' in sql:
            return {'id': log_insert_id}
        return None

    return query_calls, execute_calls, query_one_calls, fake_query, fake_execute, fake_query_one


def test_empty_question_is_noop():
    """G19 — empty notion_value → 0 query_log inserts, row marked skipped."""
    pending = [
        {'id': 1, 'audience_name': 'sb', 'page_id': 'p1',
         'property_name': 'Zapytaj mózg', 'notion_value': ''},
        {'id': 2, 'audience_name': 'sb', 'page_id': 'p2',
         'property_name': 'Zapytaj mózg', 'notion_value': '   '},
        {'id': 3, 'audience_name': 'sb', 'page_id': 'p3',
         'property_name': 'Zapytaj mózg', 'notion_value': None},
    ]
    (_, execute_calls, query_one_calls,
     fake_query, fake_execute, fake_query_one) = _patch_db(pending)

    ask_fn_calls: list[str] = []

    def ask_fn(question):
        ask_fn_calls.append(question)
        return {'retrieved_count': 5}

    with patch('exocortex.workers.cockpit_ask.query', side_effect=fake_query), \
         patch('exocortex.workers.cockpit_ask.execute', side_effect=fake_execute), \
         patch('exocortex.workers.cockpit_ask.query_one', side_effect=fake_query_one), \
         patch('exocortex.workers.cockpit_ask.get_tenant_id', return_value='t1'):
        from exocortex.workers.cockpit_ask import CockpitAskWorker
        worker = CockpitAskWorker(ask_fn=ask_fn)
        outcomes = worker.process_pending()

    assert ask_fn_calls == [], 'ask_fn must not be invoked for empty inputs'
    insert_query_log = [c for c in query_one_calls if 'INSERT INTO query_log' in c[0]]
    assert insert_query_log == [], 'no query_log rows should be inserted (G19)'
    assert [o['status'] for o in outcomes] == ['skipped', 'skipped', 'skipped']
    assert all(o['reason'] == 'empty_input' for o in outcomes)
    # 3× UPDATE cockpit_actions_pending → status='skipped'
    assert len(execute_calls) == 3
    assert all('UPDATE cockpit_actions_pending' in c[0] for c in execute_calls)


def test_nonempty_question_writes_query_log():
    """G17/G18 — non-empty value triggers ask_fn + 1 query_log INSERT."""
    pending = [
        {'id': 42, 'audience_name': 'sb', 'page_id': 'pg',
         'property_name': 'Zapytaj mózg', 'notion_value': 'Co Ola mówi o Q3?'},
    ]
    (_, execute_calls, query_one_calls,
     fake_query, fake_execute, fake_query_one) = _patch_db(pending,
                                                           log_insert_id='ql-42')

    asked: list[str] = []

    def ask_fn(question):
        asked.append(question)
        return {'retrieved_count': 7, 'results': []}

    with patch('exocortex.workers.cockpit_ask.query', side_effect=fake_query), \
         patch('exocortex.workers.cockpit_ask.execute', side_effect=fake_execute), \
         patch('exocortex.workers.cockpit_ask.query_one', side_effect=fake_query_one), \
         patch('exocortex.workers.cockpit_ask.get_tenant_id', return_value='t1'):
        from exocortex.workers.cockpit_ask import CockpitAskWorker
        worker = CockpitAskWorker(ask_fn=ask_fn)
        outcomes = worker.process_pending()

    assert asked == ['Co Ola mówi o Q3?']
    inserts = [c for c in query_one_calls if 'INSERT INTO query_log' in c[0]]
    assert len(inserts) == 1, 'exactly one query_log row per non-empty input'
    # tenant_id, question, latency_ms, retrieved_count
    sql, params = inserts[0]
    assert params[0] == 't1'
    assert params[1] == 'Co Ola mówi o Q3?'
    assert isinstance(params[2], int) and params[2] >= 0
    assert params[3] == 7
    assert outcomes[0]['status'] == 'ok'
    assert outcomes[0]['query_log_id'] == 'ql-42'
    assert outcomes[0]['retrieved_count'] == 7
    # row marked 'answered'
    assert any(c[1][0] == 'answered' for c in execute_calls)


def test_worker_importable_and_no_hardcoded_secrets():
    """G17 — worker imports cleanly + 0 hardcoded secrets in source."""
    from exocortex.workers.cockpit_ask import CockpitAskWorker
    assert CockpitAskWorker is not None

    source_path = Path(inspect.getsourcefile(CockpitAskWorker))
    source = source_path.read_text(encoding='utf-8')

    for needle in ('ntn_', 'sk-ant', 'sk-proj'):
        assert needle not in source, f'hardcoded secret pattern {needle!r} found'

    # Worker is a self-contained class; no LLM-provider imports.
    for forbidden in ('import anthropic', 'import openai', 'from anthropic',
                      'from openai'):
        assert forbidden not in source, f'forbidden LLM import: {forbidden}'
