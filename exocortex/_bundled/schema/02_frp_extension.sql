-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- FRP-specific tables

-- Content queue (URL + metadata + AI score, no text)
CREATE TABLE content_queue (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            UUID NOT NULL,
  source_id            UUID REFERENCES raw_sources(id),

  -- AI scoring on metadata + max 150-word excerpt (not stored)
  score_accessibility  INTEGER CHECK (score_accessibility BETWEEN 0 AND 3),
  score_horizon        INTEGER CHECK (score_horizon BETWEEN 0 AND 3),
  score_consequence    INTEGER CHECK (score_consequence BETWEEN 0 AND 3),
  score_total          INTEGER GENERATED ALWAYS AS
                       (score_accessibility + score_horizon + score_consequence)
                       STORED,

  suggested_prompt     TEXT,    -- e.g. 'P2.1'
  scenario_sentence    TEXT,    -- user's own one-sentence summary (added after reading)
  ai_tags              JSONB,   -- {domain:[], tech:[], change_type:[]}
  ai_rejection_reason  TEXT,

  status  TEXT DEFAULT 'queued'
          CHECK (status IN ('queued', 'reading', 'used', 'skipped')),
  queued_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_cq_tenant_status
  ON content_queue(tenant_id, status, score_total DESC);

-- FRP session metadata (graph anchor)
CREATE TABLE frp_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL,
  content_id       UUID REFERENCES content_queue(id),

  frame            TEXT CHECK (frame IN ('A', 'B', 'C')),
  level            INTEGER CHECK (level BETWEEN 1 AND 3),
  resonance        INTEGER CHECK (resonance BETWEEN 1 AND 5),

  root_thought_id  UUID REFERENCES thoughts(id),
  context_note     TEXT,    -- one sentence: current professional context

  revisit_due      DATE,
  revisited_at     TIMESTAMPTZ,
  status           TEXT DEFAULT 'active'
                   CHECK (status IN ('active', 'revisited', 'archived')),

  created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_frp_sessions_tenant ON frp_sessions(tenant_id, status);
CREATE INDEX idx_frp_sessions_revisit
  ON frp_sessions(tenant_id, revisit_due)
  WHERE status = 'active' AND revisit_due IS NOT NULL;

