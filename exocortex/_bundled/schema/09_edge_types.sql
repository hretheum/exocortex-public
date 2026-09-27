-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/09_edge_types.sql — F4.6.1: extend edge_type ENUM + dedupe UNIQUE index.
--
-- Adds 4 edge types used by F4.6.1 edges populating:
--   - classified_as_client     (meeting → client entity)
--   - classified_as_project    (meeting → project entity)
--   - addresses_problem        (synthesis → source thought)
--   - mentions_person          (synthesis → person entity)
--
-- Plus UNIQUE index on (tenant_id, src_id, dst_id, type) so _insert_edge can use
-- ON CONFLICT DO NOTHING for idempotent re-runs (backfill + per-ingest hook).
--
-- Idempotent: safe to re-run. ALTER TYPE … ADD VALUE IF NOT EXISTS is non-transactional
-- in PG <12, but PG 16 supports IF NOT EXISTS.

ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'classified_as_client';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'classified_as_project';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'addresses_problem';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'mentions_person';

CREATE UNIQUE INDEX IF NOT EXISTS uq_edges_dedupe
  ON edges(tenant_id, src_id, dst_id, type);

