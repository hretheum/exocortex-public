# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.8.3 — schema migration runner + ``exocortex migrate`` CLI."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fake connection / cursor
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Minimal psycopg-cursor-shaped object backed by an in-memory store."""

    def __init__(self, store: "_FakeStore", connection: "_FakeConnection") -> None:
        self.store = store
        self.connection = connection
        self._last: list[tuple] | tuple | None = None

    def execute(self, sql: str, params=()):  # noqa: ANN001 — duck-typed
        if self.store.fail_on_sql_contains and self.store.fail_on_sql_contains in sql:
            raise RuntimeError(
                f"forced failure on SQL containing {self.store.fail_on_sql_contains!r}"
            )
        sql_strip = sql.strip()
        if sql_strip.startswith("SELECT to_regclass"):
            self._last = [(self.store.table_exists,)]
            return self
        if sql_strip.startswith("SELECT filename, hash FROM exocortex_migrations"):
            self._last = [(fn, h) for fn, h in self.store.applied.items()]
            return self
        if sql_strip.startswith("INSERT INTO exocortex_migrations"):
            fn, h = params
            # Speculative write — recorded in the per-connection pending log so
            # rollback() can undo it. Commit promotes it into store.applied.
            self.connection.pending_inserts.append((fn, h))
            self.store.applied[fn] = h
            self._last = None
            return self
        # Any other SQL — treat as a migration body. If it looks like the
        # bootstrap migration, mark the tracking table as existing.
        if "CREATE TABLE IF NOT EXISTS exocortex_migrations" in sql:
            self.store.table_exists = True
            self.connection.pending_table_create = True
        self.store.executed_sql.append(sql)
        self.connection.pending_executed_sql.append(sql)
        self._last = None
        return self

    def fetchone(self):
        if self._last is None:
            return None
        if isinstance(self._last, list):
            return self._last[0] if self._last else None
        return self._last

    def fetchall(self):
        if self._last is None:
            return []
        if isinstance(self._last, list):
            return list(self._last)
        return [self._last]


class _FakeConnection:
    def __init__(self, store: "_FakeStore") -> None:
        self.store = store
        self.committed = 0
        self.rolled_back = 0
        self.closed = False
        # Per-transaction pending state — promoted to the store on commit(),
        # discarded on rollback() so the test fake actually models atomicity.
        self.pending_inserts: list[tuple[str, str]] = []
        self.pending_executed_sql: list[str] = []
        self.pending_table_create: bool = False
        self._table_existed_at_txn_start: bool = store.table_exists

    def cursor(self):
        return _FakeCursor(self.store, self)

    def commit(self):
        self.committed += 1
        # Pending state has already been written into the store eagerly — a
        # successful commit simply discards the rollback log.
        self.pending_inserts.clear()
        self.pending_executed_sql.clear()
        self.pending_table_create = False
        self._table_existed_at_txn_start = self.store.table_exists

    def rollback(self):
        self.rolled_back += 1
        # Undo speculative inserts.
        for fn, _h in self.pending_inserts:
            self.store.applied.pop(fn, None)
        # Undo executed migration SQL.
        for sql in self.pending_executed_sql:
            try:
                self.store.executed_sql.remove(sql)
            except ValueError:
                pass
        # Undo the table-create if the bootstrap migration was the failing one.
        if self.pending_table_create and not self._table_existed_at_txn_start:
            self.store.table_exists = False
        self.pending_inserts.clear()
        self.pending_executed_sql.clear()
        self.pending_table_create = False

    def close(self):
        self.closed = True


class _FakeStore:
    """Cross-connection state — simulates a persistent database."""

    def __init__(self) -> None:
        self.table_exists: bool = False
        self.applied: dict[str, str] = {}
        self.executed_sql: list[str] = []
        # When set, _FakeCursor.execute() raises RuntimeError whenever the SQL
        # contains this substring — used to exercise the rollback path.
        self.fail_on_sql_contains: str | None = None


def _factory(store: _FakeStore):
    def _make():
        return _FakeConnection(store)
    return _make


# ---------------------------------------------------------------------------
# Schema dir fixture
# ---------------------------------------------------------------------------


def _write(schema_dir: Path, name: str, body: str) -> str:
    p = schema_dir / name
    p.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@pytest.fixture
def schema_dir(tmp_path: Path) -> Path:
    """Tiny synthetic schema directory with bootstrap + two migrations."""
    sd = tmp_path / "schema"
    sd.mkdir()
    _write(
        sd, "00_migrations.sql",
        "CREATE TABLE IF NOT EXISTS exocortex_migrations ("
        "filename text PRIMARY KEY, hash text NOT NULL, "
        "applied_at timestamptz DEFAULT now());",
    )
    _write(sd, "01_one.sql", "-- one")
    _write(sd, "02_two.sql", "-- two")
    # views.sql must be skipped entirely.
    (sd / "views.sql").write_text("CREATE OR REPLACE VIEW v AS SELECT 1;", encoding="utf-8")
    return sd


# ---------------------------------------------------------------------------
# discovery + hashing
# ---------------------------------------------------------------------------


def test_discover_skips_views_sql(schema_dir: Path):
    from exocortex.core.db import migrations as m
    files = m._discover_migrations(schema_dir)
    names = [f.filename for f in files]
    assert names == ["00_migrations.sql", "01_one.sql", "02_two.sql"]


def test_discover_requires_bootstrap_first(tmp_path: Path):
    from exocortex.core.db import migrations as m
    sd = tmp_path / "schema"
    sd.mkdir()
    (sd / "01_oops.sql").write_text("-- no bootstrap", encoding="utf-8")
    with pytest.raises(m.MigrationError, match="00_migrations.sql"):
        m._discover_migrations(sd)


def test_discover_errors_when_schema_dir_missing(tmp_path: Path):
    from exocortex.core.db import migrations as m
    with pytest.raises(m.MigrationError, match="not found"):
        m._discover_migrations(tmp_path / "nope")


def test_hash_is_sha256(schema_dir: Path):
    from exocortex.core.db import migrations as m
    files = m._discover_migrations(schema_dir)
    expected = hashlib.sha256((schema_dir / "01_one.sql").read_bytes()).hexdigest()
    one = next(f for f in files if f.filename == "01_one.sql")
    assert one.sha256 == expected


# ---------------------------------------------------------------------------
# migrate_up
# ---------------------------------------------------------------------------


def test_migrate_up_applies_all_on_empty_db(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_up
    store = _FakeStore()
    applied = migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    assert applied == ["00_migrations.sql", "01_one.sql", "02_two.sql"]
    assert set(store.applied) == set(applied)


def test_migrate_up_second_run_is_noop(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_up
    store = _FakeStore()
    migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    second = migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    assert second == []


def test_migrate_up_picks_up_new_file(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_up
    store = _FakeStore()
    migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))

    # Add a brand new file and ensure only it is applied.
    _write(schema_dir, "03_three.sql", "-- three")
    applied = migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    assert applied == ["03_three.sql"]
    assert "03_three.sql" in store.applied


def test_migrate_up_detects_hash_drift(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_up, MigrationError
    store = _FakeStore()
    migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))

    # Mutate an already-applied file on disk.
    (schema_dir / "01_one.sql").write_text("-- one MUTATED", encoding="utf-8")
    with pytest.raises(MigrationError, match="drift"):
        migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))


def test_migrate_up_drift_blocks_all_new_files(schema_dir: Path):
    """Drift on an applied file blocks even brand new pending files."""
    from exocortex.core.db.migrations import migrate_up, MigrationError
    store = _FakeStore()
    migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))

    # Drift on existing + add new pending file.
    (schema_dir / "02_two.sql").write_text("-- two MUTATED", encoding="utf-8")
    _write(schema_dir, "03_three.sql", "-- three")
    with pytest.raises(MigrationError, match="drift"):
        migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    # The new file MUST NOT have been applied.
    assert "03_three.sql" not in store.applied


def test_migrate_up_dry_run_does_not_write(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_up
    store = _FakeStore()
    applied = migrate_up(
        schema_dir=schema_dir,
        connection_factory=_factory(store),
        dry_run=True,
    )
    assert applied == ["00_migrations.sql", "01_one.sql", "02_two.sql"]
    assert store.applied == {}
    assert store.executed_sql == []  # no SQL bodies sent


# ---------------------------------------------------------------------------
# rollback path
# ---------------------------------------------------------------------------


def test_migrate_up_rolls_back_on_failing_migration(schema_dir: Path):
    """W3: a SQL error during apply must trigger rollback AND leave the store clean."""
    from exocortex.core.db.migrations import migrate_up
    store = _FakeStore()

    # Apply the bootstrap successfully, then force "-- two" to fail.
    # _FakeCursor matches the substring against the executed SQL body.
    store.fail_on_sql_contains = "-- two"

    captured: list[_FakeConnection] = []
    base_factory = _factory(store)

    def tracking_factory():
        conn = base_factory()
        captured.append(conn)
        return conn

    with pytest.raises(RuntimeError, match="forced failure"):
        migrate_up(schema_dir=schema_dir, connection_factory=tracking_factory)

    # Bootstrap + 01_one.sql committed; 02_two.sql failed and was rolled back.
    assert "00_migrations.sql" in store.applied
    assert "01_one.sql" in store.applied
    assert "02_two.sql" not in store.applied, (
        "Failed migration must NOT appear in the applied set"
    )
    # rollback() was invoked exactly once on the single connection used.
    assert len(captured) == 1
    assert captured[0].rolled_back == 1


# ---------------------------------------------------------------------------
# migrate_status
# ---------------------------------------------------------------------------


def test_status_on_empty_db_lists_all_pending(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_status
    store = _FakeStore()
    s = migrate_status(schema_dir=schema_dir, connection_factory=_factory(store))
    assert s.applied == []
    assert s.pending == ["00_migrations.sql", "01_one.sql", "02_two.sql"]
    assert s.drift == []
    assert s.ok is True


def test_status_after_apply_lists_all_applied(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_status, migrate_up
    store = _FakeStore()
    migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    s = migrate_status(schema_dir=schema_dir, connection_factory=_factory(store))
    assert s.applied == ["00_migrations.sql", "01_one.sql", "02_two.sql"]
    assert s.pending == []
    assert s.drift == []


def test_status_surfaces_drift(schema_dir: Path):
    from exocortex.core.db.migrations import migrate_status, migrate_up
    store = _FakeStore()
    migrate_up(schema_dir=schema_dir, connection_factory=_factory(store))
    (schema_dir / "01_one.sql").write_text("-- mutated", encoding="utf-8")
    s = migrate_status(schema_dir=schema_dir, connection_factory=_factory(store))
    assert s.drift == ["01_one.sql"]
    assert s.ok is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_cli(monkeypatch, schema_dir: Path, store: _FakeStore, *args):
    import exocortex.core.db.migrations as m_module
    from exocortex.cli import main

    monkeypatch.setattr(m_module, "_default_connection_factory", _factory(store))
    return main(["migrate", *args, "--schema-dir", str(schema_dir)])


def test_cli_migrate_up_smoke(schema_dir: Path, capsys, monkeypatch):
    store = _FakeStore()
    rc = _run_cli(monkeypatch, schema_dir, store, "up")
    out = capsys.readouterr().out
    assert rc == 0
    assert "applied 3 migration(s)" in out
    assert "00_migrations.sql" in out


def test_cli_migrate_up_second_run_noop(schema_dir: Path, capsys, monkeypatch):
    store = _FakeStore()
    _run_cli(monkeypatch, schema_dir, store, "up")
    capsys.readouterr()  # discard
    rc = _run_cli(monkeypatch, schema_dir, store, "up")
    out = capsys.readouterr().out
    assert rc == 0
    assert "nothing to do" in out


def test_cli_migrate_status_reports_pending_then_applied(schema_dir: Path, capsys, monkeypatch):
    store = _FakeStore()
    rc = _run_cli(monkeypatch, schema_dir, store, "status")
    out = capsys.readouterr().out
    assert rc == 0
    assert "applied: 0" in out
    assert "pending: 3" in out
    # Now apply and re-check.
    _run_cli(monkeypatch, schema_dir, store, "up")
    capsys.readouterr()
    rc2 = _run_cli(monkeypatch, schema_dir, store, "status")
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert "applied: 3" in out2
    assert "pending: 0" in out2


def test_cli_migrate_status_exits_3_on_drift(schema_dir: Path, capsys, monkeypatch):
    store = _FakeStore()
    _run_cli(monkeypatch, schema_dir, store, "up")
    capsys.readouterr()
    (schema_dir / "01_one.sql").write_text("-- mutated", encoding="utf-8")
    rc = _run_cli(monkeypatch, schema_dir, store, "status")
    out = capsys.readouterr().out
    assert rc == 3
    assert "drift" in out


def test_cli_migrate_up_exits_2_on_drift(schema_dir: Path, capsys, monkeypatch):
    store = _FakeStore()
    _run_cli(monkeypatch, schema_dir, store, "up")
    capsys.readouterr()
    (schema_dir / "02_two.sql").write_text("-- mutated", encoding="utf-8")
    rc = _run_cli(monkeypatch, schema_dir, store, "up")
    out = capsys.readouterr().out
    assert rc == 2
    assert "ERROR" in out
    assert "drift" in out.lower()


def test_cli_migrate_up_dry_run(schema_dir: Path, capsys, monkeypatch):
    store = _FakeStore()
    rc = _run_cli(monkeypatch, schema_dir, store, "up", "--dry-run")
    out = capsys.readouterr().out
    assert rc == 0
    assert "would apply" in out
    # Nothing landed in the fake DB.
    assert store.applied == {}


def test_cli_migrate_up_falls_back_to_default_schema_dir(
    schema_dir: Path, capsys, monkeypatch
):
    """W4: ``exocortex migrate up`` without ``--schema-dir`` uses the bundled default."""
    import exocortex.core.db.migrations as m_module
    from exocortex.cli import main

    store = _FakeStore()
    monkeypatch.setattr(m_module, "_default_connection_factory", _factory(store))
    monkeypatch.setattr(m_module, "_DEFAULT_SCHEMA_DIR", schema_dir)

    rc = main(["migrate", "up"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "applied 3 migration(s)" in out


def test_cli_migrate_status_falls_back_to_default_schema_dir(
    schema_dir: Path, capsys, monkeypatch
):
    """W4: ``exocortex migrate status`` without ``--schema-dir`` uses the bundled default."""
    import exocortex.core.db.migrations as m_module
    from exocortex.cli import main

    store = _FakeStore()
    monkeypatch.setattr(m_module, "_default_connection_factory", _factory(store))
    monkeypatch.setattr(m_module, "_DEFAULT_SCHEMA_DIR", schema_dir)

    rc = main(["migrate", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pending: 3" in out


# ---------------------------------------------------------------------------
# Real repo wiring
# ---------------------------------------------------------------------------


def test_repo_schema_dir_contains_bootstrap_first():
    """Sanity: the repo's actual schema/ has 00_migrations.sql first."""
    from exocortex.core.db.migrations import _discover_migrations, _schema_dir_default
    files = _discover_migrations(_schema_dir_default())
    assert files[0].filename == "00_migrations.sql"


def test_repo_schema_dir_has_no_globex_filenames():
    """F31.8.3 acceptance: zero GLOBEX-specific files left in the public schema dir."""
    from exocortex.core.db.migrations import _schema_dir_default
    for p in _schema_dir_default().iterdir():
        if p.suffix == ".sql":
            assert "globex" not in p.name.lower(), f"GLOBEX-specific file left: {p.name}"


def test_repo_schema_dir_files_have_no_eryk_attribution():
    """F31.8 acceptance: every shipped schema file is neutrally attributed."""
    from exocortex.core.db.migrations import _schema_dir_default
    sd = _schema_dir_default()
    leakers: list[str] = []
    for p in sorted(sd.glob("*.sql")):
        body = p.read_text(encoding="utf-8")
        if "Alex" in body or "Orłowski" in body or "Orlowski" in body:
            leakers.append(p.name)
    assert leakers == [], (
        "Personal attribution leaked into schema files (move to ATTRIBUTION.md): "
        f"{leakers}"
    )
