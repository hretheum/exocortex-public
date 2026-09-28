-- R4.1 — provider_errors table (llm_router telemetry for failed calls).
-- Mirrors llm_provider_runs but for non-success calls.
-- One row per failed provider call. Used by R4 health monitoring + auto-failover.

-- Explicit search_path override removed 2026-07-28 — see
-- 18_llm_provider_runs.sql for why
-- it existed and why it's gone (db/pool.py's session default is public-first
-- now, so no override is needed to match it).

CREATE TABLE IF NOT EXISTS provider_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    provider TEXT NOT NULL,                    -- 'anthropic' | 'deepinfra' | 'openrouter'
    model TEXT,                                -- e.g. 'Qwen/Qwen3.5-397B-A17B'
    use_case TEXT,                             -- e.g. 'second_brain.F4_synthesis_client'
    status INTEGER,                            -- HTTP status code (0 = timeout)
    error_type TEXT,                           -- 'timeout', 'http_500', 'rate_limit', 'auth', 'unknown'
    error_message TEXT,
    fallback_chain TEXT[],                     -- providers tried before failure
    latency_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE provider_errors IS 'R4 — failed LLM provider calls. One row per error.';

CREATE INDEX IF NOT EXISTS idx_provider_errors_provider_ts
    ON provider_errors (tenant_id, provider, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_errors_use_case_ts
    ON provider_errors (tenant_id, use_case, started_at DESC);

GRANT INSERT, SELECT ON provider_errors TO second_brain;

