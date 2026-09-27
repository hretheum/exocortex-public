-- ─────────────────────────────────────────────────────────────────
-- F22.5: Query telemetry — Phase 1 (logging only, no graph integration)
-- ─────────────────────────────────────────────────────────────────
-- Created: 2026-05-12
-- Purpose: Log every question asked of the knowledge system.
-- Scope: Phase 1 — telemetry/analytics only. Phase 2 (Question entities
--        in graph) and Phase 3 (Answer promotion) come later.
-- ─────────────────────────────────────────────────────────────────

-- Main query log
CREATE TABLE IF NOT EXISTS query_log (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL,
  asked_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Question content
  question            TEXT NOT NULL,
  question_hash       TEXT GENERATED ALWAYS AS (md5(question)) STORED,
  question_embedding  vector(1536),

  -- Source identification
  source              TEXT NOT NULL,         -- 'claude_desktop_mcp', 'graph_rag_api', 'chat_claude_ai', 'slack_bot'
  user_id             TEXT,                  -- hashed token, never PII
  token_hash          TEXT,                  -- joins with mcp_access_tokens (future)

  -- Scope (which client data was accessible)
  scope               TEXT[] DEFAULT ARRAY['internal']::TEXT[],
  -- ['acme'] for ACME team, ['internal'] for agency, etc.

  -- Retrieval results (audit trail of what we served)
  retrieved_node_ids  UUID[],
  retrieved_count     INT,
  retrieval_method    TEXT,                  -- 'vector', 'graph', 'hybrid', 'keyword'

  -- Performance
  latency_ms          INT,
  tokens_in           INT,
  tokens_out          INT,
  cost_usd            NUMERIC(10,6) DEFAULT 0,

  -- Status & future Phase 2 hooks
  status              TEXT DEFAULT 'logged'
                      CHECK (status IN ('logged', 'saved_as_question', 'promoted_to_source', 'rejected', 'archived')),
  promoted_to_source_id UUID,                -- if user saves answer to vault (Phase 3)
  user_feedback       TEXT,                  -- 'thumbs_up', 'thumbs_down', or free text

  -- Metadata
  conversation_id     TEXT,                  -- to group related queries from same session
  retry_of            UUID REFERENCES query_log(id)  -- if user retried a failed query
);

CREATE INDEX IF NOT EXISTS idx_query_log_asked
  ON query_log(asked_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_source
  ON query_log(source, asked_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_scope
  ON query_log USING GIN(scope);
CREATE INDEX IF NOT EXISTS idx_query_log_status
  ON query_log(status) WHERE status != 'logged';
CREATE INDEX IF NOT EXISTS idx_query_log_user
  ON query_log(user_id, asked_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_query_log_question_hash
  ON query_log(question_hash);

-- pgvector index for similarity search on questions (Phase 2 prep)
CREATE INDEX IF NOT EXISTS idx_query_log_embedding
  ON query_log USING ivfflat (question_embedding vector_cosine_ops)
  WITH (lists = 100);

-- Scoped access tokens (for cross-client team access)
CREATE TABLE IF NOT EXISTS mcp_access_tokens (
  token_hash          TEXT PRIMARY KEY,       -- SHA256 of actual token
  granted_to          TEXT NOT NULL,          -- 'acme-coe-team', 'eryk-personal', etc.
  scopes              TEXT[] NOT NULL,        -- ['acme'] or ['acme','tyrell','internal']

  -- Capability flags
  allow_full_text_search  BOOLEAN DEFAULT TRUE,
  allow_graph_traversal   BOOLEAN DEFAULT TRUE,
  allow_external_links    BOOLEAN DEFAULT FALSE,
  allow_promote_to_source BOOLEAN DEFAULT FALSE,  -- can save answers as new sources

  -- Rate limiting
  rate_limit_per_hour     INT DEFAULT 100,
  rate_limit_per_day      INT DEFAULT 1000,

  -- Lifecycle
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  expires_at          TIMESTAMPTZ,
  last_used_at        TIMESTAMPTZ,
  revoked_at          TIMESTAMPTZ,
  revoked_reason      TEXT,

  -- Annotations
  notes               TEXT,                   -- free-form description
  contact_email       TEXT
);

CREATE INDEX IF NOT EXISTS idx_mcp_tokens_active
  ON mcp_access_tokens(token_hash) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_mcp_tokens_granted
  ON mcp_access_tokens(granted_to);
CREATE INDEX IF NOT EXISTS idx_mcp_tokens_scopes
  ON mcp_access_tokens USING GIN(scopes);

-- Daily aggregation view (for dashboards)
CREATE OR REPLACE VIEW query_log_daily AS
SELECT
  date_trunc('day', asked_at) AS day,
  source,
  unnest(scope) AS scope_unnested,
  count(*) AS total_queries,
  count(DISTINCT user_id) AS unique_users,
  avg(latency_ms)::int AS avg_latency_ms,
  sum(tokens_in) AS total_tokens_in,
  sum(tokens_out) AS total_tokens_out,
  sum(cost_usd) AS total_cost_usd,
  count(*) FILTER (WHERE retrieved_count = 0) AS zero_result_queries,
  count(*) FILTER (WHERE user_feedback = 'thumbs_up') AS positive_feedback,
  count(*) FILTER (WHERE user_feedback = 'thumbs_down') AS negative_feedback
FROM query_log
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 2, 3;

-- Top retrieved nodes (which docs are most valuable?)
CREATE OR REPLACE VIEW top_retrieved_nodes_30d AS
SELECT
  unnest(retrieved_node_ids) AS node_id,
  count(*) AS retrieval_count,
  count(DISTINCT user_id) AS unique_users,
  min(asked_at) AS first_retrieved,
  max(asked_at) AS last_retrieved
FROM query_log
WHERE asked_at > NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 2 DESC;

-- App user grant — match other tables' pattern (F8.8 example)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'second_brain') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON query_log TO second_brain';
    EXECUTE 'GRANT SELECT ON mcp_access_tokens TO second_brain';
    EXECUTE 'GRANT SELECT ON query_log_daily TO second_brain';
    EXECUTE 'GRANT SELECT ON top_retrieved_nodes_30d TO second_brain';
  END IF;
END $$;
