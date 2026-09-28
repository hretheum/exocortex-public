-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/44_lab_hypotheses.sql — hypothesis cards and gate decisions in the
-- lab (roadmap tasks F2.4, F2.5).
--
-- One row per card version and per gate decision, written by the lab's
-- processors from the published documents. The checksum registered when a
-- card was approved (prereg.jsonl) never changes here; a later content
-- change without a new version sets `violated`, and the gate processor
-- then refuses decisions for that hypothesis.

CREATE TABLE IF NOT EXISTS lab_hypotheses (
    slug              TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
    version           INT NOT NULL CHECK (version >= 1),
    supersedes        INT,
    title             TEXT,
    files             JSONB NOT NULL,                 -- {"pl": path, "en": path}
    content_sha256    TEXT NOT NULL,                  -- canonical checksum of both versions now
    approved          BOOLEAN NOT NULL,               -- human_validated in both versions
    prereg_sha256     TEXT,                           -- checksum in the registry, NULL until frozen
    prereg_at         TIMESTAMPTZ,
    violated          BOOLEAN NOT NULL DEFAULT FALSE,
    state             TEXT NOT NULL DEFAULT 'draft'
                      CHECK (state IN ('draft', 'frozen', 'GO', 'NO-GO', 'PIVOT', 'NOT-NOW', 'CLOSED')),
    return_condition  TEXT,
    metrics           JSONB NOT NULL DEFAULT '[]',    -- rows of the card's metrics table
    problems          JSONB NOT NULL DEFAULT '[]',
    thought_id        UUID,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (slug, version)
);

CREATE TABLE IF NOT EXISTS lab_gate_decisions (
    key                 TEXT PRIMARY KEY,             -- path without the language folder
    slug                TEXT,                         -- NULL when the header is too broken to say
    hypothesis_version  INT,
    gate                TEXT CHECK (gate IN ('G0', 'G1', 'G2')),
    decision            TEXT CHECK (decision IN ('GO', 'NO-GO', 'PIVOT', 'NOT-NOW', 'CLOSED')),
    decided_on          DATE,
    approved            BOOLEAN NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('applied', 'rejected', 'ignored')),
    reasons             JSONB NOT NULL DEFAULT '[]',
    result_ids          TEXT[] NOT NULL DEFAULT '{}',
    content_sha256      TEXT NOT NULL,
    thought_id          UUID,
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
