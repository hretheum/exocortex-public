-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/08_syntheses.sql — F4.1: append-only syntheses produced by workers/synthesizer.py.
-- One row per (perspective_type, perspective_key, prompt_version) at any moment;
-- re-synthesis writes a new row and points the previous active row's superseded_by
-- at it (NEVER UPDATE/DELETE old rows). The "at most one active" invariant is
-- enforced by partial UNIQUE index `uq_syntheses_active` (history rows are
-- unconstrained). Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS syntheses (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  perspective_type  text NOT NULL CHECK (perspective_type IN ('client','project','person','monthly','tag','type')),
  perspective_key   text NOT NULL,
  content           jsonb NOT NULL,
  source_thought_ids uuid[] NOT NULL,
  input_hash        text NOT NULL,
  llm_tokens_used   int,
  llm_cost_usd      numeric(10,6),
  model             text DEFAULT 'claude-haiku-4-5-20251001',
  prompt_version    int  DEFAULT 1,
  generated_at      timestamptz DEFAULT now(),
  -- DEFERRABLE so persist_synthesis() can UPDATE old.superseded_by = new_uuid
  -- BEFORE the matching INSERT runs (avoids tripping uq_syntheses_active during
  -- the supersede transition).
  superseded_by     uuid REFERENCES syntheses(id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_syntheses_perspective
  ON syntheses(tenant_id, perspective_type, perspective_key);

-- Partial UNIQUE: at most one ACTIVE synthesis per (tenant, type, key, version).
-- Superseded history rows are unconstrained — append-only is intact.
-- Doubles as the index for active-row lookups (filter `WHERE superseded_by IS NULL`).
CREATE UNIQUE INDEX IF NOT EXISTS uq_syntheses_active
  ON syntheses(tenant_id, perspective_type, perspective_key, prompt_version)
  WHERE superseded_by IS NULL;

GRANT ALL ON TABLE syntheses TO second_brain;

