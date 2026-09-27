-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- F31.8.3 — migration tracking bootstrap.
--
-- Idempotent: re-applying is a no-op. The runner in
-- ``exocortex/core/db/migrations.py`` always executes this file first so the
-- tracking table exists before any other schema/*.sql is checked.

CREATE TABLE IF NOT EXISTS exocortex_migrations (
    filename   TEXT PRIMARY KEY,
    hash       TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  exocortex_migrations IS
    'Tracks which schema/*.sql files have been applied by `exocortex migrate up`. '
    'hash = SHA-256 of the file content at the time it was applied.';
COMMENT ON COLUMN exocortex_migrations.filename   IS 'Base file name (no directory).';
COMMENT ON COLUMN exocortex_migrations.hash       IS 'SHA-256 hex digest of file contents.';
COMMENT ON COLUMN exocortex_migrations.applied_at IS 'Timestamp of successful apply.';
