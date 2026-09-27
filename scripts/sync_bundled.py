# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Copy ``config/`` + ``schema/`` into ``exocortex/_bundled/`` for wheel packaging.

Run this after editing ``config/*.example.yaml``, ``config/.env.example`` or
``schema/*.sql`` so that ``pip install exocortex`` users get the same defaults
as a fresh repo checkout. Idempotent: re-running with no upstream changes is a
no-op.

Usage:
    python scripts/sync_bundled.py [--check]

``--check`` exits 1 if the bundle drifts from the source. The unit-test suite
invokes ``sync_bundled --check`` so a forgotten resync fails CI before a
release ships a silently stale bundle to PyPI.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS: tuple[tuple[Path, Path, tuple[str, ...]], ...] = (
    (
        REPO_ROOT / "config",
        REPO_ROOT / "exocortex" / "_bundled" / "config",
        ("*.example.yaml", ".env.example", "README.md"),
    ),
    (
        REPO_ROOT / "schema",
        REPO_ROOT / "exocortex" / "_bundled" / "schema",
        ("*.sql",),
    ),
)


def _iter_sources(src_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        # explicit name without metachars — match exactly one file if present
        if any(ch in pattern for ch in "*?["):
            found.extend(sorted(src_dir.glob(pattern)))
        else:
            candidate = src_dir / pattern
            if candidate.exists():
                found.append(candidate)
    return found


def sync(check: bool = False) -> int:
    drift: list[str] = []
    for src_dir, dst_dir, patterns in SOURCE_DIRS:
        dst_dir.mkdir(parents=True, exist_ok=True)
        # Preserve the package marker — empty __init__.py marks _bundled/* as
        # importable resources so importlib.resources works inside the wheel.
        marker = dst_dir / "__init__.py"
        if not marker.exists():
            marker.write_text("", encoding="utf-8")
        sources = _iter_sources(src_dir, patterns)
        wanted_names = {p.name for p in sources} | {"__init__.py"}
        for src in sources:
            dst = dst_dir / src.name
            if check:
                if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
                    drift.append(f"{src.relative_to(REPO_ROOT)} != {dst.relative_to(REPO_ROOT)}")
            else:
                shutil.copyfile(src, dst)
        # Prune stale bundled files that no longer exist upstream — e.g. a
        # renamed example. Skip __init__.py so the package marker survives.
        for stale in dst_dir.iterdir():
            if stale.name not in wanted_names:
                if check:
                    drift.append(f"stale: {stale.relative_to(REPO_ROOT)}")
                else:
                    stale.unlink()
    if check and drift:
        sys.stderr.write("Bundle drift detected:\n  " + "\n  ".join(drift) + "\n")
        sys.stderr.write("Run `python scripts/sync_bundled.py` to refresh.\n")
        return 1
    if not check:
        print(f"Bundled {sum(len(_iter_sources(s, p)) for s, _, p in SOURCE_DIRS)} files into exocortex/_bundled/")
    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the bundle drifts from the source (CI-friendly)",
    )
    args = parser.parse_args()
    return sync(check=args.check)


if __name__ == "__main__":
    raise SystemExit(_main())
