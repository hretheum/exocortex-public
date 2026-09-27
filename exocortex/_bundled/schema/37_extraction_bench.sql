-- zadanie-6-stanowisko-ekstrakcji.md — deterministyczny rig pomiarowy do
-- porownania konfiguracji ekstrakcji twierdzen (M3). Stanowisko NIE jest
-- orkiestrowane modelem: te tabele sa czysta struktura danych, petla robocza
-- (scripts/bench_rig.py) to zwykly kod bez zadnego wywolania LLM w samej
-- petli sterujacej.
--
-- Celowo ODDZIELONE od produkcyjnych `thoughts`/`edges` (schema/01_base.sql)
-- — ten rig NIGDY nie zapisuje do grafu. Kandydaci na twierdzenia trafiaja
-- wylacznie do bench_claims, nie do `thoughts`. To czyni odwracalnosc
-- trywialna (DELETE po config_id/job, zero sierot w grafie z definicji) i
-- unika luki opisanej w docs/ekstrakcja/NIEPEWNOSCI.md #4 (zadanie 5) —
-- ten rig nie tworzy nic, co trzeba by bylo stamtad usuwac.

-- Macierz konfiguracji jako DANE, nie lista wywolan w skrypcie (wzorzec
-- oculink-testy) — dodanie konfiguracji = INSERT, zero zmian w petli.
CREATE TABLE IF NOT EXISTS bench_configs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL UNIQUE,          -- np. 'terse-qwen36-doc'
    use_case       TEXT NOT NULL,                 -- klucz routingu second_brain.F_bench_*
    prompt_variant TEXT NOT NULL,                 -- klucz do PROMPT_VARIANTS w extract_claims.py
    granularity    TEXT NOT NULL CHECK (granularity IN ('document', 'chunk')),
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Nazwane probki dokumentow (strojenie / kontrolna) — trzymane jako dane,
-- zapytywalne, zamiast zaszytej w kodzie listy UUID-ow.
CREATE TABLE IF NOT EXISTS bench_samples (
    sample_name  TEXT NOT NULL,          -- 'tuning-20' | 'control-10'
    document_id  UUID NOT NULL,          -- thoughts.id (thought_type='vault_note')
    added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sample_name, document_id)
);

-- Kolejka zadan: jeden wiersz = jedna jednostka tekstu (dokument ALBO
-- fragment) przepuszczona przez jedna konfiguracje. Ta sama ksztaltka
-- zadania dla obu granularnosci — agregacja do poziomu dokumentu dzieje sie
-- w analizie (M6), nie w samej kolejce.
CREATE TABLE IF NOT EXISTS bench_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id     UUID NOT NULL REFERENCES bench_configs(id) ON DELETE CASCADE,
    sample_name   TEXT NOT NULL,
    document_id   UUID NOT NULL,                  -- zawsze dokument-rodzic (agregacja)
    unit_type     TEXT NOT NULL CHECK (unit_type IN ('document', 'chunk')),
    unit_id       UUID NOT NULL,                  -- thoughts.id albo thought_chunks.id
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'in_progress', 'done', 'error', 'skipped')),
    owner         TEXT,
    lease_until   TIMESTAMPTZ,
    attempts      INT NOT NULL DEFAULT 0,
    max_attempts  INT NOT NULL DEFAULT 2,          -- retry tylko na niespodziewany wyjatek rigu, NIE na ExtractionCallError (patrz bench_rig.py)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    UNIQUE (config_id, unit_type, unit_id)         -- ponowne zaladowanie tej samej macierzy = no-op
);

CREATE INDEX IF NOT EXISTS idx_bench_jobs_claimable
    ON bench_jobs (status, lease_until);

-- Wynik zagregowany na poziomie jednego zadania (jeden dokument/fragment x
-- jedna konfiguracja). Telemetria kosztu/dostawcy NAPRAWIONA wzgledem
-- zadania 5: provider_actual pochodzi z realnego resolved base_url
-- (RoutingConfig.providers[...].base_url), nie z etykiety-aliasu
-- 'deepinfra', ktora nic nie mowi o tym, czy wywolanie bylo naprawde
-- lokalne czy zdalne (docs/ekstrakcja/NIEPEWNOSCI.md, zadanie 5).
CREATE TABLE IF NOT EXISTS bench_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id            UUID NOT NULL UNIQUE REFERENCES bench_jobs(id) ON DELETE CASCADE,
    reliability_ok    BOOLEAN NOT NULL,             -- False = wywolanie ekstrakcji rzucilo ExtractionCallError
    error_reason      TEXT,
    extracted_count   INT NOT NULL DEFAULT 0,
    grounded_count    INT NOT NULL DEFAULT 0,
    proposition_count INT NOT NULL DEFAULT 0,
    redundant_count   INT NOT NULL DEFAULT 0,
    usable_count      INT NOT NULL DEFAULT 0,
    provider          TEXT,                        -- alias z llm_router (np. 'deepinfra')
    model             TEXT,
    provider_actual   TEXT,                        -- 'local' | 'remote', z resolved base_url
    base_url          TEXT,
    use_case          TEXT,
    input_tokens      INT NOT NULL DEFAULT 0,
    output_tokens     INT NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    latency_ms        INT NOT NULL DEFAULT 0,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bench_results_job
    ON bench_results (job_id);

-- Surowy wynik na poziomie POJEDYNCZEGO kandydata na twierdzenie — brak
-- tego w zadaniu 5 uniemozliwial analize po typie dokumentu bez ponownego
-- przebiegu (docs/ekstrakcja/NIEPEWNOSCI.md #2, zadanie 5). Kazda decyzja
-- kazdego filtra zapisana jawnie, wiec analiza (M6) czyta tylko z bazy.
CREATE TABLE IF NOT EXISTS bench_claims (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id         UUID NOT NULL REFERENCES bench_jobs(id) ON DELETE CASCADE,
    claim_text     TEXT NOT NULL,
    quote          TEXT,
    is_grounded    BOOLEAN NOT NULL,
    is_proposition BOOLEAN,                        -- NULL = nie sprawdzone (odrzucone wczesniej na groundingu)
    is_redundant   BOOLEAN,                        -- NULL = nie sprawdzone (odrzucone wczesniej)
    is_usable      BOOLEAN NOT NULL,
    rejection_reason TEXT,                         -- 'not_grounded' | 'not_proposition' | 'redundant' | NULL (usable)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bench_claims_job
    ON bench_claims (job_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON bench_configs, bench_samples, bench_jobs,
    bench_results, bench_claims TO second_brain;
