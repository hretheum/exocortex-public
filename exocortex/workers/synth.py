# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Synthesizer CLI entry-point.

Importable module entry-point for ``exocortex synth`` and
``python -m exocortex.workers.synth``. The thin ``scripts/run_synthesizer.py``
shim re-exports from here for backward compatibility with cron / systemd that
historically called the script path directly.

F4.2: CLI entrypoint for workers.synthesizer.
F4.6.3: shebang `python3 -u` enforces unbuffered stdout (real-time logs in cron).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

# Load config/.env if running from a source checkout. In a wheel install,
# env is provided externally (systemd, docker).
_repo_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_repo_root / "config" / ".env")

from exocortex.db import execute, query, query_one
from exocortex.synthesizer import (
    LLM_MODEL,
    PROMPT_VERSION,
    compute_input_hash,
    discover_perspectives,
    select_source_thoughts,
    synthesize,
)

TENANT_ID = os.environ.get("TENANT_ID")

logger = logging.getLogger("exocortex.workers.synth")


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def _log_result(r, total_cost: float, idx: int | None = None, total: int | None = None) -> None:
    progress = f"[{idx}/{total}] " if idx is not None else ""
    base = f"{progress}{r.perspective_type}={r.perspective_key}"
    if r.status == "ok":
        c = r.content or {}
        logger.info(
            "%s OK (%d dec, %d prob, %d own, %d steps) src=%d cost=$%.4f cum=$%.4f",
            base,
            len(c.get("recent_decisions", [])),
            len(c.get("open_problems", [])),
            len(c.get("ownership", [])),
            len(c.get("next_steps", [])),
            len(r.source_thought_ids),
            r.cost_usd, total_cost,
        )
    elif r.status == "skipped":
        logger.info("%s SKIP (%s)", base, r.reason)
    elif r.status == "below-threshold":
        logger.warning("%s BELOW-THRESHOLD (%s)", base, r.reason)
    elif r.status == "no-thoughts":
        logger.warning("%s NO-THOUGHTS", base)
    else:
        logger.error("%s ERROR %s", base, r.reason)


def _load_active_input_hashes(tenant_id: str) -> dict[tuple[str, str], str]:
    try:
        rows = query(
            "SELECT perspective_type, perspective_key, input_hash "
            "FROM syntheses WHERE tenant_id = %s AND superseded_by IS NULL",
            tenant_id,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.warning("cannot load active input hashes (smart resume disabled): %r", exc)
        return {}
    return {(r["perspective_type"], r["perspective_key"]): r["input_hash"]
            for r in rows}


def _filter_missing_only(targets: list[tuple[str, str]],
                         tenant_id: str) -> list[tuple[str, str]]:
    active_hashes = _load_active_input_hashes(tenant_id)
    if not active_hashes:
        return targets
    kept: list[tuple[str, str]] = []
    skipped = 0
    for ptype, pkey in targets:
        existing = active_hashes.get((ptype, pkey))
        if existing is None:
            kept.append((ptype, pkey))
            continue
        source = select_source_thoughts(tenant_id, ptype, pkey)
        if not source:
            kept.append((ptype, pkey))
            continue
        try:
            new_hash = compute_input_hash(ptype, pkey, source)
        except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            kept.append((ptype, pkey))
            continue
        if new_hash == existing:
            skipped += 1
        else:
            kept.append((ptype, pkey))
    logger.info("smart resume: kept %d / skipped %d (input_hash unchanged)",
                len(kept), skipped)
    return kept


def _start_synthesis_run(tenant_id: str, cli_args: dict, triggered_by: str) -> str | None:
    try:
        row = query_one(
            "INSERT INTO synthesis_runs (tenant_id, cli_args, triggered_by) "
            "VALUES (%s, %s::jsonb, %s) RETURNING id",
            tenant_id, json.dumps(cli_args), triggered_by,
        )
        return str(row["id"]) if row else None
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.warning("cannot insert synthesis_runs row (continuing without tracking): %r", exc)
        return None


def _finish_synthesis_run(run_id: str | None, total_cost: float,
                          counts: dict, exit_status: str) -> None:
    if not run_id:
        return
    try:
        execute(
            "UPDATE synthesis_runs SET finished_at = NOW(), "
            "  total_cost_usd = %s, perspective_counts = %s::jsonb, "
            "  exit_status = %s WHERE id = %s",
            round(total_cost, 4), json.dumps(counts), exit_status, run_id,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.warning("cannot finalize synthesis_runs row %s: %r", run_id, exc)


def _cumulative_cost_24h(tenant_id: str) -> float:
    try:
        row = query_one(
            "SELECT coalesce(sum(total_cost_usd), 0)::float AS c "
            "FROM synthesis_runs "
            "WHERE tenant_id = %s "
            "  AND started_at > NOW() - interval '24 hours' "
            "  AND total_cost_usd IS NOT NULL",
            tenant_id,
        )
        return float(row["c"]) if row else 0.0
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        logger.warning("cumulative cost query failed (assuming 0): %r", exc)
        return 0.0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="exocortex-synth")
    ap.add_argument("--tenant", default=TENANT_ID, help="Tenant UUID (default $TENANT_ID).")
    ap.add_argument("--perspective", help="Limit to one perspective_type.")
    ap.add_argument("--key", help="Limit to one perspective_key (requires --perspective).")
    ap.add_argument("--domain", help="Restrict to a single domain (work/news/frp/...).")
    ap.add_argument("--all", action="store_true",
                    help="Discover and synthesize all perspectives meeting thresholds.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max syntheses to run (after discovery, useful for smoke tests).")
    ap.add_argument("--dry-run", action="store_true", help="Skip DB writes; print summaries.")
    ap.add_argument("--force", action="store_true",
                    help="Bypass input_hash idempotency, regenerate even if unchanged.")
    ap.add_argument("--missing-only", action="store_true",
                    help="F4.6.3: skip targets whose input_hash already matches an "
                         "active synthesis row (smart resume — fast no-op for daily cron).")
    ap.add_argument("--cost-stop", type=float, default=1.50,
                    help="Hard stop cumulative cost (this run only) in USD (default 1.50).")
    ap.add_argument("--cumulative-cost-stop", type=float, default=10.0,
                    help="F4.6.3: hard stop on 24h cumulative cost in USD across runs "
                         "(default 10.0). Defense vs accidental N×$cost-stop budget burn.")
    ap.add_argument("--print-content", action="store_true",
                    help="Print full synthesis JSON for each result (dry-run debug).")
    ap.add_argument("--debug", action="store_true", help="DEBUG-level logging.")
    ap.add_argument("--triggered-by", default="manual",
                    help='Free-form label for synthesis_runs.triggered_by (e.g. "cron").')
    args = ap.parse_args(list(argv) if argv is not None else None)

    _setup_logging(args.debug)

    if not args.tenant:
        logger.error("--tenant or $TENANT_ID required")
        return 2

    if args.key and not args.perspective:
        logger.error("--key requires --perspective")
        return 2

    logger.info("model=%s prompt_version=%s tenant=%s",
                LLM_MODEL, PROMPT_VERSION, args.tenant)
    logger.info("dry_run=%s force=%s missing_only=%s cost_stop=$%s cumulative_cost_stop=$%s",
                args.dry_run, args.force, args.missing_only,
                args.cost_stop, args.cumulative_cost_stop)

    if not args.dry_run and args.cumulative_cost_stop > 0:
        cum24 = _cumulative_cost_24h(args.tenant)
        if cum24 >= args.cumulative_cost_stop:
            logger.error(
                "24h cumulative cost $%.4f already >= cumulative-cost-stop $%.4f. "
                "Aborting before any LLM call.",
                cum24, args.cumulative_cost_stop,
            )
            return 3
        if cum24 > 0:
            logger.info("24h cumulative cost so far: $%.4f / $%.4f budget",
                        cum24, args.cumulative_cost_stop)

    targets: list[tuple[str, str]] = []
    if args.perspective and args.key:
        targets.append((args.perspective, args.key))
    elif args.perspective and not args.key:
        discovered = [(t, k) for t, k, _ in discover_perspectives(args.tenant)
                      if t == args.perspective]
        targets.extend(discovered)
    elif args.all or args.limit is not None:
        targets.extend([(t, k) for t, k, _ in discover_perspectives(args.tenant)])
    else:
        logger.error("provide --perspective + --key, --perspective, --all, or --limit")
        return 2

    if args.missing_only and not args.force:
        targets = _filter_missing_only(targets, args.tenant)
    elif args.missing_only and args.force:
        logger.warning("--missing-only ignored because --force is set (force re-runs everything).")

    if args.limit is not None:
        if args.limit < len(targets) and args.limit >= 3 and not args.perspective:
            by_type: dict[str, list[tuple[str, str]]] = {}
            for ptype, pkey in targets:
                by_type.setdefault(ptype, []).append((ptype, pkey))
            sampled: list[tuple[str, str]] = []
            for ptype in by_type:
                if sampled and len(sampled) >= args.limit:
                    break
                sampled.append(by_type[ptype][0])
            for ptype, items in by_type.items():
                for it in items[1:]:
                    if len(sampled) >= args.limit:
                        break
                    sampled.append(it)
            targets = sampled[:args.limit]
        else:
            targets = targets[:args.limit]

    logger.info("%d perspective(s) to process.", len(targets))

    run_id = None
    if not args.dry_run:
        cli_args_dict = {k: v for k, v in vars(args).items()
                         if k not in ("tenant",) and not k.startswith("_")}
        run_id = _start_synthesis_run(args.tenant, cli_args_dict, args.triggered_by)
        if run_id:
            logger.info("synthesis_runs.id=%s", run_id)

    total_cost = 0.0
    counts = {"ok": 0, "skipped": 0, "error": 0, "below-threshold": 0, "no-thoughts": 0}
    started = time.time()
    exit_status = "ok"

    try:
        for i, (ptype, pkey) in enumerate(targets, 1):
            source = select_source_thoughts(args.tenant, ptype, pkey)
            try:
                result = synthesize(ptype, pkey, source,
                                    tenant_id=args.tenant,
                                    dry_run=args.dry_run,
                                    force=args.force)
            except Exception as exc:
                logger.exception("[%d/%d] %s=%s unhandled exception: %r",
                                 i, len(targets), ptype, pkey, exc)  # noqa: TRY401 — message text kept unchanged
                counts["error"] += 1
                continue
            counts[result.status] += 1
            total_cost += result.cost_usd
            _log_result(result, total_cost, i, len(targets))

            if args.print_content and result.content:
                logger.info("content for %s=%s:\n%s", ptype, pkey,
                            json.dumps(result.content, ensure_ascii=False, indent=2))

            if total_cost > args.cost_stop:
                logger.error("COST STOP — cumulative this run $%.4f > $%.4f. Aborting.",
                             total_cost, args.cost_stop)
                exit_status = "cost_stop"
                break
    except KeyboardInterrupt:
        logger.error("interrupted by SIGINT")
        exit_status = "aborted"
    except Exception as exc:  # noqa: BLE001
        logger.error("fatal: %r\n%s", exc, traceback.format_exc())
        exit_status = "error"

    elapsed = time.time() - started
    logger.info("done in %.1fs. total cost $%.4f. counts=%s",
                elapsed, total_cost,
                " ".join(f"{k}={v}" for k, v in counts.items()))
    if args.dry_run:
        logger.info("DRY RUN — no DB writes performed.")
    else:
        _finish_synthesis_run(run_id, total_cost, counts, exit_status)

    from exocortex.pipeline_log import log_run_end, log_run_start
    _pl_id = log_run_start("synthesizer", dry_run=args.dry_run)
    log_run_end(_pl_id, "success" if exit_status == "ok" else "failure",
                counts=counts,
                cost_usd=total_cost if total_cost else None,
                error_message=f"synthesis exit_status={exit_status}" if exit_status != "ok" else None)

    return 0 if exit_status == "ok" else (3 if exit_status == "cost_stop" else 1)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
