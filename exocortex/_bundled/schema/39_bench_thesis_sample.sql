-- zadanie-7-probka-tezowa.md, M3/Z7-5 — gap ujawniony przez nowa probke:
-- rig zakladal, ze kazda jednostka tekstu (dokument/fragment) zyje w
-- produkcyjnym `thoughts`/`thought_chunks`. Anonimizowane kopie tezowe
-- nigdy nie sa ingestowane (i nigdy nie powinny byc - to kopie robocze
-- poza vaultem, patrz docs/ekstrakcja/ANONIMIZACJA.md), wiec potrzebuja
-- wlasnego, lokalnego magazynu tresci. To jest dokladnie przypadek, ktory
-- brief zadania 7 zapowiedzial: "jesli [nowa probka] wymaga [zmian w
-- kodzie petli] - zglos, bo to znaczy, ze stanowisko jest mniej ogolne,
-- niz deklaruje." Zglaszamy: TAK, wymagalo to jednej nowej tabeli i
-- jednej nowej galezi w _fetch_unit_body (unit_type='file') - drobne,
-- ale realne rozszerzenie, nie zaszyte od poczatku.

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
