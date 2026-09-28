-- Deterministic measurement rig for
-- comparing claim-extraction configurations (M3). The rig is NOT
-- model-orchestrated: these tables are plain data structure, and the work loop
-- (scripts/bench_rig.py) is ordinary code with no LLM call in the
-- control loop itself.
--
-- Deliberately SEPARATE from production `thoughts`/`edges` (schema/01_base.sql)
-- — this rig NEVER writes to the graph. Claim candidates go
-- only to bench_claims, not to `thoughts`. That makes reverting
-- trivial (DELETE by config_id/job, zero graph orphans by definition) and
-- avoids a known gap from an earlier run:
-- this rig creates nothing that would have to be removed from the graph.

-- Configuration matrix as DATA, not a list of calls in a script
-- — adding a configuration = INSERT, zero changes to the loop.
CREATE TABLE IF NOT EXISTS bench_configs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL UNIQUE,          -- e.g. 'terse-qwen36-doc'
    use_case       TEXT NOT NULL,                 -- routing key second_brain.F_bench_*
    prompt_variant TEXT NOT NULL,                 -- key into PROMPT_VARIANTS in extract_claims.py
    granularity    TEXT NOT NULL CHECK (granularity IN ('document', 'chunk')),
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Named document samples (tuning / control) — stored as data,
-- queryable, instead of a list of UUIDs hard-coded in the code.
CREATE TABLE IF NOT EXISTS bench_samples (
    sample_name  TEXT NOT NULL,          -- 'tuning-20' | 'control-10'
    document_id  UUID NOT NULL,          -- thoughts.id (thought_type='vault_note')
    added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sample_name, document_id)
);

-- Job queue: one row = one text unit (a document OR a
-- chunk) run through one configuration. The same job shape
-- for both granularities; aggregation to document level happens
-- in analysis (M6), not in the queue itself.
CREATE TABLE IF NOT EXISTS bench_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id     UUID NOT NULL REFERENCES bench_configs(id) ON DELETE CASCADE,
    sample_name   TEXT NOT NULL,
    document_id   UUID NOT NULL,                  -- always the parent document (aggregation)
    unit_type     TEXT NOT NULL CHECK (unit_type IN ('document', 'chunk')),
    unit_id       UUID NOT NULL,                  -- thoughts.id or thought_chunks.id
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'in_progress', 'done', 'error', 'skipped')),
    owner         TEXT,
    lease_until   TIMESTAMPTZ,
    attempts      INT NOT NULL DEFAULT 0,
    max_attempts  INT NOT NULL DEFAULT 2,          -- retry only on an unexpected rig exception, NOT on ExtractionCallError (see bench_rig.py)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    UNIQUE (config_id, unit_type, unit_id)         -- reloading the same matrix = no-op
);

CREATE INDEX IF NOT EXISTS idx_bench_jobs_claimable
    ON bench_jobs (status, lease_until);

-- Result aggregated at the level of one job (one document/chunk x
-- one configuration). Cost/provider telemetry FIXED compared
-- to the previous run: provider_actual comes from the actual resolved base_url
-- (RoutingConfig.providers[...].base_url), not from the alias label
-- 'deepinfra', which says nothing about whether the call was actually
-- local or remote.
CREATE TABLE IF NOT EXISTS bench_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id            UUID NOT NULL UNIQUE REFERENCES bench_jobs(id) ON DELETE CASCADE,
    reliability_ok    BOOLEAN NOT NULL,             -- False = the extraction call raised ExtractionCallError
    error_reason      TEXT,
    extracted_count   INT NOT NULL DEFAULT 0,
    grounded_count    INT NOT NULL DEFAULT 0,
    proposition_count INT NOT NULL DEFAULT 0,
    redundant_count   INT NOT NULL DEFAULT 0,
    usable_count      INT NOT NULL DEFAULT 0,
    provider          TEXT,                        -- alias from llm_router (e.g. 'deepinfra')
    model             TEXT,
    provider_actual   TEXT,                        -- 'local' | 'remote', from the resolved base_url
    base_url          TEXT,
    use_case          TEXT,
    input_tokens      INT NOT NULL DEFAULT 0,
    output_tokens     INT NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    latency_ms        INT NOT NULL DEFAULT 0,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bench_results_job
    ON bench_results (job_id);

-- Raw result at the level of a SINGLE claim candidate. Without
-- this, the previous run could not be analyzed by document type without
-- re-running it. Every decision
-- of every filter is stored explicitly, so the analysis (M6) reads only from the DB.
CREATE TABLE IF NOT EXISTS bench_claims (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         UUID NOT NULL REFERENCES bench_jobs(id) ON DELETE CASCADE,
    claim_text     TEXT NOT NULL,
    quote          TEXT,
    is_grounded    BOOLEAN NOT NULL,
    is_proposition BOOLEAN,                        -- NULL = not checked (rejected earlier at grounding)
    is_redundant   BOOLEAN,                        -- NULL = not checked (rejected earlier)
    is_usable      BOOLEAN NOT NULL,
    rejection_reason TEXT,                         -- 'not_grounded' | 'not_proposition' | 'redundant' | NULL (usable)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bench_claims_job
    ON bench_claims (job_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON bench_configs, bench_samples, bench_jobs,
    bench_results, bench_claims TO second_brain;
