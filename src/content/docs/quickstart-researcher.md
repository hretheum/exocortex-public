---
title: "Quickstart: Researcher"
description: "Set up Exocortex for literature review, synthesis, and idea tracking"
---

If you read more than you can remember, take notes you never revisit, and feel like your reading list has become a graveyard of good intentions — this is for you.

## What you get

- **Automated synthesis of papers and articles** — overnight, clusters of related notes become "perspective" documents that summarize what your sources collectively say
- **Resurfacing engine** — an SM2-style spaced repetition algorithm resurfaces important notes based on decay + graph proximity (the more connected a note is, the more often it comes back to you)
- **Gap Radar** — weekly report identifying topic clusters that are under-explored or missing decisions
- **Contradiction detection across sources** — when two papers say different things about the same construct, you find out

## Prerequisites

- Docker (Desktop or engine)
- An Obsidian vault, or just a folder of `.md` files

## Step 1: Start the stack

```bash
git clone https://github.com/hretheum/exocortex
cd exocortex
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up -d --build
```

## Step 2: Point the vault at your notes

Edit `.env`:

```bash
EXOCORTEX_VAULT_PATH=/Users/you/Documents/research-vault
```

Then restart:

```bash
docker compose restart vault-watcher
```

## Step 3: Ingest existing notes

If you already have hundreds of notes, bulk-ingest them once:

```bash
docker compose exec api python -m exocortex ingest --vault /vault
```

This walks the vault, extracts thoughts, generates embeddings, and builds the initial graph. Expect ~1 minute per 100 notes.

## Step 4: Let it synthesize overnight

Synthesis runs at **03:00 UTC** by default (configurable). After the first night, check:

```bash
ls /your-vault/wiki/by-topic/
```

You'll see auto-generated perspective documents grouped by topic cluster — each one citing the source notes it was synthesized from.

## The resurfacing engine

Important notes don't stay important by themselves — they need to come back to you. Exocortex implements **SM2** (the SuperMemo algorithm used by Anki) over your notes, weighted by graph proximity to recent activity.

Concretely:
- A note you wrote 3 months ago that connects to something you read yesterday gets surfaced **today**
- A note in an isolated corner of the graph gets surfaced **less often** (it has lower expected value to your current thinking)
- You can manually mark a note as "I'm done with this" to stop resurfacing

The surface for this is the **Resurfacing** pane in `wiki/_home.md` — refreshed nightly.

## The Gap Radar

Weekly (Sunday 22:00 UTC by default), Gap Radar emits a report into `wiki/gap-radar/YYYY-WW.md`:

- Topic clusters with **many sources but no synthesis**
- Clusters where the **last activity was >60 days ago**
- Topics where you've captured **2+ contradicting positions** but never resolved them

## Screenshot

![Gap Radar weekly report](/screenshots/placeholder-gap-radar.svg)

## A research workflow that works

1. **Capture freely** — drop a `.md` per paper in your vault, write notes in your own words. Don't try to organize.
2. **Let synthesis run nightly** — wake up to perspectives that connect papers you didn't realize were related.
3. **Trust the resurfacing pane** — don't manage a reading list, let the system tell you what's relevant *now*.
4. **Review the Gap Radar weekly** — it tells you where your thinking is thin.
5. **Use MCP `ask()` while writing** — pull quotes and citations from your own corpus with a single tool call from Claude Desktop.

## Next steps

- [Configure synthesis cadence and thresholds](/getting-started/configuration/)
- [Understand the knowledge layers](/architecture/knowledge-architecture/) — source / graph / query memory
- [MCP tools reference](/guides/mcp-tools/) — pull from your corpus while writing
