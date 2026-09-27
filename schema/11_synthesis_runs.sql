-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- F4.6.3.4 — synthesis_runs table for cumulative cost tracking across runs.
--
-- Each invocation of scripts/run_synthesizer.py inserts one row at start and
-- updates it at exit. `--cumulative-cost-stop` queries the last 24h sum to
-- abort early when daily budget is exceeded (defense vs accidental N×cost-stop).
--
-- exit_status: 'ok' (clean finish), 'cost_stop' (per-run cap hit),
--              'error' (unhandled exception), 'aborted' (SIGINT/manual kill).

CREATE TABLE IF NOT EXISTS synthesis_runs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID        NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    total_cost_usd      NUMERIC(10, 4),
    perspective_counts  JSONB,
    exit_status         TEXT        CHECK (exit_status IN ('ok', 'cost_stop', 'error', 'aborted')),
    cli_args            JSONB,
    triggered_by        TEXT
);

CREATE INDEX IF NOT EXISTS idx_synthesis_runs_tenant_started
    ON synthesis_runs (tenant_id, started_at DESC);

COMMENT ON TABLE synthesis_runs IS
    'F4.6.3 — one row per scripts/run_synthesizer.py invocation. '
    'Used by --cumulative-cost-stop to enforce 24h daily budget.';

