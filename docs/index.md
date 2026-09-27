---
title: Exocortex
---

# Exocortex

> *A personal knowledge OS that thinks while you sleep.*

Exocortex reads your meetings, newsletters, and notes — builds a knowledge graph from them — and surfaces what matters before you know you need it. You think; the engine remembers, connects, and compiles.

[→ Get started in 5 minutes](getting-started/quickstart.md)   [→ Why Exocortex](why-exocortex.md)   [GitHub ↗](https://github.com/hretheum/exocortex)

---

## The problem with second brains

You read 50 articles a month and remember 3. Your meeting notes are buried in a vault you never re-read. Your decisions aren't connected to the knowledge that should inform them.

Most "second brain" tools make *storage* easier. Exocortex makes *thinking* automatic.

---

## What it does

- **You never manually capture again** — meetings, newsletters, RSS, and any Markdown file you drop in your vault arrive automatically. Fireflies, Gmail, RSS, direct Markdown — all routed on a schedule.
- **Your knowledge connects itself** — every fact becomes a node, and relationships are typed (`causes →`, `contradicts →`, `cited_in →`). You stop hunting for context because the graph already knows what links to what. Powered by Postgres + pgvector + Apache AGE.
- **Your wiki rewrites itself overnight** — an LLM runs nightly over the graph and regenerates `wiki/` from scratch: meeting summaries, client dossiers, topic deep-dives, contradiction flags. You wake up to a refreshed second brain.
- **You ask, your own knowledge answers** — 16 MCP tools give Claude (or any MCP client) GraphRAG retrieval over *your* knowledge, with ranked source provenance. Not web search. Your history.
- **You stop forgetting what mattered** — SM2 spaced repetition over the graph, weighted by current relevance instead of just temporal decay. The things you needed to remember resurface on their own.
- **You see what's missing before you notice it** — `gap_analysis` flags dense thought clusters with no synthesis, orphan notes, and unresolved contradictions older than 30 days. The gaps in your thinking become visible.
- **You wake up briefed** — Night Shift perspective runs at 05:00 UTC and pushes contradictions, pattern shifts, and overdue action items to Telegram. The day starts with signal, not inbox.
- **You work in Notion, the graph follows** — check a task in Notion and every surface updates; ask a question in a Notion field and get a cited answer back. Bidirectional cockpit, no context switching tax.

---

## Who is this for

**Consultants and knowledge workers** managing multiple clients or projects — context needs to travel with you, not live in your head.

**Developers building on AI** — 16 MCP tools give Claude (or any MCP client) typed GraphRAG access to your knowledge. Not web search. *Your history.*

**Researchers and writers** who capture extensively and synthesize rarely — Gap Radar finds what's waiting to be written.

→ [Detailed use cases and personas](use-cases.md)

---

## How it works

**1. It captures** — drop a file, finish a meeting, save a link. The capture API picks it up automatically.

**2. It builds** — every captured item becomes typed nodes and edges in a Postgres graph. Relationships are explicit: `contradicts`, `decided_in`, `supersedes`, `cites`.

**3. It delivers** — nightly compilation rebuilds your wiki. Morning Telegram briefing. MCP tools for on-demand queries. Gap Radar for weekly nudges.

→ [Architecture deep dive](architecture/overview.md)

```
Sources          Graph (Postgres)     Wiki (Markdown)    Query
─────────────    ────────────────     ───────────────    ─────
Obsidian .md  →  thoughts             _home.md        →  MCP tools (15)
Gmail / RSS   →  + pgvector           clients/*.md       GraphRAG ask
Fireflies     →  + AGE graph          meetings/*.md      Telegram bot
Notion tasks  →  edges (35 types)     by-tag/*.md
```

---

## When it makes sense

- You generate more notes than you can manually revisit.
- You want a system that **surfaces connections**, not just stores links.
- You're comfortable with a local Postgres + Python stack.
- You want LLM reasoning over *your own graph*, not a cloud knowledge base.

It does **not** make sense if you want a hosted SaaS, a drag-and-drop UI,
or a system another person manages for you.

---

## A real example

```
You: "What did I decide about the auth architecture last quarter?"

Exocortex: Based on 3 synthesised notes and 2 meeting summaries from Oct–Dec:
  → Decision: JWT stateless, no session store (2024-11-14, meeting with @alice)
  → Contradicted by: email thread 2024-12-03 — "reconsider session invalidation"
  → Action item (unresolved): spike Redis session store before v2 launch

Sources: [meeting:acme-2024-11-14] [email:thread-4a2f] [note:auth-spike-dec]
```

---

## Where to go from here

| If you want to… | Start with |
|---|---|
| Run Exocortex in 5 minutes | [Quickstart](getting-started/quickstart.md) |
| Configure for your own vault | [Configuration](getting-started/configuration.md) |
| Understand the full design | [Why Exocortex](why-exocortex.md) |
| Build a plugin from scratch | [Writing a plugin](guides/writing-a-plugin.md) |
| Look up an MCP tool | [MCP tools reference](guides/mcp-tools.md) |
| Understand the architecture | [Architecture overview](architecture/overview.md) |

---

## Under the hood

Self-hosted on **Postgres 16 + pgvector + Apache AGE** — one Postgres instance carries the graph, embeddings, and relational schema. No separate vector database, no managed graph service.

`docker compose up -d --build` starts the full stack. Reference deployment: $24/mo DigitalOcean droplet.

→ [Architecture overview](architecture/overview.md) · [Plugin system](why-exocortex.md#3-the-plugin-system) · [Design principles](why-exocortex.md#7-design-principles)

---

**GitHub:** [hretheum/exocortex](https://github.com/hretheum/exocortex) ·
**PyPI:** `pip install exocortex-os` ·
**Docker:** `ghcr.io/hretheum/exocortex:v0.1.0`
