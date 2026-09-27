-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/06_indices.sql — performance indices added in F2.6 (post-F1 self-hosted PG).
-- Idempotent: safe to re-run.

-- Edges-by-type lookup (used by wiki_compiler edge traversal in F4 and GraphRAG in F5).
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(tenant_id, type);

