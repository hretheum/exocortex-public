#!/usr/bin/env -S .venv/bin/python
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F16 — Process live sections (scheduler entry point).

Called by systemd timer every 15 minutes.
Usage:
  .venv/bin/python scripts/process_live_sections.py [--verbose]
"""

import argparse
import logging
import sys
from pathlib import Path

# Allow `python scripts/process_live_sections.py` (relative or absolute path)
# to import the `workers` package — running a script file does not put the repo
# root on sys.path the way `python -m` does. Mirrors scripts/bulk_ingest_vault.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exocortex.live_sections import process_live_sections, process_live_events  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Process live sections")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    )

    # First, process events (fired from post-ingest hooks)
    events_done = process_live_events()

    # Then, check cron/window triggers
    result = process_live_sections(trigger_type='cron')

    print(f"Events processed: {events_done}")
    print(f"Sections processed: {result['processed']}")
    print(f"Skipped: {result['skipped']}")
    print(f"Errors: {result['errors']}")

    for r in result.get('results', []):
        print(f"  {r['status']:8s} {r.get('file', '?')} → {r.get('section_id', '?')}")

    return 0 if result['errors'] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
