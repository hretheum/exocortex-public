-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/10_age_indexes.sql — F4.6.1: BTREE indexes on AGE label-table
-- agtype_access_operator(properties, '"id"'::agtype) for fast MERGE lookups.
--
-- Idempotent: wrapped in DO block that skips gracefully if the AGE graph
-- schema doesn't exist yet (fresh Docker install before any data is ingested).
-- The label tables are created by AGE automatically on first vertex insert.

-- SET LOCAL, not SET (audited + corrected 2026-07-28): every object this file touches is
-- schema-qualified explicitly (exocortex."Thought", second_brain."Thought"),
-- so ag_catalog only needs to be in the path here to resolve the unqualified
-- agtype_access_operator() call. The bug: the runner (migrations.py) reuses
-- ONE connection across every schema/*.sql file in a single `migrate up`
-- run, and a bare SET (unlike SET LOCAL) survives past this file's own
-- transaction COMMIT — so this line was silently forcing ag_catalog-first
-- for EVERY migration that runs after this one in the same invocation
-- (11 onward), regardless of what those files or the database default say.
-- SET LOCAL reverts automatically at this file's transaction boundary.
SET LOCAL search_path = ag_catalog, "$user", public;

DO $$
BEGIN
  -- exocortex graph (Docker default)
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'exocortex' AND table_name = 'Thought') THEN
    CREATE INDEX IF NOT EXISTS idx_thought_id
      ON exocortex."Thought" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_person_id
      ON exocortex."Person" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_client_id
      ON exocortex."Client" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_project_id
      ON exocortex."Project" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_synthesis_id
      ON exocortex."Synthesis" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    RETURN;
  END IF;

  -- second_brain graph (legacy bare-metal deployment name)
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'second_brain' AND table_name = 'Thought') THEN
    CREATE INDEX IF NOT EXISTS idx_thought_id
      ON second_brain."Thought" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_person_id
      ON second_brain."Person" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_client_id
      ON second_brain."Client" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_project_id
      ON second_brain."Project" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    CREATE INDEX IF NOT EXISTS idx_synthesis_id
      ON second_brain."Synthesis" USING btree ((agtype_access_operator(properties, '"id"'::agtype)));
    RETURN;
  END IF;

  RAISE NOTICE '10_age_indexes: AGE label tables not found — skipping (will be created after first ingest).';
END;
$$;
