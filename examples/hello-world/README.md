---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.4 — hello-world README (5-min quickstart)"
title: Hello World — 5-minute Exocortex demo
---

# Hello World — 5-minute Exocortex demo

The smallest possible Exocortex loop: **one note in, one question out**.
No plugins, no synthesizer, no wiki compiler — just `ingest → embed → query`.

If you can run the four commands below in five minutes, the engine is
healthy and you are ready to explore the [`acme-corp`](../acme-corp/)
example next.

## Prerequisites

- `docker compose` is up and migrations applied (from the repo root):

    ```bash
    docker compose up -d --build
    docker compose exec api exocortex migrate up
    ```

- `OPENAI_API_KEY` is exported in your shell (used by
  `text-embedding-3-small` for both ingest and query). The retrieval step
  also needs an LLM provider key (`ANTHROPIC_API_KEY` or one of the
  alternatives wired into `llm_router`); without it you'll still see the
  retrieved sources but the answer paragraph will be `[error: ...]`.

## Steps

```bash
# 1. Ingest the note (POSTs to localhost:8000/capture + writes a thought row)
docker compose exec api python examples/hello-world/ingest_one_note.py
# ✓ thought_id=<uuid> ingested with embedding

# 2. Ask a question — answer + citations come back in <2 s on a warm cache
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
      "I learned today that Cypher MATCH clauses can chain through edge
       types ..."
```

## What this demo skips (and why)

- **No plugin registration.** `ingest_one_note.py` writes `thoughts`
  directly. This bypasses the F6.3 scorer/router because the default
  `docker-compose.yml` does not start a scorer daemon and `quick-note`
  is in any case a deferred routing type. See
  [`examples/acme-corp/`](../acme-corp/) for a full plugin showcase.
- **No synthesizer.** Daily LLM rollups are out of scope for a 5-min
  smoke; `exocortex synth` runs against ACME data instead.
- **No wiki compiler.** Same reason.
- **Idempotent re-runs.** The script will detect the existing thought
  on a second run and exit `0` without re-embedding.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `capture API failed: 401` | `CAPTURE_API_TOKEN` mismatch — make sure your shell uses the same token as the `api` container (`dev-token` by default). |
| `embedding generation failed` | `OPENAI_API_KEY` is unset or the key has no `embeddings` scope. |
| `No sources found` | `ingest_one_note.py` was not run inside the `api` container so it talked to a different DB. Run it the same way as step 1 above. |
| `Brak źródeł w bazie...` (Polish: "No sources in the database matching your query") | Embedding succeeded but no vector hits — usually means the question is too far from the note text. Try the exact suggested question. |
