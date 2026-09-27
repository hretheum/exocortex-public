---
title: Architecture overview
---

# Architecture overview

Exocortex has three layers. They map cleanly to the systems thinking
behind the project: **sources of truth → graph → surfaces.** The graph
is canonical; the surfaces are recompiled from it on a schedule.

```
                      L1 — sources of truth
   ┌─────────────────────────────────────────────────────┐
   │   vault/*.md   ·   email   ·   RSS   ·   meetings   │
   └─────────────────────────────────────────────────────┘
                            │  Capture API (POST /capture)
                            ▼
                      L2 — the graph
   ┌─────────────────────────────────────────────────────┐
   │   thoughts (pgvector)   ─edges (AGE, 35 types)─→    │
   │              syntheses (LLM, on-demand)             │
   └─────────────────────────────────────────────────────┘
              │                              │
      write-time fork                  query-time fork
   (wiki compiler nightly)           (GraphRAG, MCP tools)
              │                              │
              ▼                              ▼
                      L3 — surfaces
   ┌─────────────────────────────────────────────────────┐
   │  Obsidian wiki   ·   Notion   ·   Telegram   ·  CLI │
   └─────────────────────────────────────────────────────┘
```

## L1 — sources of truth

Anything you write or capture. Vault Markdown files, emails marked for
later reading, RSS items, meeting transcripts, anything POSTed to
`/capture`. L1 is human-editable; L2 and L3 are not.

The capture API routes each L1 item through a content-typed processor
that produces typed `thoughts` and `edges`. This is the *only* path
into L2 — see the [source pipeline pattern](https://github.com/hretheum/exocortex/blob/main/docs/architecture/source-pipeline-pattern.md)
for the full state machine.

## L2 — the graph

The canonical store. Three tables do the work:

- **`thoughts`** — append-only event log of atomic ideas. Each row
  carries a pgvector embedding (HNSW indexed) and a `provenance` tag
  (`human` / `ai_assisted` / `ai_extracted` / `ai_authored`).
- **`edges`** — typed relationships between thoughts. Thirty-five edge
  types in the upstream taxonomy (`supports`, `contradicts`,
  `derived_from`, `revisits`, …) stored through Apache AGE for
  Cypher-style traversal.
- **`syntheses`** — LLM-compiled rollups (per client, per project, per
  newsletter cluster, per quarter). Materialised on a schedule; the
  graph is canonical, the syntheses are a cache.

Nothing edits L2 directly. Every change starts in L1 and flows through
the capture API; if you want to "fix" a graph row, you fix the source
note and let the processor re-emit. This is the **source-of-truth
rule** — its rationale is in [`EXOCORTEX.md`](https://github.com/hretheum/exocortex/blob/main/EXOCORTEX.md#4-the-source-of-truth-rule).

## The two forks

L2 feeds two independent consumers. Keeping them separate is the most
important architectural decision in the project.

### Write-time fork — wiki compiler

Nightly, a per-domain compiler reads the relevant slice of `thoughts`
+ `edges` + `syntheses` and writes Markdown files into the vault.
Pages are deterministic and idempotent: same graph state in, same
files out. Editing a compiled page in Obsidian is *valid* (it becomes
an L1 source) but will not survive the next compile unless your edit
also lives in L1.

This is the slow path. It does the LLM work upfront so that *reading*
is instant.

### Query-time fork — GraphRAG + MCP

On a question, the engine does hybrid retrieval (pgvector top-K +
Apache AGE traversal, ranked by provenance) and asks an LLM to
synthesise an answer with inline citations. Latency budget: under
2 seconds on a warm cache.

This is the fast path. It does no batch precomputation; every answer
is composed on demand from current graph state.

## L3 — surfaces

Obsidian for editing, Notion for sharing with non-technical
collaborators, Telegram for read/write on mobile, the CLI / MCP for
programmatic and conversational access. Surfaces are *always*
regenerable from L2 — losing any one of them is non-fatal.

## Why this shape

Three properties fall out of this architecture for free:

1. **Editable everywhere, canonical in one place.** Obsidian and
   Notion remain useful for what they're already good at. The graph
   doesn't compete with them.
2. **Cheap retraction.** Removing a source note removes its
   contribution from every compiled surface on the next cycle. No
   "find every place the LLM mentioned this" cleanup.
3. **Provenance survives.** Because edges and thoughts carry a
   `provenance` tag, GraphRAG can rank human-authored content over
   unvalidated AI output and prevent feedback loops.

## Going deeper

- [`EXOCORTEX.md`](https://github.com/hretheum/exocortex/blob/main/EXOCORTEX.md) §2
  — the full architecture chapter
- [Source pipeline pattern](https://github.com/hretheum/exocortex/blob/main/docs/architecture/source-pipeline-pattern.md)
  — how a vault file becomes a thought row
- [Knowledge architecture](https://github.com/hretheum/exocortex/blob/main/docs/architecture/knowledge-architecture.md)
  — L1/L2/L3 in long form, with state-machine diagrams
- [Knowledge boundaries, telemetry, provenance](https://github.com/hretheum/exocortex/blob/main/docs/architecture/knowledge-boundaries-telemetry-provenance.md)
  — scoped retrieval, query memory, provenance ranking
