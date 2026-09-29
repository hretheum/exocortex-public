-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/16_cross_domain_matches.sql — F8.8.x.G T2: thematic cross-domain
-- matching sidecar. Stores LLM judgments per (client_synthesis × cluster_synthesis)
-- pair. Score >=6 also emits a `cross_references` edge whose UUID is captured
-- in `edge_id` (nullable: <6 logged but no edge).
--
-- Apply on the server: sudo -u postgres psql -d second_brain -f /tmp/16_cross_domain_matches.sql
--
-- Idempotency: UNIQUE (client_synthesis_id, cluster_synthesis_id, prompt_version)
-- + ON CONFLICT DO NOTHING. Re-runs are no-ops while the same prompt_version key
-- (which embeds client/cluster input_hash) is current.

CREATE TABLE IF NOT EXISTS cross_domain_matches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  edge_id UUID,
  tenant_id UUID NOT NULL,
  client_synthesis_id UUID NOT NULL,
  cluster_synthesis_id UUID NOT NULL,
  prompt_version TEXT NOT NULL,
  relevance_score INT NOT NULL CHECK (relevance_score BETWEEN 0 AND 10),
  reason TEXT NOT NULL CHECK (length(reason) <= 200),
  judged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  llm_cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
  CONSTRAINT uq_match UNIQUE (client_synthesis_id, cluster_synthesis_id, prompt_version)
);

CREATE INDEX IF NOT EXISTS idx_cdm_client_score
  ON cross_domain_matches (client_synthesis_id, relevance_score DESC);

CREATE INDEX IF NOT EXISTS idx_cdm_cluster
  ON cross_domain_matches (cluster_synthesis_id);

CREATE INDEX IF NOT EXISTS idx_cdm_tenant
  ON cross_domain_matches (tenant_id);

-- App user grant — `syntheses` is owned by `postgres` (F4.1), but the app user
-- needs DML on this sidecar. Idempotent via IF EXISTS guards.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'second_brain') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON cross_domain_matches TO second_brain';
  END IF;
END $$;

