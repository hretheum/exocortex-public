-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/12_capture_extension.sql — F6.1.1: Generic Content Acquisition Module.
--
-- Extends raw_sources with source_type + acquired_at + per-tenant UNIQUE on
-- (source_type, uri). Adds 4 edge types:
--   - acquired_from        (thought → raw_source)        — derived note ← source
--   - cross_references     (thought → thought | entity)  — generic cross-link
--   - email_correspondent  (entity → entity)             — sender ↔ recipient
--   - summarizes_thread    (thought → email_thread)      — synthesis ← thread
--
-- Idempotent. Safe to re-run.

-- raw_sources: source_type + acquired_at
ALTER TABLE raw_sources
    ADD COLUMN IF NOT EXISTS source_type   TEXT;
ALTER TABLE raw_sources
    ADD COLUMN IF NOT EXISTS acquired_at   TIMESTAMPTZ DEFAULT NOW();

-- Backfill source_type for existing rows so the UNIQUE constraint covers them.
-- Pre-F6 rows came from FRP RSS / manual seeds — labelled 'legacy' so we can
-- audit later without colliding with new well-typed rows.
UPDATE raw_sources
   SET source_type = 'legacy'
 WHERE source_type IS NULL;

ALTER TABLE raw_sources
    ALTER COLUMN source_type SET NOT NULL;

-- Per-tenant uniqueness so capture_api can ON CONFLICT DO NOTHING per source.
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_sources_tenant_type_uri
    ON raw_sources(tenant_id, source_type, uri);

CREATE INDEX IF NOT EXISTS idx_raw_sources_acquired_at
    ON raw_sources(tenant_id, acquired_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_sources_source_type
    ON raw_sources(tenant_id, source_type);

-- Edge types — extend ENUM. ALTER TYPE ADD VALUE IF NOT EXISTS is supported in PG 16.
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'acquired_from';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'cross_references';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'email_correspondent';
ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'summarizes_thread';

COMMENT ON COLUMN raw_sources.source_type IS
    'F6.1.1 — discriminator for capture pipeline routing. '
    'Examples: rss-frp, gmail-thread, web-clipping, article, recipe, '
    '3d-model, github-issue, twitter-thread, arxiv, youtube-tutorial, '
    'personal-article, quick-note, manual-url, legacy.';

COMMENT ON COLUMN raw_sources.acquired_at IS
    'F6.1.1 — when capture_api received the source. May differ from '
    'ingested_at (= row insert) when re-import happens for already-known URIs.';

