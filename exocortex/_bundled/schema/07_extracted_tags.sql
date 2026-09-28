-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/07_extracted_tags.sql — F3.1: LLM-extracted tags (Strategy F).
-- Storage: per-thought 5-axis tag bundle {client, project, activity, topic, status}
-- with metadata {value, source, confidence, validated_by, batch_run_id}.
-- GIN index for lookups like `WHERE extracted_tags @> '{"project":[{"value":"acme-pulsar"}]}'`.
-- Idempotent: safe to re-run.

ALTER TABLE thoughts
  ADD COLUMN IF NOT EXISTS extracted_tags JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_thoughts_extracted_tags
  ON thoughts USING GIN (extracted_tags);

