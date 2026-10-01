# Exocortex

[![License: Apache 2.0 + Commons Clause](https://img.shields.io/badge/license-Apache%202.0%20%2B%20Commons%20Clause-blue)](LICENSE)
[![CI](https://github.com/hretheum/exocortex-public/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hretheum/exocortex-public/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/release/python-3120/)

> A personal knowledge OS that thinks while you sleep.

**[→ Full docs at exocortex.zone](https://exocortex.zone/)** · [Why Exocortex](https://exocortex.zone/why-exocortex/) · [Quickstart](https://exocortex.zone/getting-started/quickstart/)

Exocortex is a self-hosted reasoning engine for your notes. It ingests
what you read, hear, and decide; stores it as an append-only graph
(Postgres + pgvector + Apache AGE); and asks an LLM to compile a
plain-Markdown wiki from that graph every night. Obsidian, Notion,
Telegram, and your shell are surfaces — the brain lives in Postgres.

## What it does

- **Ingests** vault files, mail, RSS feeds, meeting transcripts, and
  anything you `POST` to `/capture` — turning each into typed
  thoughts and graph edges
- **Synthesises** the graph on a schedule (default daily) into a
  compiled Markdown wiki, perspective-typed by domain (client,
  project, person, news cluster, …)
- **Answers** questions via GraphRAG — hybrid retrieval over
  pgvector HNSW + Apache AGE traversal, with provenance-aware
  ranking and inline citations
- **Surfaces contradictions** (`find_contradictions`), open action
  items, and gaps in your knowledge through an MCP server and a
  capture API

It is *not* a notes app, not a search wrapper around your files, and
not a chatbot. It is a system that processes your knowledge on its
own clock against your data.

## When Exocortex makes sense

You probably want Exocortex if:

- You already have a substantial body of personal notes (a few
  hundred files at minimum) and the volume has stopped being
  manageable by hand
- You want the system to surface things — contradictions, forgotten
  notes, knowledge gaps — without you having to ask
- You are comfortable running Postgres in Docker on a small VPS or
  a self-hosted server, and reading enough YAML to configure a few plugins
- You want plain Markdown as the rendered output, on disk, so any
  editor (Obsidian, vim, VS Code) keeps working

You probably do *not* want Exocortex if:

- You are looking for a notes app with sync and a polished mobile UI
  — Obsidian or Notion are still better at that, and Exocortex
  treats both as surfaces, not replacements
- You have under a hundred notes and process them by hand without
  pain — the system's overhead is wasted on small corpora
- You are not comfortable self-hosting; there is no managed version
  and the license does not allow anyone to offer one

## Architecture in one diagram

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

The graph (L2) is canonical. Surfaces (L3) are regenerated from it.
**Edits go to L1; nothing edits L2 directly.** See
[docs/architecture/overview.md](docs/architecture/overview.md) for the long version.

## Quick start (5 min)

Walk through [`examples/hello-world/`](examples/hello-world/) — a
self-contained guide that takes you from `docker compose up` to your
first synthesised page in under five minutes, with no plugins and a
toy vault.

## Examples

- [`examples/hello-world/`](examples/hello-world/) — minimal, no
  plugins, ~5 min
- [`examples/acme-corp/`](examples/acme-corp/) — a fictional company
  plugin with a custom perspective, MCP tool, and domain compiler
  in ~150 lines

## Documentation

Full docs site: **<https://exocortex.zone/>**
(also browsable as Markdown under [`docs/`](docs/)).

- [Architecture overview](docs/architecture/overview.md) — the layers,
  the graph, the plugin system
- [Writing a plugin](docs/guides/writing-a-plugin.md) — the five extension
  points end-to-end, walked through the `acme-corp` example
- [`plugins/README.md`](plugins/README.md) — short version of the
  plugin contract (registry API, entry points)

## Evidence: R&D in the open

[`dowody/`](dowody/) ("evidence" in Polish) is the public record of the
research and development done with Exocortex: how the evidence cycle works,
the roadmap, hypotheses, experiments and their results. Every document exists
in Polish and in English. Documents come from the author's vault through the
[publisher](deploy/gate/), which runs every change through the
publishing gate first:

- [`tools/leakgate`](tools/leakgate/) — hashed denylist of client and person
  names, personal-data detectors, file metadata, packages and container
  images; tested every night with planted canaries
- [`tools/simcheck`](tools/simcheck/) — similarity to the private corpus, so
  that reworded private material is caught too
- [`tools/paritycheck`](tools/paritycheck/) and
  [`tools/humanlint`](tools/humanlint/) — the Polish and English versions
  match, and the text does not read like unedited model output

Start with [the cycle](dowody/en/01-cycle.md) ([PL](dowody/pl/01-cycle.md))
and [the roadmap](dowody/en/02-roadmap.md) ([PL](dowody/pl/02-roadmap.md)).

### Where the public history starts

The history of this repository starts in September 2026. Exocortex was
developed earlier in a private repository whose history also contains client
material, so that history is not published. The code was brought over through
an explicit allowlist ([`tools/export`](tools/export/)), example configuration
was rewritten with fictional data, and comments and docstrings were
translated to English. Some user-facing strings in the engine (wiki headings,
bot replies) are still in Polish; that is known and tracked in the roadmap.

## License

Apache 2.0 with the Commons Clause — see [`LICENSE`](LICENSE),
[`NOTICE`](NOTICE), [`ATTRIBUTION.md`](ATTRIBUTION.md), and
[`docs/legal/license.md`](docs/legal/license.md)
for the plain-language version. Short form: use it, modify it, build
on it; you cannot resell Exocortex itself or run it as a paid SaaS.
