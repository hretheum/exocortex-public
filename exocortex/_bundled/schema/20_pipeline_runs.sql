-- F14 — Pipeline runs telemetry table.
-- Single table for all worker metrics: compile, synth, rss, gmail, fireflies, etc.
-- Enables _home.md dashboard surfacing + "why did timer X fail silently" debugging.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    worker           TEXT NOT NULL,                     -- 'wiki_compiler', 'synthesizer', 'gmail', 'rss', 'fireflies', 'ingest'
    status           TEXT NOT NULL DEFAULT 'running',   -- 'running', 'success', 'failure'
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    counts           JSONB,                             -- e.g. {"fetched": 200, "created": 11, "error": 0}
    error_message    TEXT,                              -- tylko gdy status='failure'
    cost_usd         NUMERIC(10, 6),                    -- dla workerów LLM (synthesizer, wiki_compiler aggregator)
    input_hash       TEXT,                              -- SHA256 z input params dla idempotencji re-run
    runtime_seconds  NUMERIC(10, 3),                    -- finished_at - started_at (nullable pre-finish)
    UNIQUE (tenant_id, worker, input_hash)              -- idempotent re-run = no-op
);

COMMENT ON TABLE pipeline_runs IS 'F14 — per-worker run telemetry. One row per timer activation.';
COMMENT ON COLUMN pipeline_runs.worker IS 'worker name: wiki_compiler, synthesizer, gmail, rss, fireflies, ingest';
COMMENT ON COLUMN pipeline_runs.counts IS 'flexible JSONB: {\"fetched\": 200, \"created\": 11, \"errors\": 0, ...}';
COMMENT ON COLUMN pipeline_runs.input_hash IS 'SHA256 of (worker, input params) for idempotency. UNIQUE constraint makes re-run a no-op.';

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_worker_ts
    ON pipeline_runs (tenant_id, worker, started_at DESC);

GRANT INSERT, SELECT, UPDATE, DELETE ON pipeline_runs TO second_brain;

