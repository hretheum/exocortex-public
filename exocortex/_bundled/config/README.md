# `config/`

Configuration surface for Exocortex. Two kinds of files live here.

## 1. Shipped defaults (committed, edit in place)

These ship with the repo as a working baseline. Edit the file directly to
customise; there is no separate `.example` copy.

| File | What it drives |
|------|----------------|
| `tag_taxonomy.yaml`   | LLM tag extraction vocabulary (F3) |
| `llm_routing.yaml`    | `llm_router` provider routing per use-case |
| `wiki_schema.yaml`    | Domain-set the wiki compiler emits |
| `home_sections.yaml`  | Section ordering for `wiki/_home.md` |
| `live_sections.yaml`  | Live-section registry (event/cron-driven compiles) |

These do not contain any operator-specific data, so they stay in version
control as-is. Tweak in place if you want different defaults.

## 2. User-customisable (gitignored, generated from `*.example.yaml`)

For each file below the repo ships a `<name>.example.yaml`. `exocortex init`
copies it to `<name>.yaml`, which is gitignored so your local edits don't
leak into commits.

| File | Holds |
|------|-------|
| `projects.yaml`            | Your client / sub-project registry (`classifier.py`) |
| `sources.yaml`             | Vault-watcher + RSS + Gmail adapter config (F6.x) |
| `auto_tag_taxonomy.yaml`   | Closed-vocab list used by `scripts/auto_tag_tasks.py` |
| `news_topic_clusters.yaml` | Newsletter cluster slugs (F8.8 aggregator) |
| `work_tag_clusters.yaml`   | Bootstrap groups for `work_tag_group` edges |
| `integrations.yaml`        | Internal email domain (F31.8.1) |
| `graph_rag.yaml`           | GraphRAG system-prompt config (F31.8.2) |

Loaders fall back to `*.example.yaml` if the corresponding `*.yaml` is
missing, so the repo stays runnable in a fresh clone (e.g. CI) — but you
should still run `exocortex init` before doing real work.

## 3. `.env`

Required environment variables live in `.env` at the repo root (note: **not**
inside `config/`). The template is `config/.env.example`. `exocortex init`
will copy and optionally fill the two REQUIRED values:

- `EXOCORTEX_VAULT_PATH` — absolute path to your Obsidian vault.
- `DATABASE_URL` — Postgres connection string for `exocortex migrate`.

Everything else in `.env.example` is optional and commented out by default;
uncomment what you need.

## Quick start

```bash
# 1. Scaffold local config + .env
exocortex init

# 2. Apply schema
exocortex migrate up

# 3. (optional) edit config/*.yaml to match your data — `projects.yaml` and
#    `auto_tag_taxonomy.yaml` are the two most opinionated files.
```

Re-running `exocortex init` is safe — it never overwrites a file that
already exists. Pass `--force` to regenerate from the examples.
