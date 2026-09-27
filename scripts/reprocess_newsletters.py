#!/usr/bin/env -S python3.12
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/reprocess_newsletters.py — F8.8.x.H2 follow-up.
#
# Re-runs newsletter.synthesize(source_id, force=True) for all existing
# newsletter raw_sources. Used after F8.8.x.H2.3 deployed canonical vocab
# constraint to refresh the 100 backlog newsletters with the new prompt.
#
# Idempotent: emit_thought_for_source UPDATEs existing thought rows by
# (source_id, thought_type) — preserves thought IDs + downstream edges.
# mark_processed re-stamps metadata.processors with new timestamp.
#
# Cost: ~100 × $0.013 = ~$1.30 expected with prompt cache hits.
# Cost-stop guard: --max-cost $X (default $5).
#
# Usage:
#   .venv/bin/python scripts/reprocess_newsletters.py [--limit N] [--max-cost 5.0] [--dry-run]
import argparse
import logging
import sys
from typing import Optional

from exocortex.db import query
from exocortex.processors._common import TENANT_ID
from exocortex.processors import newsletter as newsletter_processor

logger = logging.getLogger(__name__)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Re-run newsletter processor on all backlog sources.')
    p.add_argument('--limit', type=int, default=None, help='Process at most N newsletters (default: all).')
    p.add_argument('--max-cost', type=float, default=5.0, help='Abort once cumulative cost exceeds $X.')
    p.add_argument('--dry-run', action='store_true', help='List sources that would be reprocessed; no LLM calls.')
    p.add_argument('--debug', action='store_true', help='DEBUG-level logging.')
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s %(message)s',
    )

    sql = '''
        SELECT id::text AS id
        FROM raw_sources
        WHERE tenant_id = %s
          AND source_type = 'newsletter'
        ORDER BY ingested_at ASC
    '''
    if args.limit:
        sql += f' LIMIT {int(args.limit)}'
    rows = query(sql, TENANT_ID)
    logger.info('found %d newsletter raw_sources', len(rows))

    if args.dry_run:
        for r in rows[:10]:
            print(r['id'])
        if len(rows) > 10:
            print(f'... ({len(rows) - 10} more)')
        return 0

    cumulative = 0.0
    counts = {'ok': 0, 'error': 0, 'skipped': 0}

    for i, r in enumerate(rows, 1):
        source_id = r['id']
        try:
            result = newsletter_processor.synthesize(source_id, force=True)
            status = result.get('status', '?')
            cost = float(result.get('cost_usd') or 0.0)
            cumulative += cost
            counts[status] = counts.get(status, 0) + 1
            logger.info('[%d/%d] %s → %s (cost=$%.4f, cum=$%.4f)',
                        i, len(rows), source_id[:8], status, cost, cumulative)
            if cumulative > args.max_cost:
                logger.error('cumulative cost $%.4f exceeded cap $%.2f, aborting', cumulative, args.max_cost)
                return 3
        except Exception as exc:
            counts['error'] += 1
            logger.exception('error reprocessing %s: %s', source_id[:8], exc)

    logger.info('=== summary ===')
    for k, v in sorted(counts.items()):
        logger.info('  %s: %d', k, v)
    logger.info('cumulative cost: $%.4f', cumulative)
    return 0


if __name__ == '__main__':
    sys.exit(main())
