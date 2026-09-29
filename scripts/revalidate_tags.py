# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/revalidate_tags.py — F3.4: periodic re-validation of LLM-extracted tags.
#
# Why: tags extracted once can go stale — a new project starts to make
#   sense, a client renames itself, a topic evolves. Plus: taxonomy.yaml changes
#   (new statuses, activities) → older extractions do not know the new vocab.
#
# Strategy:
#   1. Selection: thoughts where extracted_tags.extracted_at < now() - 60 days
#      (or --all to force re-runs).
#   2. Re-run extract_tags_batch.process_thought (idempotent — skip when run_id matches).
#   3. Diff old vs new tags → log to data/discovery/tag_drift_log.tsv.
#   4. New tags (`new: true` from LLM) → data/discovery/new_tags.tsv (manual review queue).
#
# Usage:
#   python scripts/revalidate_tags.py --tenant=$TENANT_ID            # only stale (60d+)
#   python scripts/revalidate_tags.py --all --limit 10               # force re-run, capped
#   python scripts/revalidate_tags.py --dry-run --limit 5            # smoke test
#
# Cron schedule (once F1.5 is ready): pg_cron weekly run, --all=False (selective).

from __future__ import annotations
import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / 'config' / '.env')

from scripts.extract_tags_batch import (
    PROMPT_VERSION,
    estimate_cost_usd,
    process_thought,
    taxonomy_hash,
    load_taxonomy,
    build_system_prompt,
)
from exocortex.classifier import load_config
from exocortex.db import query

THOUGHT_TYPE = 'work_meeting_note'
TENANT_ID = os.environ.get('TENANT_ID')
DISCOVERY_DIR = Path(__file__).parent.parent / 'data' / 'discovery'
DRIFT_LOG = DISCOVERY_DIR / 'tag_drift_log.tsv'
NEW_TAGS_LOG = DISCOVERY_DIR / 'new_tags.tsv'
STALE_DAYS_DEFAULT = 60

AXES = ('client', 'project', 'activity', 'topic', 'status')


# ─────────────────────────────────────────────── Diff helpers ──

def _values_with_conf(items: list[dict]) -> dict[str, float]:
    """Map tag value → confidence. Used for diff comparison."""
    return {it['value']: float(it.get('confidence', 0.0))
            for it in (items or []) if it.get('value')}


def diff_axis(old: list[dict], new: list[dict]) -> list[tuple[str, str, str, str]]:
    """Return list of (action, old_value, new_value, detail) tuples per axis.

    Actions:
      - added:           tag in new, not in old
      - removed:         tag in old, not in new
      - confidence_changed: same tag, |Δconf| > 0.15
    """
    old_map = _values_with_conf(old)
    new_map = _values_with_conf(new)
    diffs: list[tuple[str, str, str, str]] = []
    for v, conf in new_map.items():
        if v not in old_map:
            diffs.append(('added', '', v, f'conf={conf:.2f}'))
        elif abs(conf - old_map[v]) > 0.15:
            diffs.append(('confidence_changed', v, v,
                          f'{old_map[v]:.2f}->{conf:.2f}'))
    for v, conf in old_map.items():
        if v not in new_map:
            diffs.append(('removed', v, '', f'old_conf={conf:.2f}'))
    return diffs


# ─────────────────────────────────────────────── Logging ──

def _log_drift(meeting_id: str, axis: str,
               diffs: list[tuple[str, str, str, str]]) -> None:
    if not diffs:
        return
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not DRIFT_LOG.exists()
    with open(DRIFT_LOG, 'a', newline='') as fh:
        w = csv.writer(fh, delimiter='\t')
        if new_file:
            w.writerow(['timestamp', 'meeting_id', 'axis', 'action',
                        'old_value', 'new_value', 'detail'])
        ts = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for action, old_v, new_v, detail in diffs:
            w.writerow([ts, meeting_id, axis, action, old_v, new_v, detail])


def _log_new_tags(meeting_id: str, payload: dict) -> int:
    """Log tags with the `new: true` flag. Returns count of new tags logged."""
    count = 0
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    new_file = not NEW_TAGS_LOG.exists()
    with open(NEW_TAGS_LOG, 'a', newline='') as fh:
        w = csv.writer(fh, delimiter='\t')
        if new_file:
            w.writerow(['timestamp', 'meeting_id', 'axis', 'value', 'confidence'])
        ts = datetime.now(timezone.utc).isoformat(timespec='seconds')
        for axis in ('project', 'topic'):  # only dynamic vocab axes
            for it in (payload.get(axis) or []):
                if it.get('new'):
                    w.writerow([ts, meeting_id, axis, it['value'],
                                f"{float(it.get('confidence', 0)):.2f}"])
                    count += 1
    return count


# ─────────────────────────────────────────────── Selection ──

def _build_select_sql(args) -> tuple[str, list]:
    """Returns (sql, params) for thought selection.

    --all   → all thoughts (no time filter)
    default → only thoughts where extracted_at < now() - $stale_days
              OR extracted_tags is missing entirely (never extracted).
    """
    base = ("SELECT id, thought_type, metadata, extracted_tags FROM thoughts "
            "WHERE tenant_id = %s AND thought_type = %s")
    params: list = [args.tenant, THOUGHT_TYPE]
    if not args.all:
        base += (" AND ("
                 "extracted_tags->>'extracted_at' IS NULL "
                 "OR (extracted_tags->>'extracted_at')::timestamptz "
                 "    < now() - (%s || ' days')::interval"
                 ")")
        params.append(str(args.stale_days))
    base += " ORDER BY extracted_tags->>'extracted_at' ASC NULLS FIRST"
    if args.limit is not None:
        base += " LIMIT %s"
        params.append(args.limit)
    return base, params


# ─────────────────────────────────────────────────── Main ──

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tenant', default=TENANT_ID, help='Tenant UUID (default: $TENANT_ID).')
    ap.add_argument('--all', action='store_true',
                    help='Re-extract ALL thoughts (ignore stale_days filter).')
    ap.add_argument('--stale-days', type=int, default=STALE_DAYS_DEFAULT,
                    help=f'Re-extract thoughts older than N days (default {STALE_DAYS_DEFAULT}).')
    ap.add_argument('--limit', type=int, default=None,
                    help='Max thoughts to process (default unlimited).')
    ap.add_argument('--dry-run', action='store_true',
                    help='Skip DB writes; print drift and new-tags summary.')
    ap.add_argument('--cost-stop', type=float, default=0.50,
                    help='Abort if cumulative cost exceeds $X (default 0.50).')
    args = ap.parse_args()

    if not args.tenant:
        print('ERROR: --tenant or $TENANT_ID required', file=sys.stderr)
        return 2

    taxonomy = load_taxonomy()
    tax_hash = taxonomy_hash(taxonomy)
    system_prompt = build_system_prompt(taxonomy)
    projects_cfg = load_config()

    sql, params = _build_select_sql(args)
    rows = query(sql, *params)

    print(f'[F3.4] Selected {len(rows)} thoughts for re-validation '
          f'(stale_days={args.stale_days}, all={args.all}, limit={args.limit})')
    print(f'[F3.4] taxonomy_hash={tax_hash} prompt_version={PROMPT_VERSION}')
    print(f'[F3.4] dry_run={args.dry_run} cost_stop=${args.cost_stop}')
    print(f'[F3.4] drift log: {DRIFT_LOG}')
    print(f'[F3.4] new tags log: {NEW_TAGS_LOG}\n')

    cum_usage = {'input_tokens': 0, 'output_tokens': 0,
                 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
    counts = {'ok': 0, 'skipped': 0, 'error': 0}
    drifted = 0
    new_tags_total = 0

    for i, thought in enumerate(rows, 1):
        meeting_id = (thought.get('metadata') or {}).get('meeting_id') or thought['id']
        old_tags = thought.get('extracted_tags') or {}

        result = process_thought(thought, system_prompt, tax_hash, projects_cfg, args.dry_run)
        counts[result['status']] += 1

        if result['status'] == 'ok':
            for k, v in result['usage'].items():
                cum_usage[k] += v
            new_payload = result['output']

            # Diff per axis
            had_drift = False
            for axis in AXES:
                diffs = diff_axis(old_tags.get(axis) or [],
                                  new_payload.get(axis) or [])
                if diffs and not args.dry_run:
                    _log_drift(meeting_id, axis, diffs)
                    had_drift = True
                elif diffs:
                    had_drift = True
                    print(f'  [{i}/{len(rows)}] {meeting_id} {axis}: {len(diffs)} diffs')
            if had_drift:
                drifted += 1

            # New tags log
            if not args.dry_run:
                n = _log_new_tags(meeting_id, new_payload)
                new_tags_total += n
            else:
                n = sum(1 for axis in ('project', 'topic')
                        for it in (new_payload.get(axis) or []) if it.get('new'))
                new_tags_total += n

            cost = estimate_cost_usd(cum_usage)
            print(f'  [{i}/{len(rows)}] {meeting_id}: '
                  f'ok drift={had_drift} new={n} cost=${cost:.4f}')
            if cost > args.cost_stop:
                print(f'\n[F3.4] COST STOP — cumulative ${cost:.4f} > ${args.cost_stop}.')
                break
        elif result['status'] == 'skipped':
            print(f'  [{i}/{len(rows)}] {meeting_id}: SKIP ({result["reason"]})')
        else:
            print(f'  [{i}/{len(rows)}] {meeting_id}: ERROR {result.get("reason")}')

    final_cost = estimate_cost_usd(cum_usage)
    print(f'\n[F3.4] Done. ok={counts["ok"]} skipped={counts["skipped"]} '
          f'error={counts["error"]} drifted={drifted} new_tags={new_tags_total}')
    print(f'[F3.4] Tokens: input={cum_usage["input_tokens"]} '
          f'cache_read={cum_usage["cache_read_input_tokens"]} '
          f'output={cum_usage["output_tokens"]}')
    print(f'[F3.4] Estimated cost: ${final_cost:.4f}')
    if args.dry_run:
        print('[F3.4] DRY RUN — no DB writes, no drift/new-tags TSV updates.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
