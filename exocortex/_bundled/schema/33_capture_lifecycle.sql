-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/33_capture_lifecycle.sql — F32: lifecycle for raw_sources (deletion,
-- rename) so the Obsidian plugin (and any future watcher) can tell the graph
-- "this file is gone" / "this file moved" instead of leaving orphaned rows.
--
-- Soft delete, not hard delete: thoughts.source_id and content_queue.source_id
-- REFERENCE raw_sources(id) with the default (RESTRICT) action — a hard DELETE
-- would fail the moment anything points at the row, and even if it didn't,
-- destroying the row would silently orphan the thoughts/edges that cite it.
-- deleted_at marks the source as gone while keeping every existing reference
-- intact; consumers that care about "still live" filter on deleted_at IS NULL.
--
-- Rename is a plain UPDATE of raw_sources.uri (see capture_api.py /capture/rename)
-- — same row id, so thoughts/edges never need to move. No schema change is
-- needed for rename itself; deleted_at is the only new column this migration
-- adds, but it's also what makes rename-of-a-deleted-file a well-defined no-op
-- (see capture_api.py: rename only touches rows WHERE deleted_at IS NULL).

ALTER TABLE raw_sources ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

COMMENT ON COLUMN raw_sources.deleted_at IS
    'F32 — set when the originating file/note disappeared (e.g. deleted from '
    'the vault). NULL = still live. Existing thoughts/edges referencing this '
    'row are NOT cascaded or cleaned up — that is a deliberate, separate '
    'concern from marking the source itself as gone.';

-- Partial index: cleanup/audit queries only ever care about the (small)
-- deleted subset, not a scan predicate on every active-row lookup.
CREATE INDEX IF NOT EXISTS idx_raw_sources_deleted_at
    ON raw_sources(tenant_id, deleted_at)
    WHERE deleted_at IS NOT NULL;
