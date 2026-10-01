# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/pipeline_log.py — F14 structured pipeline run telemetry.
#
# Workers call log_run_start() at entry, log_run_end() at exit. All pipeline_runs
# rows are then surfaced in _home.md via compile_home_module.
#
# Idempotent: input_hash is SHA256(worker + sorted args). UNIQUE constraint
# on (tenant_id, worker, input_hash) makes re-runs a no-op.

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from exocortex.db import insert_returning, query_one, update_where
from exocortex.settings import get_tenant_id

logger = logging.getLogger(__name__)

TENANT_ID = get_tenant_id()


def _make_hash(worker: str, **kwargs: Any) -> str:
    """Stable input hash for idempotency (re-run within same hour = no-op).

    Includes current hour so each hourly run gets a unique hash, but retries
    within the same hour are deduped.
    """
    hour_key = datetime.now(UTC).strftime('%Y-%m-%dT%H')
    payload = json.dumps(
        [worker, hour_key, sorted(kwargs.items())],
        sort_keys=True, default=str, ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()[:16]


def log_run_start(worker: str, **input_kwargs: Any) -> str | None:
    """Insert pipeline_runs row with status='running'. Returns run_id or None if idempotent skip."""
    if not TENANT_ID:
        return None
    ihash = _make_hash(worker, **input_kwargs)
    try:
        row = insert_returning('pipeline_runs', {
            'tenant_id': TENANT_ID,
            'worker': worker,
            'status': 'running',
            'started_at': datetime.now(UTC),
            'input_hash': ihash,
        }, returning='id')
        return str(row['id'])
    except Exception:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        return None


def log_run_end(
    run_id: str,
    status: str,
    counts: dict[str, int] | None = None,
    error_message: str | None = None,
    cost_usd: float | None = None,
) -> None:
    """Finalise pipeline_runs row with end-of-run stats.

    Args:
        status: 'success' or 'failure'
        counts: e.g. {'fetched': 200, 'created': 11, 'unchanged': 189, 'error': 0}
        error_message: only when status='failure'
        cost_usd: total cost of the run (for LLM workers)
    """
    if not run_id or not TENANT_ID:
        return
    now = datetime.now(UTC)
    row = query_one('SELECT started_at FROM pipeline_runs WHERE id = %s AND status = %s',
                    run_id, 'running')
    if not row:
        return
    runtime_seconds = None
    if row.get('started_at'):
        runtime_seconds = (now - row['started_at']).total_seconds()
    data: dict[str, Any] = {
        'status': status,
        'finished_at': now,
        'runtime_seconds': runtime_seconds,
    }
    if counts:
        data['counts'] = json.dumps(counts)
    if error_message:
        data['error_message'] = error_message[:2000]
    if cost_usd is not None:
        data['cost_usd'] = cost_usd
    update_where('pipeline_runs', data, 'id = %s', run_id)


@contextmanager
def pipeline_run(worker: str, **input_kwargs: Any):
    """Context manager wrapping a worker run with telemetry.

    Usage:
        with pipeline_run('gmail', mode='newsletter', max_messages=200) as ctx:
            counts = fetch_newsletters_once(...)
            ctx['counts'] = counts
            ctx['cost_usd'] = 0.0
            # On exception: auto-logged as 'failure'
    """
    ctx: dict[str, Any] = {}
    run_id: str | None = None
    error_msg: str | None = None
    try:
        run_id = log_run_start(worker, **input_kwargs)
        ctx['run_id'] = run_id
        yield ctx
    except Exception as exc:
        error_msg = f'{type(exc).__name__}: {exc}'
        logger.error('[pipeline_log] %s failed: %s', worker, error_msg)
        raise
    finally:
        if run_id:
            status = 'failure' if error_msg else 'success'
            log_run_end(
                run_id, status,
                counts=ctx.get('counts'),
                error_message=error_msg or ctx.get('error'),
                cost_usd=ctx.get('cost_usd'),
            )
