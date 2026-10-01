"""Shared fake `conn()` context manager for vault_note/vault_backlog tests.

Both processors use the `with conn() as c: c.execute(sql, params).fetchone()`
pattern directly (not the query()/query_one() module functions test_cockpit_
action.py mocks) — this fakes just enough of that surface to exercise real
INSERT-then-UPDATE idempotency without a real Postgres connection.
"""
from __future__ import annotations

import itertools


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConn:
    """In-memory stand-in for a psycopg connection, scoped to one `thoughts`
    table. Recognizes exactly the SQL shapes vault_note.py / vault_backlog.py
    emit — SELECT id ... LIMIT 1, INSERT ... RETURNING id, UPDATE ... WHERE
    id = %s. Everything else (edges, entities) is a no-op recorded in
    `.calls` for assertions.
    """

    _id_counter = itertools.count(1)

    def __init__(self, existing_rows: dict[tuple, str] | None = None):
        # key -> thought_id, mimicking what a SELECT would find already there.
        self.existing_rows = dict(existing_rows or {})
        self.inserted: dict[str, dict] = {}
        self.updated: dict[str, dict] = {}
        self.calls: list[tuple[str, tuple]] = []
        # thought_chunks: list of (tenant_id, thought_id, chunk_index, heading, body, embedding)
        self.chunk_inserts: list[tuple] = []
        self.chunk_deletes: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        s = sql.strip()

        if s.startswith('SELECT id FROM thoughts'):
            key = self._select_key(sql, params)
            tid = self.existing_rows.get(key)
            return _FakeResult({'id': tid} if tid else None)

        if s.startswith('INSERT INTO thoughts'):
            tid = f'thought-{next(self._id_counter)}'
            self.inserted[tid] = {'sql': sql, 'params': params}
            # Register it so a second process() call in the same test session
            # (simulating a re-run against the same backing store) finds it.
            return _FakeResult({'id': tid})

        if s.startswith('UPDATE thoughts'):
            tid = params[-1]
            self.updated[tid] = {'sql': sql, 'params': params}
            return _FakeResult(None)

        if s.startswith('DELETE FROM thought_chunks'):
            thought_id = params[0]
            self.chunk_deletes.append(thought_id)
            self.chunk_inserts = [row for row in self.chunk_inserts if row[1] != thought_id]
            return _FakeResult(None)

        if s.startswith('INSERT INTO thought_chunks'):
            self.chunk_inserts.append(params)
            return _FakeResult(None)

        return _FakeResult(None)

    @staticmethod
    def _select_key(sql, params):
        # vault_note: (tenant, source_id, chunk_index) — params = (tenant, source_id, chunk_index)
        # vault_backlog: (tenant, source_id) — params = (tenant, source_id)
        if "chunk_index" in sql:
            return ('chunk', params[0], params[1], params[2])
        return ('single', params[0], params[1])
