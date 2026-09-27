-- F16 — live_section_runs table (telemetry for auto-updating sections).
-- One row per execution of a live section trigger.

-- Explicit search_path override removed 2026-07-28 — see
-- docs/incidenty/2026-07-28-schema.md and 18_llm_provider_runs.sql for why
-- it existed and why it's gone (db/pool.py's session default is public-first
-- now, so no override is needed to match it).

CREATE TABLE IF NOT EXISTS live_section_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    file_path TEXT NOT NULL,
    section_id TEXT NOT NULL,
    trigger_type TEXT NOT NULL,       -- 'cron' | 'window' | 'event' | 'manual'
    event_source TEXT,                 -- NULL for cron/window
    status TEXT NOT NULL,              -- 'success' | 'skipped' | 'error'
    content_before_hash TEXT,
    content_after_hash TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ DEFAULT NOW(),
    inserted_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE live_section_runs IS 'F16 — live section trigger execution telemetry';

CREATE INDEX IF NOT EXISTS idx_live_section_runs_file_section
    ON live_section_runs (tenant_id, file_path, section_id, started_at DESC);

GRANT INSERT, SELECT ON live_section_runs TO second_brain;

