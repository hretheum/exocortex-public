---
title: "Quickstart"
description: "Get Exocortex running locally in under 10 minutes"
---

The smallest possible Exocortex loop: **one note in, one question out**.
No plugins, no synthesiser, no wiki compiler — just `ingest → embed →
query`. Five minutes if Docker is already on your machine.

## Prerequisites

- Docker + Docker Compose v2
- `OPENAI_API_KEY` exported in your shell (for embeddings)
- `ANTHROPIC_API_KEY` (or another `llm_router`-supported provider) for
  the retrieval step

## Four commands

```bash
git clone https://github.com/hretheum/exocortex.git
cd exocortex

# 1. Bring Postgres + pgvector + Apache AGE up, apply migrations
docker compose up -d --build
docker compose exec api exocortex migrate up

# 2. Ingest a single note (POSTs to /capture + writes a thought row)
docker compose exec api python examples/hello-world/ingest_one_note.py
# ✓ thought_id=<uuid> ingested with embedding

# 3. Ask a question — answer + citations in <2 s on a warm cache
docker compose exec api python examples/hello-world/ask_question.py \
    "what did I learn about Cypher"
```

Expected output (abridged):

```
Q: what did I learn about Cypher

A: Cypher MATCH clauses can chain through edge types ... Apache AGE
   supports this within Postgres ... downside is AGE 1.6 lags behind
   the official Neo4j spec.

Sources (1):
  [1] Cypher quick notes
      thought_id=...  score=...  provenance=ai_authored
```

## What this skips (and why)

This is the smoke loop. It is deliberately *not* a full Exocortex setup:

- **No plugin registration.** `ingest_one_note.py` writes `thoughts`
  directly. The full source pipeline (vault watcher, scorer, router,
  processors) is documented in the
  [capture API runbook](https://github.com/hretheum/exocortex/blob/main/docs/capture-api-runbook.md).
- **No synthesiser.** Daily LLM rollups are out of scope for a 5-min
  smoke. See the
  [synthesis runbook](https://github.com/hretheum/exocortex/blob/main/docs/synthesis-runbook.md).
- **No wiki compiler.** Same reason — the compiler runs nightly in
  production.

## Next steps

- [Configuration](configuration.md) — env vars, YAML config files, how
  the engine picks them up
- [Writing a plugin](../guides/writing-a-plugin.md) — the
  end-to-end tutorial against [`examples/acme-corp/`](https://github.com/hretheum/exocortex/tree/main/examples/acme-corp)
- [MCP tools reference](../guides/mcp-tools.md) — what the MCP
  server exposes to Claude Desktop or `exocortex query`
- [Architecture overview](../architecture/overview.md) — L1/L2/L3
  in two paragraphs
