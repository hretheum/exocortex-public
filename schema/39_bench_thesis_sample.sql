-- M3/Z7-5 — gap exposed by the new sample:
-- the rig assumed every text unit (document/chunk) lives in
-- production `thoughts`/`thought_chunks`. Anonymized thesis copies
-- are never ingested (and never should be - they are working copies
-- outside the vault), so they need
-- their own local content store. This is exactly the case
-- the task brief anticipated: "if [the new sample] requires [changes to the
-- loop code] - report it, because it means the rig is less general
-- than it claims." Reporting: YES, it took one new table and
-- one new branch in _fetch_unit_body (unit_type='file') - small,
-- but a real extension, not built in from the start.

CREATE TABLE IF NOT EXISTS bench_files (
    id       UUID PRIMARY KEY,
    filename TEXT NOT NULL,
    body     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE bench_files IS
    'Tresc dokumentow/fragmentow spoza produkcyjnego grafu (np. anonimizowane '
    'kopie z zadania 7) - jedyne miejsce, gdzie rig czyta tresc NIE z '
    'thoughts/thought_chunks. id jest deterministyczny (uuid5 z nazwy pliku), '
    'zeby ponowne zaladowanie tej samej probki bylo idempotentne.';

ALTER TABLE bench_jobs DROP CONSTRAINT IF EXISTS bench_jobs_unit_type_check;
ALTER TABLE bench_jobs ADD CONSTRAINT bench_jobs_unit_type_check
    CHECK (unit_type IN ('document', 'chunk', 'file'));

GRANT SELECT, INSERT, UPDATE, DELETE ON bench_files TO second_brain;
