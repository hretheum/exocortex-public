#!/usr/bin/env -S python3.12 -u
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# F4.6.5.4 — DB sanity check for second-brain ingest + synthesis pipeline.
#
# Designed to run from cron or CI: exits 0 when clean, non-zero with a per-
# check error count when anomalies are found. Fast read-only queries; safe to
# run anytime against production DB.
#
# Usage:
#   python3 scripts/sanity_check.py            # all checks, exit non-zero on anomaly
#   python3 scripts/sanity_check.py --json     # machine-readable JSON
#   python3 scripts/sanity_check.py --strict   # also fail on warnings (e.g. orphan edges)

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / 'config' / '.env')

from exocortex.db import query, query_one  # noqa: E402

logger = logging.getLogger('sanity_check')

REPO_ROOT = Path(__file__).resolve().parent.parent
X_SNAPSHOT_PATH = REPO_ROOT / 'data' / 'discovery' / '.sanity_x_snapshot.json'
X_LINE_RE = re.compile(r'^[ \t]*-[ \t]*\[[xX]\]', re.MULTILINE)


def _comma_participants(tenant_id: str) -> list[dict]:
    sql = """
        SELECT id::text AS id, metadata->>'meeting_id' AS meeting_id,
               metadata->'participants' AS participants
        FROM thoughts
        WHERE tenant_id = %s
          AND thought_type = 'work_meeting_note'
          AND jsonb_typeof(metadata->'participants') = 'array'
          AND EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(metadata->'participants') AS x
              WHERE x LIKE %s
          )
    """
    return query(sql, tenant_id, '%,%')


def _comma_syntheses(tenant_id: str) -> list[dict]:
    return query(
        "SELECT id::text AS id, perspective_type, perspective_key "
        "FROM syntheses WHERE tenant_id = %s "
        "  AND superseded_by IS NULL "
        "  AND perspective_key LIKE %s",
        tenant_id, '%,%',
    )


def _orphan_edges(tenant_id: str) -> list[dict]:
    """Edges whose dst_id is not in entities (for person/client/project) or
    in thoughts (for thought)."""
    sql = """
        WITH e AS (
            SELECT id::text AS id, src_id::text AS src_id, src_type,
                   dst_id::text AS dst_id, dst_type, type
            FROM edges WHERE tenant_id = %s
        )
        SELECT e.* FROM e
        LEFT JOIN entities et
               ON et.id = e.dst_id::uuid
              AND et.tenant_id = %s
              AND e.dst_type IN ('person', 'client', 'project')
        LEFT JOIN thoughts th
               ON th.id = e.dst_id::uuid
              AND th.tenant_id = %s
              AND e.dst_type = 'thought'
        WHERE (e.dst_type IN ('person', 'client', 'project') AND et.id IS NULL)
           OR (e.dst_type = 'thought' AND th.id IS NULL)
    """
    return query(sql, tenant_id, tenant_id, tenant_id)


def _comma_entities(tenant_id: str) -> list[dict]:
    return query(
        "SELECT id::text AS id, canonical_name, type FROM entities "
        "WHERE tenant_id = %s AND canonical_name LIKE %s",
        tenant_id, '%,%',
    )


def _missing_titles(tenant_id: str) -> int:
    row = query_one(
        "SELECT count(*) AS n FROM thoughts "
        "WHERE tenant_id = %s AND thought_type = 'work_meeting_note' "
        "  AND (metadata->>'title' IS NULL OR metadata->>'title' = '')",
        tenant_id,
    )
    return int(row['n']) if row else 0


def _missing_embeddings(tenant_id: str) -> int:
    row = query_one(
        "SELECT count(*) AS n FROM thoughts "
        # vault_note documents are NULL by design since the thought_chunks
        # migration (docs/migracje/thought-chunks.md) — excluded so this
        # counts real gaps, not the expected state of every vault_note row.
        "WHERE tenant_id = %s AND embedding IS NULL AND thought_type != 'vault_note'",
        tenant_id,
    )
    return int(row['n']) if row else 0


def _check_user_state_drift(vault_path: Path) -> tuple[list[dict], dict[str, int]]:
    """Detect any [x] count drop in meeting pages between snapshots.

    Stores snapshot at data/discovery/.sanity_x_snapshot.json. Returns
    (drift_entries, current_snapshot). Drift = file's [x] count is LOWER
    than stored snapshot — user-toggled [x] was overwritten by some
    automation (e.g. wiki_compiler regen, auto-tag bug). Reports as
    warning. Saves new snapshot AFTER comparing.
    """
    meetings_dir = vault_path / 'wiki' / 'work' / 'meetings' / 'src'
    if not meetings_dir.is_dir():
        return [], {}

    # Load prior snapshot (or empty dict on first run / corruption).
    prior: dict[str, int] = {}
    if X_SNAPSHOT_PATH.exists():
        try:
            prior = json.loads(X_SNAPSHOT_PATH.read_text())
            if not isinstance(prior, dict):
                prior = {}
        except (json.JSONDecodeError, OSError):
            prior = {}

    current: dict[str, int] = {}
    drift: list[dict] = []
    for fp in sorted(meetings_dir.glob('*.md')):
        try:
            text = fp.read_text()
        except OSError:
            continue
        cnt = len(X_LINE_RE.findall(text))
        rel = fp.name
        current[rel] = cnt
        prior_cnt = prior.get(rel)
        if prior_cnt is not None and cnt < prior_cnt:
            drift.append({
                'file': rel,
                'snapshot_count': prior_cnt,
                'current_count': cnt,
                'delta': cnt - prior_cnt,
            })

    return drift, current


def _save_x_snapshot(snapshot: dict[str, int]) -> None:
    X_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    X_SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))


def _check_backlog_orphan_refs(vault_path: Path) -> list[dict]:
    """F13.4 — find [[meetings/...]] wikilinks in backlog files pointing to nonexistent pages."""
    backlog_dir = vault_path / '_ Second Brain' / 'backlog' / '_second-brain'
    meetings_src = vault_path / 'wiki' / 'work' / 'meetings' / 'src'
    if not backlog_dir.is_dir():
        return []

    existing_slugs: set[str] = set()
    if meetings_src.is_dir():
        for fp in meetings_src.glob('*.md'):
            existing_slugs.add(fp.stem)

    orphans: list[dict] = []
    wikilink_re = re.compile(r'\[\[(?:\.\./)*wiki/work/meetings(?:/src)?/([^\]|]+)(?:\|[^\]]*)?\]\]')
    for fp in sorted(backlog_dir.glob('*.md')):
        try:
            text = fp.read_text()
        except OSError:
            continue
        for m in wikilink_re.finditer(text):
            ref = m.group(1).removesuffix('.md')
            if ref and ref not in existing_slugs:
                orphans.append({
                    'backlog_file': str(fp.relative_to(vault_path)),
                    'reference': m.group(0),
                    'resolved_to': ref,
                })
    return orphans


def _check_promotion_consistency(vault_path: Path) -> dict:
    """F15 — verify the integrity of MCP-driven promotion stubs in
    `_second-brain/manual/*.md`.

    Post-F15-MCP-refactor (2026-05-05) the create path validates lines
    pre-write (workers.promotion_lib.create_promotion_stubs), so signals
    here detect drift _after_ promotion (manual edits, deleted parents,
    missing frontmatter fields) — not creation bugs.

    Returns dict with:
      orphans              — child stub whose `source_meeting` page is gone
      unmatched_lines      — child stub line edited/removed in meeting
                             (edge case: meeting curated post-promotion)
      dangling_children    — child whose declared parent file no longer
                             exists (parent removed without cascade)
      missing_fingerprint  — child stub frontmatter lacks
                             `source_fingerprint` (incomplete schema)
      total_promoted       — count of child stubs found
    """
    manual_dir = vault_path / '_ Second Brain' / 'backlog' / '_second-brain' / 'manual'
    meetings_dir = vault_path / 'wiki' / 'work' / 'meetings'
    if not manual_dir.is_dir() or not meetings_dir.is_dir():
        return {
            'orphans': [], 'unmatched_lines': [], 'dangling_children': [],
            'missing_fingerprint': [], 'total_promoted': 0,
        }

    # Build map: meeting_slug → body text.
    meeting_bodies: dict[str, str] = {}
    for fp in meetings_dir.glob('*.md'):
        try:
            meeting_bodies[fp.stem] = fp.read_text(encoding='utf-8')
        except OSError:
            continue

    # Inventory existing parent stubs (no `source_fingerprint`, no `parent`).
    import yaml
    parent_slugs: set[str] = set()
    stub_frontmatters: dict[Path, dict] = {}
    for stub in manual_dir.glob('*.md'):
        try:
            text = stub.read_text(encoding='utf-8')
        except OSError:
            continue
        m = re.match(r'\A---\n(.*?)\n---\n', text, re.DOTALL)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        stub_frontmatters[stub] = fm
        if 'source_fingerprint' not in fm and 'parent' not in fm:
            parent_slugs.add(stub.stem)

    orphans: list[dict] = []
    unmatched: list[dict] = []
    dangling: list[dict] = []
    missing_fp: list[dict] = []
    total = 0

    for stub, fm in stub_frontmatters.items():
        # Identify children either by source_fingerprint OR parent ref.
        is_child = 'source_fingerprint' in fm or 'parent' in fm
        if not is_child:
            continue
        total += 1

        # missing_fingerprint check: child schema requires source_fingerprint.
        if 'source_fingerprint' not in fm:
            missing_fp.append({
                'stub': stub.name,
                'reason': 'child stub frontmatter missing source_fingerprint',
            })
            continue

        fp_str = str(fm.get('source_fingerprint') or '')
        if ':' not in fp_str:
            missing_fp.append({
                'stub': stub.name,
                'reason': f'malformed source_fingerprint: {fp_str!r}',
            })
            continue
        meeting_slug, _hash = fp_str.split(':', 1)

        # dangling_children check: declared parent file must exist.
        parent_link = str(fm.get('parent') or '').strip()
        if parent_link:
            parent_id = parent_link.strip('[]')
            parent_slug = (parent_id[len('manual-'):]
                           if parent_id.startswith('manual-') else parent_id)
            if parent_slug not in parent_slugs:
                dangling.append({
                    'stub': stub.name,
                    'parent_id': parent_id,
                    'reason': 'parent stub file missing — uncascaded delete',
                })

        # orphans: meeting page itself is gone.
        body = meeting_bodies.get(meeting_slug)
        if body is None:
            orphans.append({
                'stub': stub.name,
                'meeting_slug': meeting_slug,
                'reason': 'meeting page missing',
            })
            continue

        # unmatched_lines (edge case detector): line text edited post-promotion.
        raw_line = str(fm.get('description') or fm.get('title') or '').strip()
        if not raw_line:
            continue
        canonical = re.sub(r'\s+✅\s*\d{4}-\d{2}-\d{2}', '', raw_line)
        canonical = re.sub(r'\s+➕\s*\d{4}-\d{2}-\d{2}', '', canonical).strip()
        if canonical and canonical not in body:
            unmatched.append({
                'stub': stub.name,
                'meeting_slug': meeting_slug,
                'reason': 'meeting line edited or removed after promotion',
            })

    return {
        'orphans': orphans,
        'unmatched_lines': unmatched,
        'dangling_children': dangling,
        'missing_fingerprint': missing_fp,
        'total_promoted': total,
    }


def _stale_syntheses(tenant_id: str, days: int = 30) -> int:
    row = query_one(
        "SELECT count(*) AS n FROM syntheses "
        "WHERE tenant_id = %s AND superseded_by IS NULL "
        "  AND generated_at < NOW() - %s::interval",
        tenant_id, f'{days} days',
    )
    return int(row['n']) if row else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tenant', default=os.environ.get('TENANT_ID'))
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--strict', action='store_true',
                    help='Treat warnings as failures (orphan edges, stale syntheses)')
    ap.add_argument('--stale-days', type=int, default=30,
                    help='Synthesis is "stale" after N days (default 30)')
    ap.add_argument('--vault', default=os.environ.get('VAULT_PATH'),
                    help='Vault path for user_state_drift check (default: $VAULT_PATH)')
    ap.add_argument('--no-update-snapshot', action='store_true',
                    help='Do NOT save new [x] snapshot (read-only sanity check)')
    args = ap.parse_args()
    if not args.tenant:
        print('ERROR: --tenant or $TENANT_ID required', file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)-7s %(name)s %(message)s')

    report: dict = {'tenant_id': args.tenant, 'errors': {}, 'warnings': {}, 'info': {}}
    errors = 0
    warnings = 0

    # ── ERRORS (block CI) ──
    comma_p = _comma_participants(args.tenant)
    if comma_p:
        report['errors']['comma_participants'] = {
            'count': len(comma_p),
            'sample': [r['meeting_id'] for r in comma_p[:5]],
        }
        errors += len(comma_p)

    comma_s = _comma_syntheses(args.tenant)
    if comma_s:
        report['errors']['comma_syntheses'] = {
            'count': len(comma_s),
            'sample': [r['perspective_key'][:80] for r in comma_s[:5]],
        }
        errors += len(comma_s)

    comma_e = _comma_entities(args.tenant)
    if comma_e:
        report['errors']['comma_entities'] = {
            'count': len(comma_e),
            'sample': [r['canonical_name'][:80] for r in comma_e[:5]],
        }
        errors += len(comma_e)

    missing_titles = _missing_titles(args.tenant)
    if missing_titles:
        report['errors']['missing_titles'] = {'count': missing_titles}
        errors += missing_titles

    # ── WARNINGS (--strict optional fail) ──
    orphan = _orphan_edges(args.tenant)
    if orphan:
        report['warnings']['orphan_edges'] = {
            'count': len(orphan),
            'sample': [{'id': r['id'][:8], 'type': r['type'],
                        'dst_type': r['dst_type'], 'dst_id': r['dst_id'][:8]}
                       for r in orphan[:5]],
        }
        warnings += len(orphan)

    missing_embeddings = _missing_embeddings(args.tenant)
    if missing_embeddings:
        report['warnings']['missing_embeddings'] = {'count': missing_embeddings}
        warnings += missing_embeddings

    stale = _stale_syntheses(args.tenant, args.stale_days)
    if stale:
        report['warnings']['stale_syntheses'] = {
            'count': stale, 'days_threshold': args.stale_days,
        }
        warnings += stale

    # F11.5.3 — user_state_drift check (filesystem snapshot, not DB).
    if args.vault:
        drift, current_snap = _check_user_state_drift(Path(args.vault))
        if drift:
            report['warnings']['user_state_drift'] = {
                'count': len(drift),
                'sample': drift[:5],
            }
            warnings += len(drift)
        # Save snapshot AFTER reporting drift, unless user opts out.
        if current_snap and not args.no_update_snapshot:
            _save_x_snapshot(current_snap)

        # F15 — promotion stub consistency (post MCP-refactor 2026-05-05:
        # creation is deterministic, so signals here flag _drift_ events).
        promo = _check_promotion_consistency(Path(args.vault))
        if promo['orphans']:
            report['errors']['promotion_orphans'] = {
                'count': len(promo['orphans']),
                'sample': promo['orphans'][:5],
            }
            errors += len(promo['orphans'])
        if promo['unmatched_lines']:
            report['warnings']['promotion_unmatched_lines'] = {
                'count': len(promo['unmatched_lines']),
                'sample': promo['unmatched_lines'][:5],
            }
            warnings += len(promo['unmatched_lines'])
        if promo['dangling_children']:
            report['warnings']['promotion_dangling_children'] = {
                'count': len(promo['dangling_children']),
                'sample': promo['dangling_children'][:5],
            }
            warnings += len(promo['dangling_children'])
        if promo['missing_fingerprint']:
            report['warnings']['promotion_missing_fingerprint'] = {
                'count': len(promo['missing_fingerprint']),
                'sample': promo['missing_fingerprint'][:5],
            }
            warnings += len(promo['missing_fingerprint'])
        if promo['total_promoted']:
            report['info']['promoted_stubs'] = promo['total_promoted']

        # F13.4 — orphan meeting refs in backlog files
        orphan_refs = _check_backlog_orphan_refs(Path(args.vault))
        if orphan_refs:
            report['warnings']['backlog_orphan_meeting_refs'] = {
                'count': len(orphan_refs),
                'sample': orphan_refs[:10],
            }
            warnings += len(orphan_refs)

    # ── INFO (summary) ──
    counts = {}
    counts['thoughts'] = query_one(
        'SELECT count(*) AS n FROM thoughts WHERE tenant_id = %s',
        args.tenant)['n']
    counts['active_syntheses'] = query_one(
        'SELECT count(*) AS n FROM syntheses WHERE tenant_id = %s '
        '  AND superseded_by IS NULL', args.tenant)['n']
    counts['edges'] = query_one(
        'SELECT count(*) AS n FROM edges WHERE tenant_id = %s',
        args.tenant)['n']
    counts['entities'] = query_one(
        'SELECT count(*) AS n FROM entities WHERE tenant_id = %s',
        args.tenant)['n']
    report['info']['counts'] = counts

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        logger.info('counts: %s', counts)
        if not (errors or warnings):
            logger.info('all clean — no anomalies detected')
        if report['errors']:
            for name, info in report['errors'].items():
                logger.error('  %s: %s', name, info)
        if report['warnings']:
            for name, info in report['warnings'].items():
                logger.warning('  %s: %s', name, info)

    if errors > 0:
        return 1
    if warnings > 0 and args.strict:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
