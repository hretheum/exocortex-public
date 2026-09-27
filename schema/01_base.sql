-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- Base Open Brain tables

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Metadata of sources (no full text — copyright requirement)
CREATE TABLE raw_sources (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL,
  uri          TEXT NOT NULL,          -- URL to the original work
  title        TEXT,                   -- title of the work
  author_name  TEXT,                   -- author name (if known)
  word_count   INTEGER,                -- estimated length
  published_at DATE,
  source_name  TEXT,                   -- "365tomorrows", "Clarkesworld", etc.
  -- NO content, full_text, or content_hash of text
  -- Metadata only — copyright requirement
  ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata     JSONB                   -- tags, genre, additional metadata
);
CREATE INDEX idx_raw_sources_tenant ON raw_sources(tenant_id);
CREATE INDEX idx_raw_sources_uri ON raw_sources(uri);

-- Atomic user thoughts (user's own writing — no third-party text)
CREATE TABLE thoughts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL,
  source_id     UUID REFERENCES raw_sources(id), -- link to source, not its text
  body          TEXT NOT NULL,           -- user's own thought or reflection
  embedding     VECTOR(1536),            -- embedding of user's own text only
  confidence    NUMERIC(3,2),
  author        TEXT,                    -- 'human:X' | 'agent:claude'
  thought_type  TEXT DEFAULT 'generic',
  metadata      JSONB DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  superseded_by UUID REFERENCES thoughts(id) NULL
);
CREATE INDEX idx_thoughts_tenant ON thoughts(tenant_id);
CREATE INDEX idx_thoughts_type ON thoughts(tenant_id, thought_type);
CREATE INDEX idx_thoughts_embedding ON thoughts
  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_thoughts_fts ON thoughts
  USING gin(to_tsvector('english', body));

-- Canonical entities (concepts, persons, projects, devices, etc.)
CREATE TABLE entities (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL,
  canonical_name TEXT NOT NULL,
  type           TEXT NOT NULL,
  aliases        TEXT[],
  description    TEXT,
  UNIQUE (tenant_id, canonical_name)
);

-- Typed relationships between nodes
CREATE TYPE edge_type AS ENUM (
  -- Open Brain base
  'broader_than', 'narrower_than', 'related_to', 'used_for',
  'supports', 'contradicts', 'supersedes', 'derived_from',
  -- FRP
  'session_contains', 'reflects_on', 'signals_domain',
  'revisits', 'materializes_as',
  -- Work
  'attended_meeting', 'owns_project', 'decided_in', 'blocked_by',
  -- 3D Printing
  'printed_with', 'printed_on', 'used_profile', 'model_of', 'solves',
  -- Home Automation
  'located_in', 'uses_integration', 'triggers', 'depends_on',
  -- Cross-domain
  'cross_domain_instance'
);

CREATE TABLE edges (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  UUID NOT NULL,
  src_id     UUID NOT NULL,
  src_type   TEXT NOT NULL,   -- 'thought' | 'entity' | 'raw_source'
  dst_id     UUID NOT NULL,
  dst_type   TEXT NOT NULL,
  type       edge_type NOT NULL,
  confidence NUMERIC(3,2),
  created_by TEXT,
  resolved   BOOLEAN DEFAULT FALSE,  -- for 'contradicts' edges
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_edges_src ON edges(tenant_id, src_id, type);
CREATE INDEX idx_edges_dst ON edges(tenant_id, dst_id, type);

-- Compilation audit log
CREATE TABLE compile_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,
  triggered_by    TEXT,              -- 'cron' | 'manual' | 'webhook'
  domain          TEXT,              -- 'frp' | 'work' | '3d' | 'ha' | 'cross' | 'all'
  schema_version  TEXT,
  input_hash      TEXT,
  pages_written   TEXT[],
  pages_skipped   TEXT[],
  llm_tokens_used INTEGER,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ
);

