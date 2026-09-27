# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/backfill_edges.py — F4.6.1.3: retroactively populate edges for existing
# 210 thoughts + 171 active syntheses. Idempotent — uq_edges_dedupe + ON CONFLICT
# DO NOTHING make re-runs no-op. AGE Cypher MERGE handles dual-write idempotently.
#
# Usage:
#   python3 scripts/backfill_edges.py            # full backfill
#   python3 scripts/backfill_edges.py --meetings # only meetings
#   python3 scripts/backfill_edges.py --syntheses # only syntheses
#   python3 scripts/backfill_edges.py --dry-run  # report counts but skip writes

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / 'config' / '.env')

from exocortex.db import (
    conn,
    query,
    _emit_meeting_edges,
    _emit_synthesis_edges,
)
from exocortex.classifier import classify_meeting

TENANT_ID = os.environ['TENANT_ID']
THOUGHT_TYPE = 'work_meeting_note'
LOG_EVERY = 25


def backfill_meetings() -> dict:
    """Re-classify and emit edges for every work_meeting_note thought.
    Returns aggregate counts dict."""
    rows = query(
        "SELECT id, metadata, extracted_tags FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = %s ORDER BY created_at",
        TENANT_ID, THOUGHT_TYPE,
    )
    print(f"[meetings] {len(rows)} thoughts to backfill")
    totals: dict = {}
    t0 = time.time()
    with conn() as c:
        for i, row in enumerate(rows, 1):
            tid = str(row['id'])
            meta = row['metadata'] or {}
            cls = classify_meeting({
                'id': tid,
                'metadata': meta,
                'extracted_tags': row.get('extracted_tags') or {},
            })
            counts = _emit_meeting_edges(c, tid, meta, cls, TENANT_ID)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            if i % LOG_EVERY == 0:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed else 0.0
                print(f"  [meetings] {i}/{len(rows)} done "
                      f"({elapsed:.1f}s, {rate:.1f}/s)")
    print(f"[meetings] done in {time.time() - t0:.1f}s — emitted {totals}")
    return totals


def backfill_syntheses() -> dict:
    """Emit edges for every active synthesis. Returns aggregate counts."""
    rows = query(
        "SELECT id, content FROM syntheses "
        "WHERE tenant_id = %s AND superseded_by IS NULL ORDER BY generated_at",
        TENANT_ID,
    )
    print(f"[syntheses] {len(rows)} active syntheses to backfill")
    totals: dict = {}
    t0 = time.time()
    with conn() as c:
        for i, row in enumerate(rows, 1):
            sid = str(row['id'])
            content = row['content'] or {}
            counts = _emit_synthesis_edges(c, sid, content, TENANT_ID)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
            if i % LOG_EVERY == 0:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed else 0.0
                print(f"  [syntheses] {i}/{len(rows)} done "
                      f"({elapsed:.1f}s, {rate:.1f}/s)")
    print(f"[syntheses] done in {time.time() - t0:.1f}s — emitted {totals}")
    return totals


def report() -> None:
    print('\n=== Edge counts by type ===')
    rows = query(
        "SELECT type, count(*) AS n FROM edges WHERE tenant_id = %s "
        "GROUP BY type ORDER BY n DESC", TENANT_ID,
    )
    if not rows:
        print('  (no edges)')
    for r in rows:
        print(f"  {r['type']:24s} {r['n']:>6d}")

    total_row = query("SELECT count(*) AS n FROM edges WHERE tenant_id = %s",
                      TENANT_ID)
    print(f"\nTotal edges: {total_row[0]['n']}")

    print('\n=== Entity counts by type ===')
    erows = query(
        "SELECT type, count(*) AS n FROM entities WHERE tenant_id = %s "
        "GROUP BY type ORDER BY n DESC", TENANT_ID,
    )
    for r in erows:
        print(f"  {r['type']:24s} {r['n']:>6d}")


def main() -> None:
    parser = argparse.ArgumentParser(description='Retroactively populate edges for existing thoughts and syntheses')
    parser.add_argument('--meetings', action='store_true', help='Only backfill meetings')
    parser.add_argument('--syntheses', action='store_true', help='Only backfill syntheses')
    parser.add_argument('--dry-run', action='store_true', help='Report counts but skip writes')
    args = parser.parse_args()

    do_meetings = not args.syntheses
    do_syntheses = not args.meetings
    if args.dry_run:
        print('[dry-run] would backfill meetings + syntheses but skipping writes')
        report()
        return

    t0 = time.time()
    if do_meetings:
        backfill_meetings()
    if do_syntheses:
        backfill_syntheses()
    print(f"\nTotal elapsed: {time.time() - t0:.1f}s")
    report()


if __name__ == '__main__':
    main()
