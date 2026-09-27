# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# F6.3 per-source_type processors. Each module exports `process(source_id, ...)`
# that workers/scorer.py dispatches via the ROUTING table.
#
# Contract:
#   def process(source_id: str) -> dict
#   - Read raw_sources by id.
#   - Do source-specific enrichment (LLM tag/summary, structured field extract).
#   - Persist outputs (thoughts row, edges, metadata patch).
#   - Idempotent: re-runs should be a no-op (read state, skip if already done).
#   - Return summary dict for logging: {status: "ok"|"skipped"|"error", ...}
