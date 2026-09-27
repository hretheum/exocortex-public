-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/42_thoughts_updated_at.sql — audit column for thought mutation.
--
-- Why: `thoughts` had `created_at` but nothing recording a later change, and
-- `emit_thought_for_source` UPDATEs an existing row in place (same id) on every
-- reprocessing. So when a mass reprocessing run on 2026-08-02 wiped the title
-- of 66 of 283 recipes — collapsing them all onto one filename and leaving 65
-- with no wiki page — there was no way to establish what had touched them or
-- when. The root cause in the processor is fixed (5e0ca2b), but the blind spot
-- that made it undiagnosable is not, and the next surprise will be a different
-- one.
--
-- A trigger rather than application code: the point is to catch writes nobody
-- remembered to instrument, including ad-hoc UPDATEs run by hand during an
-- incident. Backfilled to created_at so existing rows read "never modified"
-- rather than "modified at migration time", which would be a lie.

ALTER TABLE thoughts ADD COLUMN IF NOT EXISTS updated_at timestamptz;

UPDATE thoughts SET updated_at = created_at WHERE updated_at IS NULL;

ALTER TABLE thoughts ALTER COLUMN updated_at SET DEFAULT now();

CREATE OR REPLACE FUNCTION fn_thoughts_set_updated_at() RETURNS trigger AS $$
BEGIN
  -- Only on a real change: a no-op UPDATE should not look like an edit.
  IF NEW IS DISTINCT FROM OLD THEN
    NEW.updated_at := now();
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_thoughts_updated_at ON thoughts;
CREATE TRIGGER trg_thoughts_updated_at
  BEFORE UPDATE ON thoughts
  FOR EACH ROW EXECUTE FUNCTION fn_thoughts_set_updated_at();

-- Answering "what changed in the last 24h, and which of it drifted a title"
-- is the whole point, so make that query cheap.
CREATE INDEX IF NOT EXISTS idx_thoughts_updated_at
  ON thoughts (tenant_id, updated_at DESC)
  WHERE updated_at IS NOT NULL;
