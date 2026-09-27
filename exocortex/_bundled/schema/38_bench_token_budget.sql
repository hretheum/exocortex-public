-- M5: token budget as per-configuration data,
-- not a constant hardcoded in the rig code.
--
-- Reason: max_tokens=2048 (extraction) / 256 (judge) were carried over unchanged
-- from scripts/extract_claims.py, tuned for local qwen3.6. The
-- M5 test on gemini-3.6-flash showed `finish_reason=length` (response cut off
-- BEFORE the tool call was emitted) even on a 314-character document
-- - likely "thinking" token overhead in remote models. Keeping a
-- shared budget would penalize those models unfairly (truncation, not extraction
-- quality, would decide the result). The defaults below = exactly
-- what was hardcoded before - zero behavior change for already
-- loaded local configurations.

ALTER TABLE bench_configs
    ADD COLUMN IF NOT EXISTS max_tokens_extract INT NOT NULL DEFAULT 2048,
    ADD COLUMN IF NOT EXISTS max_tokens_judge   INT NOT NULL DEFAULT 256;
