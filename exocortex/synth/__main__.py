# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""CLI entry-point for the Exocortex synthesis runner.

Usage::

    python -m exocortex.synth --perspective meeting_summary --dry-run
    python -m exocortex.synth --perspective client_review --key acme --dry-run
    python -m exocortex.synth --list

With --fake-data the runner skips DB and LLM; useful for smoke-testing the
registry plumbing without any external credentials.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys


def _fake_thoughts(perspective_name: str, key: str) -> list[dict]:
    """Return a minimal list of synthetic thought dicts for smoke testing."""
    return [
        {
            "id": f"00000000-0000-0000-0000-00000000000{i}",
            "thought_type": "work_meeting_note",
            "body": f"[Smoke test thought {i}] perspective={perspective_name} key={key}",
            "created_at": f"2026-01-0{i}T10:00:00",
            "metadata": {
                "title": f"Test meeting {i}",
                "date": f"2026-01-0{i}",
                "tags": [key],
            },
            "extracted_tags": {
                "client": [{"value": key}],
                "type": [{"value": perspective_name}],
            },
        }
        for i in range(1, 4)
    ]


def _fake_run(perspective_name: str, key: str) -> None:
    """Smoke test: exercise registry plumbing without DB/LLM."""
    from exocortex.core.registry import Registry
    from exocortex.synth.runner import setup_builtins, SynthContext

    reg = Registry()
    setup_builtins(reg)

    if perspective_name not in reg.perspectives:
        print(f"ERROR: unknown perspective '{perspective_name}'", file=sys.stderr)
        print(f"Available: {', '.join(sorted(reg.perspectives))}", file=sys.stderr)
        sys.exit(1)

    p = reg.perspectives[perspective_name]
    SynthContext(tenant_id="smoke-test", perspective_key=key)
    thoughts = _fake_thoughts(perspective_name, key)

    print(f"perspective : {perspective_name}")
    print(f"legacy_type : {getattr(p, '_legacy_type', perspective_name)}")
    print(f"key         : {key}")
    print(f"thoughts    : {len(thoughts)}")
    print("status      : ok (fake-data, no LLM call)")
    print("\n1 synthesis row would be generated in non-dry-run mode.")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    ap = argparse.ArgumentParser(description="Exocortex synthesis runner")
    ap.add_argument("--perspective", help="Perspective name (e.g. meeting_summary)")
    ap.add_argument("--key", default="smoke-test", help="Perspective key")
    ap.add_argument("--dry-run", action="store_true", help="Skip DB persist")
    ap.add_argument("--fake-data", action="store_true", help="Use synthetic thoughts, skip DB+LLM")
    ap.add_argument("--list", action="store_true", help="List registered perspectives and exit")
    args = ap.parse_args()

    if args.list:
        from exocortex.core.registry import Registry
        from exocortex.synth.runner import setup_builtins
        reg = Registry()
        setup_builtins(reg)
        for name in sorted(reg.perspectives):
            p = reg.perspectives[name]
            legacy = getattr(p, "_legacy_type", "—")
            print(f"  {name:<30} (legacy: {legacy})")
        return

    if not args.perspective:
        ap.error("--perspective is required (or use --list)")

    if args.fake_data or args.dry_run:
        _fake_run(args.perspective, args.key)
        return

    from exocortex.core.registry import registry
    from exocortex.synth.runner import setup_builtins, run

    setup_builtins(registry)
    result = run(
        registry,
        args.perspective,
        args.key,
        dry_run=args.dry_run,
    )
    print(json.dumps(
        {
            "perspective_type": getattr(result, "perspective_type", None),
            "perspective_key": getattr(result, "perspective_key", None),
            "status": getattr(result, "status", str(result)),
            "synthesis_id": getattr(result, "synthesis_id", None),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
