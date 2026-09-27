#!/usr/bin/env -S python3.12 -u
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# scripts/run_cross_domain_matching.py — F8.8.x.G T2 driver.
#
# Examples:
#   ./scripts/run_cross_domain_matching.py --client acme --dry-run --debug
#   ./scripts/run_cross_domain_matching.py --client acme --cost-stop 0.50
#   ./scripts/run_cross_domain_matching.py --all --missing-only
#   ./scripts/run_cross_domain_matching.py --cluster ai-foundations --force --cost-stop 0.50

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from exocortex.cross_domain_matcher import match_all  # noqa: E402


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description='F8.8.x.G T2 — cross-domain matcher (newsletter clusters × work clients).',
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--all', action='store_true',
                       help='Run all 12 × 8 = 96 pairs (default if no scope flag).')
    scope.add_argument('--client', metavar='SLUG',
                       help='Single client × all clusters (8 pairs).')
    scope.add_argument('--cluster', metavar='SLUG',
                       help='All clients × single cluster (12 pairs).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Log per-pair what would be judged; no LLM calls, no DB writes.')
    parser.add_argument('--missing-only', action='store_true', default=True,
                        help='Skip pairs already in sidecar cache (default true).')
    parser.add_argument('--no-missing-only', dest='missing_only', action='store_false',
                        help='Re-evaluate cached pairs (still respects sidecar UNIQUE — re-judge skipped).')
    parser.add_argument('--force', action='store_true',
                        help='Ignore sidecar cache, re-judge every pair (bumps cost).')
    parser.add_argument('--cost-stop', type=float, default=5.0, metavar='USD',
                        help='Cost cap (default $5). Pre-flight checks 24h cumulative; in-run halts further calls.')
    parser.add_argument('--debug', action='store_true', help='DEBUG logging.')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(name)s %(message)s',
    )

    summary = match_all(
        dry_run=args.dry_run,
        cost_stop_usd=args.cost_stop,
        missing_only=args.missing_only,
        force=args.force,
        client_filter=args.client,
        cluster_filter=args.cluster,
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if summary.get('aborted') and summary.get('reason') == 'cost_stop_pre_flight':
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(_cli())
