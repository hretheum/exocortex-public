-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- K12: embeddings computed locally by bge-m3 (llama-swap, 127.0.0.1:8080),
-- which returns 1024-dimensional vectors, instead of OpenAI text-embedding-3-small
-- (1536d). The K12 deployment starts with an empty database (no computed vectors),
-- so changing the column type is instant and lossless. The HNSW index
-- survives ALTER TYPE (rebuild on an empty table = no-op).
--
-- If a future deployment ALREADY has computed 1536d vectors, this migration
-- requires nulling the columns first (the old vectors are useless anyway
-- after a model change: vectors from different models do not share one space).

ALTER TABLE thoughts  ALTER COLUMN embedding          TYPE VECTOR(1024);
ALTER TABLE query_log ALTER COLUMN question_embedding TYPE VECTOR(1024);
