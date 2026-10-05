# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""CLI entry-point: python -m exocortex.wiki [options]

Examples:
  python -m exocortex.wiki --domain news --dry-run
  python -m exocortex.wiki --domain all --full-rebuild
  python -m exocortex.wiki --list-domains
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exocortex.core.registry import Registry


def _ensure_path() -> None:
    if __package__ is None:
        import pathlib

        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))


def _build_registry() -> Registry:
    from exocortex.core.registry import Registry
    from exocortex.wiki.runner import setup_builtins

    registry = Registry()
    setup_builtins(registry)
    return registry


def main(argv: list[str] | None = None) -> None:
    _ensure_path()

    parser = argparse.ArgumentParser(
        prog="python -m exocortex.wiki",
        description="Compile wiki domains from the knowledge graph.",
    )
    from exocortex.settings import get_tenant_id

    parser.add_argument("--tenant", default=get_tenant_id())
    parser.add_argument("--domain", default="all", help="Domain to compile, or 'all'")
    parser.add_argument(
        "--since", default=None, help="ISO-8601 cutoff (e.g. 2024-01-01)"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full-rebuild", action="store_true")
    parser.add_argument(
        "--list-domains", action="store_true", help="Print registered domains and exit"
    )
    args = parser.parse_args(argv)

    registry = _build_registry()

    if args.list_domains:
        for name in sorted(registry.compile_domains):
            print(name)
        return

    since_dt = None
    if args.since:
        from datetime import datetime

        since_dt = datetime.fromisoformat(args.since)

    from exocortex.wiki.runner import compile_all

    compile_all(
        registry,
        tenant_id=args.tenant,
        domain=args.domain,
        since=since_dt,
        dry_run=args.dry_run,
        full_rebuild=args.full_rebuild,
    )


if __name__ == "__main__":
    main()
