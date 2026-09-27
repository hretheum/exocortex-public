-- F31.2.1 — resurfacing_state table.
-- Per-thought SM2 (SuperMemo 2) scheduling state for the Resurfacing Engine.
-- One row per thought; FK ON DELETE CASCADE keeps state in sync with thoughts.
-- Idempotent (safe to re-run).

CREATE TABLE IF NOT EXISTS resurfacing_state (
    thought_id        UUID        PRIMARY KEY REFERENCES thoughts(id) ON DELETE CASCADE,
    tenant_id         UUID        NOT NULL,
    sm2_interval      INT         NOT NULL DEFAULT 1,
    sm2_repetitions   INT         NOT NULL DEFAULT 0,
    sm2_efactor       FLOAT       NOT NULL DEFAULT 2.5,
    last_surfaced_at  TIMESTAMPTZ,
    next_surface_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    surface_count     INT         NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resurfacing_next_surface
    ON resurfacing_state (next_surface_at);

CREATE INDEX IF NOT EXISTS idx_resurfacing_last_surfaced
    ON resurfacing_state (last_surfaced_at);

GRANT ALL ON TABLE resurfacing_state TO second_brain;

COMMENT ON TABLE resurfacing_state IS
    'F31.2.1 — SM2 scheduling state per thought for the Resurfacing Engine.';
