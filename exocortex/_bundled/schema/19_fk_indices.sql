-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- F19: Foreign key column indexes for referential integrity performance.
--
-- Missing FK indexes cause sequential scans on child tables when parent rows
-- are updated or deleted, leading to table locks and slow cascades.
-- All indexes are idempotent (IF NOT EXISTS) and safe to re-run.

-- thoughts.source_id → raw_sources(id)
CREATE INDEX IF NOT EXISTS idx_thoughts_source_id
  ON thoughts(source_id);

-- thoughts.superseded_by → thoughts(id) (append-only soft supersession)
CREATE INDEX IF NOT EXISTS idx_thoughts_superseded_by
  ON thoughts(superseded_by) WHERE superseded_by IS NOT NULL;

-- content_queue.source_id → raw_sources(id)
CREATE INDEX IF NOT EXISTS idx_content_queue_source_id
  ON content_queue(source_id);

-- frp_sessions.content_id → content_queue(id)
CREATE INDEX IF NOT EXISTS idx_frp_sessions_content_id
  ON frp_sessions(content_id);

-- frp_sessions.root_thought_id → thoughts(id)
CREATE INDEX IF NOT EXISTS idx_frp_sessions_root_thought_id
  ON frp_sessions(root_thought_id);

-- syntheses.superseded_by → syntheses(id) (append-only soft supersession)
CREATE INDEX IF NOT EXISTS idx_syntheses_superseded_by
  ON syntheses(superseded_by) WHERE superseded_by IS NOT NULL;

-- email_threads.summary_thought_id → thoughts(id)
CREATE INDEX IF NOT EXISTS idx_email_threads_summary_thought_id
  ON email_threads(summary_thought_id);

-- llm_provider_runs.shadow_for_run_id → llm_provider_runs(id)
CREATE INDEX IF NOT EXISTS idx_llm_provider_runs_shadow_for
  ON llm_provider_runs(shadow_for_run_id) WHERE shadow_for_run_id IS NOT NULL;

