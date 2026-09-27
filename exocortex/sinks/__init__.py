# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# F21 output sinks — side-effect writers invoked by F6.3 processors.
#
# Unlike workers/sources/ (which POST into the Capture API) and
# workers/processors/ (which enrich raw_sources → PG), a sink takes already-
# persisted state and pushes it to an external system. Sinks are best-effort:
# they never raise into the processor that called them, the canonical PG state
# is the source of truth, and the sink can be re-run idempotently.
