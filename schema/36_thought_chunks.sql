-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/36_thought_chunks.sql — separates the unit of meaning from the unit
-- of search.
--
-- Why: F33's vault_note processor emits one thought PER MARKDOWN HEADING —
-- 399 documents became 4684 thoughts, median fragment 303 chars, 1505 of
-- them under 200 chars. That's splitting on formatting, not meaning: wiki
-- generation gets 4648 pages instead of 399, synthesis sees fragments
-- without document context across 15 perspectives, ranking favors prose
-- (a document cut into twelve pieces gets twelve chances to match; a
-- backlog ticket gets one), and the three processors disagree on what a
-- thought even is (backlog_item/recipe are 1:1 with files, vault_note is
-- ~12:1).
--
-- Fix: a vault_note document is ONE thought (one graph node, one wiki page,
-- one synthesis item, one thing to link to). Fragments move here, each with
-- its own embedding and a reference to the parent thought. Semantic search
-- hits a chunk but returns the parent document, deduplicated.
--
-- thoughts.embedding stays exactly as-is for backlog_item, recipe, and
-- work_meeting_note — for those, thought already equals document, and a
-- separate chunks table would be pure overhead. Only vault_note moves to
-- NULL thoughts.embedding + rows here (see exocortex/processors/vault_note.py).

CREATE TABLE IF NOT EXISTS thought_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    thought_id  UUID NOT NULL REFERENCES thoughts(id) ON DELETE CASCADE,
    chunk_index INT  NOT NULL,
    heading     TEXT,
    body        TEXT NOT NULL,
    embedding   VECTOR(1024),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE thought_chunks IS
    'search-unit fragments of a parent thought (currently: vault_note '
    'documents only). One row per merged section (see vault_note.py chunking, '
    'H2 boundaries merged to a minimum length — NOT one row per heading). '
    'Deleted wholesale (CASCADE) when the parent thought is deleted; the '
    'processor also deletes+reinserts all of a document''s chunks on every '
    're-run rather than upserting by chunk_index, so a shrinking document '
    'never leaves orphaned trailing chunks.';

CREATE INDEX IF NOT EXISTS idx_thought_chunks_thought
    ON thought_chunks (thought_id);

CREATE INDEX IF NOT EXISTS idx_thought_chunks_embedding
    ON thought_chunks USING hnsw (embedding vector_cosine_ops);
