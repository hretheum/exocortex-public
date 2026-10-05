"""Applied migrations are immutable.

`exocortex migrate up` hashes every ``schema/*.sql`` file and refuses to run when
an already-applied file changed on disk ("Schema drift detected"). A comment-only
edit (54a9a72, 2026-09-29) was enough to stop the lab migration and, with it,
the lab API after the next image pull. This test catches that in CI instead.

To add a migration: create the new file and append its line to
``tests/unit/migrations.lock`` (``sha256  filename``, same hashing as the migrator).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schema"
BUNDLED = ROOT / "exocortex" / "_bundled" / "schema"
LOCK = Path(__file__).with_name("migrations.lock")


def _hash(path: Path) -> str:
    # Mirrors exocortex.core.db.migrations._hash_text(read_text(utf-8)).
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _lock() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, name = line.split(maxsplit=1)
        entries[name.strip()] = digest
    return entries


def _migrations(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.name != "views.sql")


def test_locked_migrations_are_unchanged() -> None:
    changed = [
        name
        for name, digest in _lock().items()
        if (SCHEMA / name).exists() and _hash(SCHEMA / name) != digest
    ]
    assert not changed, (
        f"already-applied migrations were edited: {changed}. Revert them and put the "
        "change in a NEW migration — edited files make `migrate up` refuse to run."
    )


def test_locked_migrations_are_not_deleted() -> None:
    missing = [name for name in _lock() if not (SCHEMA / name).exists()]
    assert not missing, f"applied migrations deleted from schema/: {missing}"


def test_every_migration_is_in_the_lock() -> None:
    unlocked = [p.name for p in _migrations(SCHEMA) if p.name not in _lock()]
    assert not unlocked, f"new migrations missing from tests/unit/migrations.lock: {unlocked}"


def test_bundled_migrations_match_the_lock() -> None:
    if not BUNDLED.is_dir():
        return
    lock = _lock()
    changed = [p.name for p in _migrations(BUNDLED) if p.name in lock and _hash(p) != lock[p.name]]
    assert not changed, f"bundled copies differ from the applied migrations: {changed}"
