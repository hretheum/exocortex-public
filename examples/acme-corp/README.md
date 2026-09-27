---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 — examples/acme-corp/ README (showcase + smoke fixture)"
title: ACME Corp — Exocortex example plugin
---

# ACME Corp — Exocortex example plugin

This directory is a **fully working community plugin** for a fictional
client called **ACME Corp**. It exists for two purposes:

1. **Documentation by example.** Read this directory end-to-end to learn how
   to build your own Exocortex plugin: a perspective, an MCP tool and a
   wiki domain compiler.
2. **Smoke-test fixture.** F31.9.5 (the CI smoke job) uses this exact
   directory as input. Running every command below on a clean Docker
   Compose stack must succeed.

ACME Corp is fictional. The two sub-projects (`acme-platform`,
`acme-revamp`), the people (Jan, Anna, Piotr, Tomasz), the numbers and the
decisions are all invented for the showcase.

## Layout

```
examples/acme-corp/
├── README.md                ← you are here
├── .gitignore               ← ignores output/, .env
├── config/
│   ├── projects.yaml        ← clients + sub-projects registry (ACME + acme-platform + acme-revamp)
│   └── tag_taxonomy.yaml    ← 30 ACME-relevant tags on 5 axes
├── notes/                   ← 7 sample notes (ingested by `exocortex ingest --from notes/`)
│   ├── 2026-04-15-acme-platform-kickoff.md
│   ├── 2026-04-22-acme-q3-roadmap.md
│   ├── 2026-05-01-acme-margin-review.md
│   ├── 2026-05-08-acme-revamp-discovery.md
│   ├── 2026-05-15-acme-quarterly-review.md
│   ├── people/jan-kowalski.md
│   └── decisions/2026-04-22-pricing-model-shift.md
├── output/                  ← (gitignored) compiled wiki lands here
└── plugin/                  ← installable Python package (`pip install -e plugin/`)
    ├── pyproject.toml       ← declares entry-point `acme = exocortex_plugin_acme:setup`
    └── exocortex_plugin_acme/
        ├── __init__.py      ← `setup(registry)` — registers 3 extension points
        ├── perspectives.py  ← AcmeClientReview (synth one summary per quarter)
        ├── mcp_tools.py     ← AcmeQuarterlyStatus (read-only DB peek)
        └── wiki/__init__.py ← AcmeDomainCompiler (renders wiki/acme/_index.md)
```

## Extension points exercised

| Point             | Class                  | What it does |
|-------------------|------------------------|--------------|
| `perspective`     | `AcmeClientReview`     | Groups ACME-tagged thoughts by quarter, asks LLM for a 4-paragraph executive summary. |
| `mcp_tool`        | `AcmeQuarterlyStatus`  | Returns counts of ACME thoughts grouped by project + type. Pure SQL, no LLM. |
| `compile_domain`  | `AcmeDomainCompiler`   | Renders `acme/_index.md` + `by-project/*.md` + `by-type/*.md` under `$WIKI_OUTPUT_PATH`. |

The plugin does **not** exercise `capture_processor` or `live_section` — those
are documented in the main Exocortex docs.

## Quickstart

```bash
# 1. Bring the engine up (from repo root)
docker compose up -d --build
docker compose exec api exocortex migrate up

# 2. Install the plugin into the api container
docker compose exec api pip install -e examples/acme-corp/plugin/

# 3. Drop ACME config in place (override the bundled defaults)
docker compose exec api cp examples/acme-corp/config/projects.yaml     config/
docker compose exec api cp examples/acme-corp/config/tag_taxonomy.yaml config/

# 4. Ingest the 7 sample notes
docker compose exec api exocortex ingest --from examples/acme-corp/notes

# 5. Run the ACME perspective for Q2 2026
docker compose exec api exocortex synth \
    --perspective acme_client_review --key 2026-q2

# 6. Compile the ACME wiki domain
WIKI_OUTPUT_PATH=examples/acme-corp/output/wiki \
    docker compose exec api exocortex compile --domain acme

# 7. Ask a question that should hit the margin-review note
docker compose exec api exocortex query \
    "what does ACME say about Q3 margin pressure"
```

## Verifying the plugin is discovered

```bash
docker compose exec api python -c "
from importlib.metadata import entry_points
for ep in entry_points(group='exocortex.plugins'):
    print(ep.name, '->', ep.value)
"
# Expected output includes:
#   acme -> exocortex_plugin_acme:setup
```

## Authoring your own plugin

1. Copy this directory: `cp -r examples/acme-corp/plugin ~/my-plugin`
2. Rename `exocortex_plugin_acme` → `exocortex_plugin_<your-client>` everywhere
3. Edit `pyproject.toml`:
   - `name = "exocortex-plugin-<your-client>"`
   - `[project.entry-points."exocortex.plugins"]` — change the entry name
4. Replace the SQL filter in `perspectives.py` /  `mcp_tools.py` /
   `wiki/__init__.py` (`metadata->>'client' = 'acme'`) with your own slug
5. `pip install -e ~/my-plugin` — the engine picks it up on next start

That's it. No core fork, no patches, no monorepo coupling.
