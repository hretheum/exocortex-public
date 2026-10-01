# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.8.3 — schema migration runner.

Applies ``schema/*.sql`` files in lexicographic order against a Postgres
database and records the result in the ``exocortex_migrations`` tracking
table.  Idempotent: a second run is a no-op when file hashes match.  A
mismatched hash raises :class:`MigrationError` so an operator cannot
silently mutate already-applied schema.

Public surface
--------------
* :func:`migrate_up`   — apply all pending migrations.
* :func:`migrate_status` — return ``(applied, pending, drift)`` lists.
* :class:`MigrationError` — raised on any unrecoverable problem.

The runner is intentionally decoupled from :mod:`exocortex.db.pool` so it
can run before the application pool is initialised (and so unit tests can
inject a fake connection factory).
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


_BOOTSTRAP_FILENAME = "00_migrations.sql"


def _resolve_default_schema_dir() -> Path:
    """Locate the SQL migrations shipped with this install.

    Order:
      1. ``<repo_root>/schema``         — dev checkout / editable install.
      2. ``<package>/_bundled/schema``  — pip-installed wheel; ``schema/``
         doesn't exist next to ``site-packages``, so we fall back to the
         copy bundled inside the package data (see ``pyproject.toml`` and
         ``scripts/sync_bundled.py``).

    Returning a path even when neither exists keeps callers' error messages
    honest — ``_discover_migrations`` raises with the resolved path.
    """
    # parents[3] = repo root for an editable install:
    #   <root>/exocortex/core/db/migrations.py
    repo_layout = Path(__file__).resolve().parents[3] / "schema"
    if repo_layout.is_dir():
        return repo_layout
    bundled = Path(__file__).resolve().parents[2] / "_bundled" / "schema"
    if bundled.is_dir():
        return bundled
    # Stable default for error reporting — points at the layout we recommend.
    return repo_layout


_DEFAULT_SCHEMA_DIR = _resolve_default_schema_dir()


class MigrationError(RuntimeError):
    """Raised for any unrecoverable migration condition."""


@dataclasses.dataclass(frozen=True)
class MigrationFile:
    """Lightweight DTO describing one file on disk.

    ``content`` is captured at discovery time alongside ``sha256`` so the same
    bytes that produced the hash are executed against the database — closes a
    TOCTOU window where the file could be edited between hashing and apply.
    """

    path: Path
    sha256: str
    content: str

    @property
    def filename(self) -> str:
        return self.path.name


@dataclasses.dataclass(frozen=True)
class MigrationStatus:
    """Result of :func:`migrate_status`."""

    applied: list[str]    # filenames applied AND hash matches the file on disk
    pending: list[str]    # files on disk not yet in the tracking table
    drift: list[str]      # filenames applied but on-disk hash differs

    @property
    def ok(self) -> bool:
        return not self.drift


# ---------------------------------------------------------------------------
# Connection abstraction
# ---------------------------------------------------------------------------


class _Cursorish(Protocol):  # pragma: no cover — typing only
    def execute(self, sql: str, params: Iterable | None = ...) -> object: ...
    def fetchone(self) -> tuple | None: ...
    def fetchall(self) -> list[tuple]: ...


class _Connish(Protocol):  # pragma: no cover — typing only
    def cursor(self) -> _Cursorish: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[], _Connish]


def _default_connection_factory() -> _Connish:
    """Build a fresh psycopg connection from the same env vars as ``exocortex.db``.

    Lazy import keeps the module test-friendly: unit tests can inject a stub
    factory and avoid pulling psycopg in at all.
    """
    import psycopg  # local import: heavy dep

    from exocortex.db.pool import _conninfo  # reuses env-var contract

    # autocommit=False — each migration runs as one explicit transaction.
    return psycopg.connect(_conninfo(), autocommit=False)


# ---------------------------------------------------------------------------
# File discovery + hashing
# ---------------------------------------------------------------------------


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _discover_migrations(schema_dir: Path) -> list[MigrationFile]:
    """Return every ``*.sql`` file under *schema_dir* sorted lexicographically.

    ``views.sql`` is excluded from migration tracking — it is intentionally
    re-applicable (idempotent CREATE OR REPLACE VIEW statements) and is
    applied by a separate command in the runbook.
    """
    if not schema_dir.is_dir():
        raise MigrationError(f"Schema directory not found: {schema_dir}")

    files: list[MigrationFile] = []
    for entry in sorted(schema_dir.iterdir()):
        if entry.suffix != ".sql":
            continue
        if entry.name == "views.sql":
            continue
        text = entry.read_text(encoding="utf-8")
        files.append(
            MigrationFile(path=entry, sha256=_hash_text(text), content=text)
        )

    if not files or files[0].filename != _BOOTSTRAP_FILENAME:
        raise MigrationError(
            f"First migration must be {_BOOTSTRAP_FILENAME!r} (creates the tracking "
            f"table). Found: {[f.filename for f in files[:3]]}"
        )
    return files


# ---------------------------------------------------------------------------
# Tracking-table helpers
# ---------------------------------------------------------------------------


_TRACKING_TABLE_EXISTS_SQL = (
    "SELECT to_regclass('public.exocortex_migrations') IS NOT NULL AS exists_"
)
_FETCH_APPLIED_SQL = "SELECT filename, hash FROM exocortex_migrations"
_INSERT_LOG_SQL = (
    "INSERT INTO exocortex_migrations (filename, hash) VALUES (%s, %s)"
    " ON CONFLICT (filename) DO NOTHING"
)


def _tracking_table_exists(cursor: _Cursorish) -> bool:
    cursor.execute(_TRACKING_TABLE_EXISTS_SQL, ())
    row = cursor.fetchone()
    if row is None:
        return False
    # tuple (False) or dict-style — handle both for test stubs.
    return bool(row[0]) if not isinstance(row, dict) else bool(next(iter(row.values())))


def _fetch_applied(cursor: _Cursorish) -> dict[str, str]:
    cursor.execute(_FETCH_APPLIED_SQL, ())
    rows = cursor.fetchall()
    out: dict[str, str] = {}
    for r in rows:
        if isinstance(r, dict):
            out[r["filename"]] = r["hash"]
        else:
            out[r[0]] = r[1]
    return out


# ---------------------------------------------------------------------------
# Apply / status
# ---------------------------------------------------------------------------


def _apply_one(connection: _Connish, mig: MigrationFile) -> None:
    """Run a single migration file inside one transaction.

    The bootstrap migration creates the tracking table itself, so by the time
    we reach the ``INSERT`` it is guaranteed to exist — whether the bootstrap
    statement created it in this same transaction or an earlier run did.
    """
    cur = connection.cursor()
    try:
        cur.execute(mig.content, ())
        cur.execute(_INSERT_LOG_SQL, (mig.filename, mig.sha256))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _open_connection(factory: Optional[ConnectionFactory]) -> _Connish:
    f = factory or _default_connection_factory
    return f()


@contextmanager
def _managed_connection(factory: Optional[ConnectionFactory]) -> Iterator[_Connish]:
    conn = _open_connection(factory)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover — defensive
            pass


def migrate_up(
    *,
    schema_dir: Optional[Path] = None,
    connection_factory: Optional[ConnectionFactory] = None,
    dry_run: bool = False,
) -> list[str]:
    """Apply every pending migration. Returns the filenames just applied.

    Re-running with no new files is a no-op. A drifted hash raises
    :class:`MigrationError` — no migration runs in that case.
    """
    sdir = schema_dir or _DEFAULT_SCHEMA_DIR
    files = _discover_migrations(sdir)

    just_applied: list[str] = []

    with _managed_connection(connection_factory) as conn:
        cur = conn.cursor()

        bootstrap_just_ran = False
        # Bootstrap: the tracking table may not exist yet.
        if not _tracking_table_exists(cur):
            bootstrap = files[0]
            if dry_run:
                logger.info("[dry-run] would bootstrap %s", bootstrap.filename)
                just_applied.append(bootstrap.filename)
            else:
                logger.info("Bootstrapping %s", bootstrap.filename)
                _apply_one(conn, bootstrap)
                just_applied.append(bootstrap.filename)
            bootstrap_just_ran = True
            # Refresh cursor in case the connection was reset by DDL.
            cur = conn.cursor()

        applied = _fetch_applied(cur) if not (dry_run and bootstrap_just_ran) else {}
        # When dry-running on an empty DB we still want to "skip" the bootstrap
        # we just claimed to apply.
        if bootstrap_just_ran and dry_run:
            applied = {files[0].filename: files[0].sha256}
        # Drift check across ALL files before applying anything.
        drift = [
            f.filename
            for f in files
            if f.filename in applied and applied[f.filename] != f.sha256
        ]
        if drift:
            raise MigrationError(
                "Schema drift detected. The following files were already applied "
                "but their contents changed on disk: "
                f"{drift}. Refusing to migrate. "
                "Resolve by either reverting the file or creating a new migration "
                "with the changes."
            )

        for mig in files:
            if mig.filename in applied:
                continue
            if dry_run:
                logger.info("[dry-run] would apply %s", mig.filename)
                just_applied.append(mig.filename)
                continue
            logger.info("Applying %s", mig.filename)
            _apply_one(conn, mig)
            just_applied.append(mig.filename)

    return just_applied


def migrate_status(
    *,
    schema_dir: Optional[Path] = None,
    connection_factory: Optional[ConnectionFactory] = None,
) -> MigrationStatus:
    """Return the current applied/pending/drift sets without changing the DB."""
    sdir = schema_dir or _DEFAULT_SCHEMA_DIR
    files = _discover_migrations(sdir)

    with _managed_connection(connection_factory) as conn:
        cur = conn.cursor()
        if not _tracking_table_exists(cur):
            return MigrationStatus(
                applied=[],
                pending=[f.filename for f in files],
                drift=[],
            )
        applied_map = _fetch_applied(cur)

    applied: list[str] = []
    pending: list[str] = []
    drift: list[str] = []
    for f in files:
        if f.filename not in applied_map:
            pending.append(f.filename)
        elif applied_map[f.filename] != f.sha256:
            drift.append(f.filename)
        else:
            applied.append(f.filename)
    return MigrationStatus(applied=applied, pending=pending, drift=drift)


# ---------------------------------------------------------------------------
# Convenience for unit tests
# ---------------------------------------------------------------------------


def _schema_dir_default() -> Path:
    """Exposed for tests that want to know where the runner looks by default."""
    return _DEFAULT_SCHEMA_DIR
