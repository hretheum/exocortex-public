---
title: Configuration
---

# Configuration

Exocortex reads three layers of configuration. They're applied in this
order — later sources override earlier ones:

1. **Bundled defaults** — `exocortex/_bundled/config/*.example.yaml`,
   shipped inside the wheel
2. **User config** — `config/*.yaml` in the working directory (created
   by `exocortex init` from the matching `*.example.yaml`)
3. **Environment variables** — `DATABASE_URL`, `OPENAI_API_KEY`, etc.
   override individual settings at process start

## First run

```bash
# Inside the repo (dev) or any working directory (pip-installed):
exocortex init
```

`exocortex init` copies every `*.example.yaml` that isn't already
present, leaves existing user-customised files alone, and creates a
`.env` skeleton. It is idempotent — re-running on an initialised
directory is a no-op.

## The env file

`.env` (and `/etc/exocortex.env` for systemd-managed installs) holds
secrets and infrastructure URLs:

```bash
# Database — psycopg-style URL. Exocortex parses it via Pydantic
# Settings; individual PG_* overrides are also honoured.
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/exocortex

# Tenant — Exocortex is multi-tenant-aware at the row level. Pick any
# stable UUID; you only need to change this if you run multiple
# logically separated knowledge bases against one Postgres.
TENANT_ID=00000000-0000-0000-0000-000000000001

# LLM providers — llm_router fan-out. At least one is required for the
# `ask` MCP tool to return a synthesised answer.
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional — a self-hosted OpenAI-compatible server (llama.cpp,
# llama-swap) instead of paid APIs. EXOCORTEX_LLM_ROUTING picks the
# routing file; OPENAI_BASE_URL sends embeddings to the same server.
# EXOCORTEX_LLM_ROUTING=config/llm_routing.selfhosted.yaml
# LOCAL_LLM_API_KEY=local
# LLM_ROUTER_OPENAI_TOOL_CHOICE=auto
# OPENAI_BASE_URL=http://127.0.0.1:8080/v1
# EXOCORTEX_EMBEDDING_MODEL=bge-m3

# Optional — fallback router behaviour. Default is on; set to `off` to
# fail hard instead of cascading providers.
LLM_ROUTER_FALLBACK=on

# Vault root — used by the wiki compiler for output and by the vault
# watcher for ingest. Defaults to ./vault/ relative to the working
# directory. Canonical name across systemd units, docker-compose, and
# the bootstrap script.
EXOCORTEX_VAULT_PATH=./vault
```

## The YAML files

`config/` holds opinionated, project-specific configuration. None of
these are required for the engine to start, but most plugins assume
at least `projects.yaml` exists.

| File | Purpose | Example shipped at |
|---|---|---|
| `projects.yaml` | Client/project registry, person tag mapping | `_bundled/config/projects.example.yaml` |
| `tag_taxonomy.yaml` | Five-axis tag taxonomy used by the synthesiser | `_bundled/config/tag_taxonomy.example.yaml` |
| `sources.yaml` | RSS feeds + vault watch rules | `_bundled/config/sources.example.yaml` |
| `integrations.yaml` | Notion / Gmail / Telegram integration settings | `_bundled/config/integrations.example.yaml` |
| `graph_rag.yaml` | GraphRAG retrieval tuning (top-k, hop count, weights) | `_bundled/config/graph_rag.example.yaml` |
| `llm_routing.yaml` | Provider and model per use case (default: hosted APIs) | `config/llm_routing.yaml` |
| `llm_routing.selfhosted.yaml` | The same for a local server on `127.0.0.1:8080`; select with `EXOCORTEX_LLM_ROUTING` | `config/llm_routing.selfhosted.yaml` |

All user-edited files in `config/` are gitignored by default — your
secrets and project names never end up in version control unless you
explicitly stage them.

## Plugins

Plugins discover configuration through the same `config/` directory,
either by reading a file directly or by registering a Pydantic Settings
class against an `EXOCORTEX_PLUGIN_<NAME>__*` prefix. See
[Writing a plugin](../guides/writing-a-plugin.md) for the patterns.

## Verifying the setup

```bash
# Show resolved settings (secrets redacted)
exocortex query --diag settings

# Show registered plugins
exocortex query --diag plugins

# Show database connectivity + migration state
exocortex migrate status
```

If any of these fail, the error message points at the missing variable
or file.

## Next steps

- [Quickstart](quickstart.md) — five-minute end-to-end smoke
- [Writing a plugin](../guides/writing-a-plugin.md) — extend the
  engine for your domain
- [Architecture overview](../architecture/overview.md) — L1/L2/L3
