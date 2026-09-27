-- F31-MS-P0.5: module-discriminated migration tracker for module-owned schema files.
-- Complements exocortex_migrations (core) — modules own their SQL in migrations/ subfolders.

CREATE TABLE IF NOT EXISTS schema_migrations (
    module      TEXT        NOT NULL DEFAULT 'core',
    filename    TEXT        NOT NULL,
    hash        TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (module, filename)
);
COMMENT ON TABLE  schema_migrations IS 'Module-owned migrations tracker. module discriminates core vs plugin migrations.';
COMMENT ON COLUMN schema_migrations.module   IS 'Owner module (core, notion, frp, ...).';
COMMENT ON COLUMN schema_migrations.filename IS 'SQL file basename within the module migrations/ dir.';
COMMENT ON COLUMN schema_migrations.hash     IS 'SHA-256 of file content at apply time.';
