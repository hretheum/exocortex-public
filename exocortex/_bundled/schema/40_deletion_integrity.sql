-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/40_deletion_integrity.sql — deletion integrity.
--
-- Two changes combined into one migration to avoid migrating the schema
-- twice (both gate writing model-generated claims to the graph).
--
-- ============================================================================
-- Part 1 — guarantee of no orphaned edges when a thought is deleted
-- ============================================================================
--
-- `edges.dst_id`/`edges.src_id` are polymorphic (in practice today: thought,
-- synthesis as src; thought, entity — four subtypes via entities.type —
-- and raw_source as dst), so a plain single-column foreign key is not an option.
-- The only delete operation that exists in the code is DELETE FROM thoughts
-- (scripts/extract_claims.py::delete_run; /capture/delete works only
-- on raw_sources and never deletes rows — see Part 2 below). entities,
-- raw_sources and syntheses are never deleted anywhere, so the trigger covers
-- only thoughts — extending it to the other tables, if they ever
-- start being deleted, is a new CREATE TRIGGER with the same function, not a change
-- to this migration.
--
-- Rejected alternatives:
--   1. FK directly on src_id/dst_id — impossible: one column cannot
--      reference four different tables at once without restructuring.
--   2. A periodic sweep looking for edges with no match in the
--      target table — rejected: gives EVENTUAL cleanup, not a GUARANTEE. Between
--      the delete and the next sweep the edge is orphaned and readable
--      (exactly the state already detected informally by
--      exocortex/wiki/domains/home/__init__.py — the orphaned-edges query
--      exists, but nothing removes them). A guarantee is required here.
--   3. Splitting `edges` into per-target-type tables (edges_thought, edges_entity, …)
--      with real FKs — architecturally correct, but explicitly out of scope
--      here (a change with wider impact than this one
--      — a stop condition, not a design choice).
--
-- Chosen: a trigger, because it runs IN THE SAME transaction as the DELETE — the delete and
-- the edge cleanup either both succeed or both roll back. That is
-- what "guarantees" actually means.

CREATE OR REPLACE FUNCTION fn_cleanup_thought_edges() RETURNS trigger AS $$
BEGIN
  DELETE FROM edges
  WHERE (src_id = OLD.id AND src_type = 'thought')
     OR (dst_id = OLD.id AND dst_type = 'thought');
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_cleanup_thought_edges ON thoughts;
CREATE TRIGGER tg_cleanup_thought_edges
  AFTER DELETE ON thoughts
  FOR EACH ROW
  EXECUTE FUNCTION fn_cleanup_thought_edges();

COMMENT ON FUNCTION fn_cleanup_thought_edges IS
    'Deletes edges in both directions (src and dst) when a thought is deleted. '
    'The only such mechanism; transactional; also covers batch deletes '
    '(DELETE ... WHERE metadata->>''run_id''=X fires this trigger once per row).';

-- ============================================================================
-- Part 3 — ADR-008: citation required for claims
-- ============================================================================
--
-- Applies only to thought_type='claim' (model-generated content).
-- vault_note/backlog_item/recipe/work_meeting_note are copied from files —
-- no new requirement, no change in row count, no constraint change.
--
-- scripts/extract_claims.py did NOT need a change: check_grounding() already
-- rejects an empty/whitespace-only quote (`if not quote or not quote.strip():
-- return False`) before a claim ever reaches _write_claim(), so every
-- row this code has ever written had a quote. This constraint is
-- a schema-level safety net — it closes the path for ANY
-- future/other code, not just today's processor.

ALTER TABLE thoughts ADD CONSTRAINT chk_claim_requires_quote
  CHECK (thought_type <> 'claim' OR (metadata->>'quote' IS NOT NULL AND metadata->>'quote' <> ''));

COMMENT ON CONSTRAINT chk_claim_requires_quote ON thoughts IS
    'ADR-008 — a claim without a source quote cannot be stored. '
    'Applies only to thought_type=''claim''.';
