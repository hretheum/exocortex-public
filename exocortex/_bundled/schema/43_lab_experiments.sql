-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/43_lab_experiments.sql — lab experiment tables (roadmap task F2.6).
--
-- A general version of the extraction bench (37..39): the same queue with
-- leases and attempts and the same record of model, provider (local or
-- remote), tokens, cost and latency per job, but results are JSON, so a new
-- kind of experiment needs no schema change. Samples carry their seed, a
-- checksum of their members and a data class; in the lab the only class
-- allowed is 'public'. A control sample can be opened by one run per
-- hypothesis version; the database refuses a second one.
--
-- Nothing here references the engine's content tables. Items are stable
-- text ids (for example an arXiv id), so every number can be recomputed
-- from the published data alone.

CREATE TABLE IF NOT EXISTS experiments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    kind             TEXT NOT NULL,                 -- runner key, e.g. 'toy', 'claims'
    title            TEXT NOT NULL,
    hypothesis_slug  TEXT,                          -- NULL for tests of the machinery itself
    params           JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS exp_configs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id  UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    name           TEXT NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9.-]*$'),
    model          TEXT,                            -- NULL when no model is involved
    provider       TEXT NOT NULL DEFAULT 'none' CHECK (provider IN ('local', 'remote', 'none')),
    variant        TEXT NOT NULL DEFAULT '',
    params         JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (experiment_id, name)
);

CREATE TABLE IF NOT EXISTS exp_samples (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id   UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    name            TEXT NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9-]*$'),
    role            TEXT NOT NULL CHECK (role IN ('tuning', 'control', 'pilot', 'test', 'blind')),
    seed            BIGINT NOT NULL,
    method          TEXT NOT NULL,                  -- how the members were drawn
    data_class      TEXT NOT NULL CHECK (data_class = 'public'),
    members_sha256  TEXT NOT NULL,                  -- over "item_id content_sha256" lines, sorted by item_id
    size            INT NOT NULL CHECK (size >= 0),
    touched_at      TIMESTAMPTZ,                    -- when a run first read a control sample
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (experiment_id, name)
);

CREATE TABLE IF NOT EXISTS exp_sample_items (
    sample_id       UUID NOT NULL REFERENCES exp_samples(id) ON DELETE CASCADE,
    item_id         TEXT NOT NULL,
    content_sha256  TEXT NOT NULL,
    stratum         TEXT,
    position        INT NOT NULL,                   -- order of the draw
    payload         JSONB NOT NULL DEFAULT '{}',    -- what a person sees, for blind samples
    PRIMARY KEY (sample_id, item_id)
);

CREATE TABLE IF NOT EXISTS exp_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id       UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    run_id              TEXT NOT NULL CHECK (run_id ~ '^run-[0-9a-z-]+$'),
    sample_id           UUID NOT NULL REFERENCES exp_samples(id),
    hypothesis_version  INT,
    prereg_hash         TEXT,
    code_commit         TEXT,
    status              TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    UNIQUE (experiment_id, run_id)
);

-- One row per control sample and hypothesis version that a run has read.
-- The primary key is the lock: a second run on the same control sample for
-- the same version fails inside the database.
CREATE TABLE IF NOT EXISTS exp_control_openings (
    sample_id           UUID NOT NULL REFERENCES exp_samples(id) ON DELETE CASCADE,
    hypothesis_version  INT NOT NULL,
    run_id              UUID NOT NULL REFERENCES exp_runs(id) ON DELETE CASCADE,
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sample_id, hypothesis_version)
);

CREATE OR REPLACE FUNCTION exp_open_control_sample() RETURNS trigger AS $$
DECLARE
    sample_role TEXT;
BEGIN
    SELECT role INTO sample_role FROM exp_samples WHERE id = NEW.sample_id;
    IF sample_role = 'control' THEN
        IF NEW.hypothesis_version IS NULL THEN
            RAISE EXCEPTION 'a run on a control sample needs a hypothesis version'
                USING ERRCODE = 'check_violation';
        END IF;
        INSERT INTO exp_control_openings (sample_id, hypothesis_version, run_id)
            VALUES (NEW.sample_id, NEW.hypothesis_version, NEW.id);
        UPDATE exp_samples SET touched_at = COALESCE(touched_at, NOW()) WHERE id = NEW.sample_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_exp_runs_open_control ON exp_runs;
CREATE TRIGGER trg_exp_runs_open_control
    AFTER INSERT ON exp_runs
    FOR EACH ROW EXECUTE FUNCTION exp_open_control_sample();

-- One row = one item run through one configuration within a run.
CREATE TABLE IF NOT EXISTS exp_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        UUID NOT NULL REFERENCES exp_runs(id) ON DELETE CASCADE,
    config_id     UUID NOT NULL REFERENCES exp_configs(id) ON DELETE CASCADE,
    item_id       TEXT NOT NULL,
    model         TEXT,                             -- copied from the config: the queue groups by it
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'in_progress', 'done', 'error')),
    owner         TEXT,
    lease_until   TIMESTAMPTZ,
    attempts      INT NOT NULL DEFAULT 0,
    max_attempts  INT NOT NULL DEFAULT 2,           -- retries cover crashes, not invalid model output
    last_error    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    UNIQUE (run_id, config_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_exp_jobs_claimable ON exp_jobs (status, model, lease_until);

CREATE TABLE IF NOT EXISTS exp_results (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         UUID NOT NULL UNIQUE REFERENCES exp_jobs(id) ON DELETE CASCADE,
    run_id         UUID NOT NULL REFERENCES exp_runs(id) ON DELETE CASCADE,
    config_id      UUID NOT NULL REFERENCES exp_configs(id) ON DELETE CASCADE,
    item_id        TEXT NOT NULL,
    ok             BOOLEAN NOT NULL,                -- false: no valid output for this item (a measured outcome)
    error_reason   TEXT,
    output         JSONB NOT NULL DEFAULT '{}',     -- shape decided by the experiment kind
    model          TEXT,
    provider       TEXT,                            -- 'local' | 'remote' | 'none'
    base_url       TEXT,
    input_tokens   INT NOT NULL DEFAULT 0,
    output_tokens  INT NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(10, 6) NOT NULL DEFAULT 0,
    latency_ms     INT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exp_results_run ON exp_results (run_id, config_id);

-- Numbers that gate decisions and pages cite. result_id is readable and
-- stable: <experiment>/<run>/<config or "diff">/<metric>.
CREATE TABLE IF NOT EXISTS exp_metrics (
    result_id    TEXT PRIMARY KEY,
    run_id       UUID NOT NULL REFERENCES exp_runs(id) ON DELETE CASCADE,
    config_id    UUID REFERENCES exp_configs(id) ON DELETE CASCADE,  -- NULL for a comparison of configs
    metric       TEXT NOT NULL,
    value        DOUBLE PRECISION,
    ci_low       DOUBLE PRECISION,
    ci_high      DOUBLE PRECISION,
    n            INT,
    method       TEXT,                              -- 'wilson', 'bootstrap-by-item', 'mean', ...
    details      JSONB NOT NULL DEFAULT '{}',
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Human judgments of blind sample items (F3.5). Raters appear under
-- pseudonyms only.
CREATE TABLE IF NOT EXISTS exp_judgments (
    sample_id    UUID NOT NULL,
    item_id      TEXT NOT NULL,
    rater        TEXT NOT NULL CHECK (rater ~ '^[a-z0-9-]+$'),
    labels       TEXT[] NOT NULL,
    source_mode  TEXT,
    comment      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sample_id, item_id, rater),
    FOREIGN KEY (sample_id, item_id) REFERENCES exp_sample_items(sample_id, item_id) ON DELETE CASCADE,
    CHECK (labels <@ ARRAY['correct', 'mode_swap', 'number_or_name', 'other_error']::TEXT[]
           AND cardinality(labels) >= 1)
);
