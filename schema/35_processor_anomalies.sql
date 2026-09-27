-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/35_processor_anomalies.sql — DB-backed anomaly log for processors.
--
-- Why: workers/ingest.py's normalize_participants() logged data-quality
-- anomalies (Fireflies sometimes emits one comma-joined participants string
-- instead of a proper list) to data/discovery/ingest_anomalies.tsv — a file
-- inside the repo checkout. That file doesn't survive container rebuilds
-- (F34's target deployment is an immutable GHCR image) and isn't queryable.
-- Moving this to a table follows the same pattern already established by
-- provider_errors (schema/21_...) for exactly this kind of best-effort,
-- append-only diagnostic record.
--
-- Generic across processors (source_id + processor_name identify the
-- caller), even though work_meeting_note.py (F34) is the only writer today —
-- mirrors provider_errors' shape rather than inventing a meeting-specific
-- table for what is a cross-cutting concern.

CREATE TABLE IF NOT EXISTS processor_anomalies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    source_id UUID REFERENCES raw_sources(id) ON DELETE CASCADE,
    processor_name TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,
    detail JSONB,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE processor_anomalies IS
    'F34 — best-effort processor-side data-quality anomalies (e.g. malformed '
    'source frontmatter). Replaces ad-hoc per-processor TSV files. One row '
    'per detected anomaly; never blocks the caller on insert failure.';

CREATE INDEX IF NOT EXISTS idx_processor_anomalies_source
    ON processor_anomalies (tenant_id, processor_name, detected_at DESC);

GRANT INSERT, SELECT ON processor_anomalies TO second_brain;
