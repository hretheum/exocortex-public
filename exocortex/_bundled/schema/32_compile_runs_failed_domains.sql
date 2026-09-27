-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/32_compile_runs_failed_domains.sql — incident fix, 2026-07-28.
--
-- Commit 9782c78 ("F31.6.4/F31.6.5/F31.6.6: wiki compiler audit fixes — all
-- 20 goals green") repurposed the compile_runs completion UPDATE in
-- wiki_compiler.py from tracking `pages_skipped` to tracking `failed_domains`
-- (the list of domain modules that raised during compile_all — see
-- `failed.append(name)` in wiki_compiler.py) WITHOUT a matching migration.
-- The old `pages_skipped TEXT[]` column has been dead (written by nobody)
-- since that commit; nothing reads it either, so it is left in place here —
-- this migration is the minimal fix for the live incident, not a column
-- audit. See docs/incidenty/2026-07-28-schema.md for the full timeline.
--
-- Why this was never caught before K12: `current_run_id` is only truthy
-- (see wiki_compiler.py compile_all()) on a REAL, non-dry-run compile with
-- an actual compile_runs row already inserted — the exact combination K12's
-- nightly ingest exercises for the first time in this program's history.

ALTER TABLE compile_runs ADD COLUMN IF NOT EXISTS failed_domains TEXT[];

COMMENT ON COLUMN compile_runs.failed_domains IS
    'Domain modules (frp/work/3d/...) that raised during this compile run — '
    'see wiki_compiler.py compile_all(). Added 2026-07-28 to match code that '
    'had already been writing to this (until-now nonexistent) column since '
    'commit 9782c78.';
