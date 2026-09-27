-- F-llm-router-integration — telemetry table for llm_router Usage records.
-- One row per LLM provider call. Privacy-by-construction: Usage never carries
-- prompt content, so this table never stores user/system prompts either.
--
-- Explicit `SET search_path = ag_catalog, public` removed 2026-07-28: it was
-- a deliberate workaround matching db/pool.py's (then ag_catalog-first)
-- session default, so this table wouldn't land in a DIFFERENT schema than
-- the app's own inserts. That default was the actual bug (2026-07-28
-- incident — every unqualified CREATE TABLE across schema/*.sql silently
-- went to ag_catalog). Both are now public-first; no override needed here.
-- See docs/incidenty/2026-07-28-schema.md.

CREATE TABLE IF NOT EXISTS llm_provider_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    use_case TEXT NOT NULL,
    provider TEXT NOT NULL,                    -- 'anthropic' | 'deepinfra' | 'openrouter'
    model TEXT NOT NULL,                       -- e.g. 'claude-haiku-4-5-20251001'
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL,
    fallback_chain TEXT[] NOT NULL DEFAULT '{}',
    -- Reserved for Phase 2 shadow mode (NULL when not a shadow run).
    shadow_for_run_id UUID REFERENCES llm_provider_runs(id) ON DELETE SET NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_provider_runs_tenant_started
    ON llm_provider_runs (tenant_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_provider_runs_use_case_started
    ON llm_provider_runs (use_case, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_provider_runs_provider
    ON llm_provider_runs (provider, started_at DESC);

GRANT SELECT, INSERT, UPDATE ON llm_provider_runs TO second_brain;

