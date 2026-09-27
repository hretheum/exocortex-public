-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/15_newsletter_pipeline.sql — F8.8: newsletter ingestion edge types.
--
-- Adds 4 edge types used by the newsletter pipeline (workers/processors/newsletter.py):
--   - cites              (newsletter thought → cited_source entity)
--   - mentions_topic     (newsletter thought → topic entity)
--   - tagged_with        (newsletter thought → tag entity / concept)
--   - from_source        (newsletter thought → newsletter sender entity)
--
-- Idempotent: ALTER TYPE … ADD VALUE IF NOT EXISTS is supported by PG 12+.
-- Re-running the migration is safe.

ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'cites';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'mentions_topic';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'tagged_with';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'from_source';

