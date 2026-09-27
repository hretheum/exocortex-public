# Roadmap

This page tracks what we've built, what we're working on, and where Exocortex is headed.

We ship in stages — each stage is usable on its own, and each one makes the next stage possible.

---

## What We've Built — v0.1.0

Released 2026-05-24 · [Release notes →](https://github.com/hretheum/exocortex/releases/tag/v0.1.0)

### Core engine

- **Plugin registry** with six extension points — perspectives, MCP tools, compile domains, capture processors, live sections, and source pollers
- **Perspective registry** — 10+ built-in synthesis perspectives (client, project, monthly, tag, type, news cluster, FRP, night-shift briefing, gap radar, and more)
- **`exocortex migrate`** — schema versioning with ordered SQL migrations
- **`exocortex init`** — interactive first-run setup (vault path, API keys, database connection)
- **Pydantic Settings** — all configuration via environment variables, no hard-coded paths
- **Modular wiki compiler** — `wiki_compiler.py` refactored from 8066 lines to a 419-line facade plus a `wiki/` package (F31.6); domains register through entry points

### Deployment

- **Docker Compose** — PostgreSQL 16 + pgvector + Apache AGE in one command
- **VPS / bare-metal bootstrap** — `scripts/bootstrap_vps.sh` brings a fresh Ubuntu 24.04 droplet to a working install in under 15 minutes
- **systemd units** — `exocortex-*` services and timers (renamed from internal `second-brain-*`), all paths env-driven, installable via `deploy/install.sh`
- **CLI with 7 commands** — `init`, `ingest`, `synth`, `compile`, `serve`, `migrate`, `query`
- **GHCR image** — `ghcr.io/hretheum/exocortex:v0.1.0`
- **PyPI package** — `pip install exocortex-os`

### Examples & docs

- **`examples/acme-corp/`** — full working plugin with custom domain configuration
- **`examples/hello-world/`** — 5-minute quickstart for new users
- **GitHub Actions CI** — smoke tests on every push
- **Documentation site** at [exocortex.zone](https://exocortex.zone/)

### Features running in production

These features are implemented in the v0.1.0 engine and run daily on the maintainer's reference instance:

- **Night Shift Briefing** — daily 05:00 UTC perspective that delta-queries the last 24 h of thoughts, runs pattern detection (term-frequency spikes, embedding drift, contradictions), and pushes a plain-Polish narrative to Telegram
- **Resurfacing Engine** — daily SM2 spaced-repetition worker over the knowledge graph; surfaces 3–5 relevant past notes per day weighted by graph distance and provenance
- **Two-Way Notion Cockpit** — bidirectional sync with action resolution; check a task in Notion, the graph updates and every surface follows
- **Telegram bot** — intent classifier, `graph_fact_check` against your own history, push notifications for briefings and contradictions
- **Gap Radar** — `gap_analysis` MCP tool plus a weekly synthesis perspective; finds dense thought clusters with no synthesis, orphan notes, unresolved contradictions, and dead taxonomy edges
- **Notion sync** — differential publish pipeline (499/501 pages on the reference instance)

### MCP tool surface

The v0.1.0 server exposes **16 built-in MCP tools**: `search_thoughts`, `expand_node`, `synthesize`, `find_action_items`, `find_contradictions`, `ask`, `gap_analysis`, plus the FRP workflow (`query_content_queue`, `create_frp_session`, `append_session_thought`, `complete_session`, `add_revisit`, `enqueue_generated_frp_story`) and promotion tools (`promote_action_items`, `unpromote`, `list_promoted`). Plugins add more — see the [MCP tools reference](guides/mcp-tools.md).

---

## Stage 1 — Developer Package (in progress)

**Goal:** a developer with basic Python/Linux skills can clone the repo and have Exocortex running in 30 minutes on a fresh Ubuntu VPS — without reading internal notes.

Foundation is shipped (F31.7–F31.10). Packaging polish is the current focus.

### Done

- [x] **systemd units renamed** — `second-brain-*` → `exocortex-*`, all paths env-driven, includes `install.sh`
- [x] **VPS bootstrap script** — `scripts/bootstrap_vps.sh` on clean Ubuntu 24.04 → working instance in <15 min (Postgres + AGE + pgvector + venv + systemd). See [VPS / Bare Metal](getting-started/vps-bare-metal.md).
- [x] **Architecture docs migrated to public repo** — L1/L2/L3 knowledge layers, source-pipeline pattern, and module-system design now live under [Architecture](architecture/overview.md), sanitised of private context.
- [x] **CLI works from wheel install** — `pip install exocortex-os && exocortex --help` no longer requires an editable install.

### In progress (~10h remaining)

- [ ] **llm_router on PyPI** — publish as `exocortex-llm-router` so `pip install exocortex-os exocortex-llm-router` is the full install story
- [ ] **requirements.txt cleanup** — remove stale package reference, fix Procfile module paths
- [ ] **Unified `.env.example`** — one canonical file, every variable documented, consistent naming (`EXOCORTEX_VAULT_PATH` everywhere)

---

## Stage 2 — One-Command Deploy ✅ DONE 2026-05-25

**Goal:** `docker compose up` brings up the complete Exocortex stack — database, all workers, job scheduler, optional Telegram bot — on any machine. No systemd, no Python version management, no Postgres compilation.

Shipped in commit `4e0f59f`. Six containers healthy on `docker compose up -d --build`. See [Docker Deployment](getting-started/docker-deployment.md).

### Done

- [x] **All workers as Docker services** — notify-listener, scorer, vault-watcher added to Compose using a shared `x-worker-base` anchor
- [x] **Scheduler container** — supercronic replaces systemd timers; all scheduled jobs (ingest, synth, compile) run from one container
- [x] **Telegram bot profile** — `docker compose --profile telegram up` with proper env validation
- [x] **llm_router bundled in Docker image** — vendored under `vendor/`, no external dependency for LLM routing
- [x] **Local vault override** — `docker-compose.override.yml.example` for bind-mounting an existing Obsidian vault
- [x] **Docker deployment guide** — local laptop + remote VPS walkthrough with troubleshooting
- [x] **TLS overlay** — `docker-compose.prod.yml` with Caddy ACME automatic cert renewal
- [x] **Migration runbook** — [systemd → Docker](migration/systemd-to-docker.md) without losing data

### In progress

- [ ] **GHCR pre-built DB image** — `ghcr.io/hretheum/exocortex-db:pg16-age1.6.0` (CI wired, push pending first GH Actions run)
- [ ] **E2E smoke test** — GitHub Actions validates full `docker compose up` stack on every push (CI wired, pending first run)

---

## On the Horizon — v0.2 and beyond

Designed, spec'd, or partially scaffolded; will move into a numbered stage once Stage 2 ships.

### MCP HTTP/SSE Transport (~8h)

Expose the MCP server over HTTP/SSE so remote clients (Claude Desktop on a different machine, a web app, a VS Code extension) can query Exocortex without a local process. Prerequisite for the multi-host Cockpit deployment and any browser-based UI.

### Module System extraction (~46h)

Promote optional integrations (Notion, Gmail, Telegram, Slack) from bundled core code to first-class modules — separate install extras, isolated config, opt-in via `EXOCORTEX_MODULES`. Designed in [Architecture / Module System](architecture/module-system.md); first reference extraction is Notion.

### Scoped MCP tokens & query memory

Multi-tenant safety: tokens scoped to a subset of clients/projects (`scope=['client_a']` cannot see `client_b` data), query log promoted to a searchable entity (Question/Answer nodes with embeddings), and answer-promotion-with-human-review (Phase 3 of [Knowledge Layers](architecture/knowledge-architecture.md)).

### Calendar as a source

Pull tomorrow's calendar in as `pending_meeting` thoughts so the system pre-briefs you. Pairs naturally with the Night Shift perspective.

### Team / multi-user deployment

Once scoped tokens land, the same engine should run as a small shared service for a team — separate tenants per user, shared graph for shared projects, role-based MCP tool exposure.

---

## Philosophy

We build Exocortex incrementally — each version should be useful on its own, not just a stepping stone. We don't ship half-finished abstractions.

We follow Nate's source-of-truth rule (see [Architecture overview](architecture/overview.md)): never duplicate data, always know where a fact lives, make the computer do the bookkeeping.

Contributions welcome — see [CONTRIBUTING.md](https://github.com/hretheum/exocortex/blob/main/CONTRIBUTING.md) and the [open issues](https://github.com/hretheum/exocortex/issues).

---

*Last updated: 2026-05-25. Estimates are rough — complexity varies. Items may shift as we learn.*
