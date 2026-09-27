---
title: "Roadmap"
description: "What we have built, what we are working on, and where Exocortex is headed"
---

This page tracks what we've built, what we're working on, and where Exocortex is headed.

We ship in stages — each stage is usable on its own, and each one makes the next stage possible.


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
- [x] **Migration runbook** — step-by-step guide for moving from systemd to Docker without losing data

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
