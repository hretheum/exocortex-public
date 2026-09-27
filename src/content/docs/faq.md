---
title: "FAQ"
description: "Frequently asked questions about Exocortex"
---

## How much does it cost to run?

Self-hosted: **~$6-24/mo** for a DigitalOcean droplet (the $6 nano works for small vaults; $24 4GB droplet recommended once you have a few thousand thoughts).

LLM API costs: **~$2-10/mo** depending on vault size and synthesis cadence. Most workloads route through cheap models (DeepInfra Qwen) via `llm_router`. There are no subscription fees — you only pay your infra + LLM provider directly.

## What LLMs does it use?

By default, **DeepInfra (Qwen)** for embeddings and synthesis (cheap and good enough for ~95% of tasks), and **Anthropic Claude** as fallback for complex reasoning (synthesis of contradictions, multi-perspective questions). The `llm_router` picks the cheapest capable model automatically based on the task type and falls back if a provider fails.

You can also point it at a local Ollama instance — everything will run on-device.

## Is my data private?

Yes. Everything runs on your own server. Your notes, meetings, and graph never leave your infrastructure **unless** you configure a cloud LLM API (Anthropic, OpenAI, DeepInfra) — in which case the text you send for synthesis goes to that provider under their API terms.

If you want zero data egress, use a local LLM (Ollama) for synthesis. Performance trade-off applies.

## What's the GDPR situation?

You control the data. Exocortex itself doesn't transmit anything outside your server.

- **If you use cloud LLM APIs**: their API terms apply to the text you send. Anthropic and OpenAI both offer zero-retention options on their API tier — enable those.
- **If you use self-hosted LLMs** (Ollama or DeepInfra private): everything stays local.
- **For EU users processing third-party personal data** (e.g. meeting notes mentioning clients), the same rules apply to Exocortex as to any tool you self-host. You are the data controller.

## How do I back up my data?

Two things to back up: PostgreSQL and the vault directory.

```bash
pg_dump exocortex > backup.sql
tar czf vault-$(date +%Y%m%d).tar.gz /opt/exocortex-vault
```

Schedule both daily, ship off-server. That's it.

## What happens if the server goes down?

Your Obsidian vault continues to work offline — it's just `.md` files. Syncthing (or whatever sync layer you use) re-syncs when the server is back up. The Postgres graph rebuilds from the vault on next ingest if you ever lose the DB entirely.

**No data loss** as long as you have either the vault or the Postgres dump.

## How is this different from a RAG chatbot?

RAG chatbots **answer questions** by retrieving chunks and stuffing them into an LLM prompt. They forget between sessions.

Exocortex **builds structured reasoning** over time:

- Typed edges (`supports`, `contradicts`, `derives_from`, `supersedes`) — not just embedding similarity
- Autonomous synthesis at night — clusters of related thoughts become Markdown perspectives
- Contradiction detection — when two sources disagree, the graph surfaces it
- Provenance tracking — human-written knowledge ranked higher than AI-generated to prevent feedback loops

It gets **smarter** the longer you use it, not just bigger.

## Can I use it with Obsidian?

Yes. The vault is just a directory of `.md` files with frontmatter. Obsidian reads it directly, and Exocortex writes back to it. Wikilinks, tags, and Dataview queries all work.

## Does it work without a Notion account?

Yes. Notion is optional (used by the Two-Way Cockpit feature for mirroring projects/tasks). Core functionality — synthesis, MCP, briefings, Gap Radar — works with just Obsidian + Telegram.

## Is it open source?

**Apache 2.0 + Commons Clause.**

- ✅ Free for personal use
- ✅ Free for non-commercial community use
- ✅ Modify, fork, run, share
- ❌ Selling services or products built on Exocortex requires a commercial license

See [the license explainer](/legal/license/) for plain-language details.
