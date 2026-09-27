---
title: "Writing a Plugin"
description: "Extend Exocortex with custom sources, processors, sinks, or MCP tools"
---

Plugins are how you teach Exocortex about *your* world — a client, a
hobby, a research domain, a Notion database. The engine ships with the
common-case scaffolding (vault watcher, capture API, GraphRAG, MCP
server, daily synthesiser, wiki compiler); a plugin layers domain
knowledge on top by registering one or more of **five extension
points**.

This guide walks the full loop from empty directory to working install,
using the bundled [`examples/acme-corp/`](https://github.com/hretheum/exocortex/tree/main/examples/acme-corp)
plugin as the reference. ACME is a fictional client; everything below
is real, runnable code you can copy.

## The five extension points

| Point | Base class | Identity | What it does |
|---|---|---|---|
| `perspective` | `PerspectiveType` | `.name` | Recipe for one synthesis row — select thoughts, build prompt, parse LLM reply |
| `mcp_tool` | `McpTool` | `.name` | Custom MCP tool exposed to Claude Desktop / CLI / Telegram |
| `compile_domain` | `DomainCompiler` | `.name` | Renders a slice of the wiki (e.g. `wiki/acme/_index.md`) from the graph |
| `capture_processor` | `Processor` | `.source_type` | Turns a `POST /capture` payload of one source type into thoughts + edges |
| `live_section` | `SectionGenerator` | `.name` | Block of Markdown injected into a wiki page on event triggers (Notion change, scheduled cron) |

You only register what you need. Many plugins register just one
perspective. The ACME example exercises three (perspective, MCP tool,
domain compiler).

## The `setup(registry)` contract

Every plugin exposes exactly one function:

```python
from exocortex.core.registry import Registry

def setup(registry: Registry) -> None:
    """Called once at engine startup."""
    registry.register_perspective(MyPerspective())
    registry.register_mcp_tool(MyTool())
    registry.register_compile_domain(MyCompiler())
    # registry.register_capture_processor(...)
    # registry.register_live_section(...)
```

The engine calls `setup()` once per plugin during
`Registry.discover()`, which runs before any CLI subcommand
dispatches. Two discovery channels:

1. **Production** — declared as a `pyproject.toml` entry point. Picked
   up via `importlib.metadata.entry_points(group="exocortex.plugins")`.
2. **Dev-time** — dropped under `plugins/<name>/` in the repo root.
   Picked up by directory scan; no `pip install` needed.

We'll use both below.

## Tutorial — build the ACME plugin in five steps

### 1. Create the package skeleton

```
plugin/
├── pyproject.toml
└── exocortex_plugin_acme/
    ├── __init__.py        ← exposes setup(registry)
    ├── perspectives.py    ← AcmeClientReview
    ├── mcp_tools.py       ← AcmeQuarterlyStatus
    └── wiki/__init__.py   ← AcmeDomainCompiler
```

The package name doesn't have to start with `exocortex_plugin_` — that's
just a convention. The entry-point key (`acme` below) is what shows up
in logs.

### 2. Wire `setup()`

```python
# exocortex_plugin_acme/__init__.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exocortex.core.registry import Registry


def setup(registry: "Registry") -> None:
    # Imports are local so that loading plugin metadata
    # (e.g. for `importlib.metadata.entry_points` listing)
    # doesn't drag in the full runtime.
    from .perspectives import AcmeClientReview
    from .mcp_tools import AcmeQuarterlyStatus
    from .wiki import AcmeDomainCompiler

    registry.register_perspective(AcmeClientReview())
    registry.register_mcp_tool(AcmeQuarterlyStatus())
    registry.register_compile_domain(AcmeDomainCompiler())
```

That's the whole entry surface. Everything else is implementation of
the three classes you just instantiated.

### 3. Register a perspective

A perspective produces one row in `syntheses`. The contract is three
methods: `select_thoughts → build_prompt → parse_response`. The synth
runner provides a context with `tenant_id` + `perspective_key`
(typically a slug like `2026-q2`).

```python
# exocortex_plugin_acme/perspectives.py
from datetime import datetime, timezone
from typing import Any
from exocortex.synth.perspectives.base import PerspectiveType


class AcmeClientReview(PerspectiveType):
    """One synthesis per (client=acme, quarter) — executive review."""

    @property
    def name(self) -> str:
        return "acme_client_review"

    def select_thoughts(self, ctx: Any) -> list[Any]:
        self._ctx = ctx
        from exocortex.db import query_all
        return list(query_all(
            """
            SELECT id, body_md, metadata, created_at
              FROM thoughts
             WHERE tenant_id = %s
               AND metadata->>'client' = 'acme'
               AND metadata->>'quarter' = %s
             ORDER BY created_at
            """,
            (ctx.tenant_id, ctx.perspective_key),
        ) or [])

    def build_prompt(self, thoughts: list[Any]) -> str:
        bullets = "\n".join(
            f"- {(t.get('metadata') or {}).get('title')}: "
            f"{(t.get('body_md') or '')[:160]}"
            for t in thoughts
        ) or "(no thoughts — produce an empty summary)"
        return (
            "Summarize the quarter for ACME Corp in 4 paragraphs:\n"
            "1. Shipped/decided  2. Slipped  3. Open risks  4. Next focus\n\n"
            f"Source thoughts:\n{bullets}\n"
        )

    def parse_response(self, response: str) -> dict[str, Any]:
        return {
            "perspective_type": self.name,
            "perspective_key": self._ctx.perspective_key,
            "body_md": response.strip(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
```

Run with:

```bash
exocortex synth --perspective acme_client_review --key 2026-q2
```

The router picks `AcmeClientReview` by `.name`, your method chain
fires, and the resulting row lands in `syntheses` with
`perspective_type='acme_client_review'`.

### 4. Register an MCP tool

An MCP tool is what Claude Desktop sees when it calls `tools/list`.
The contract is `.name`, `.schema` (JSON Schema for input args), and
`handler(args) -> result`.

```python
# exocortex_plugin_acme/mcp_tools.py
from typing import Any
from exocortex.mcp.tools.base import McpTool


class AcmeQuarterlyStatus(McpTool):
    @property
    def name(self) -> str:
        return "acme_quarterly_status"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "quarter": {
                    "type": "string",
                    "description": "Quarter slug, e.g. '2026-q2'.",
                },
            },
            "additionalProperties": False,
        }

    def handler(self, args: dict[str, Any]) -> dict[str, Any]:
        from exocortex.db import query_all
        quarter = args.get("quarter")
        where = "metadata->>'client' = 'acme'"
        params: tuple = ()
        if quarter:
            where += " AND metadata->>'quarter' = %s"
            params = (quarter,)
        rows = query_all(
            f"SELECT metadata->>'project' AS project, COUNT(*) AS n "
            f"  FROM thoughts WHERE {where} GROUP BY 1 ORDER BY 1",
            params,
        ) or []
        return {
            "quarter": quarter or "all",
            "by_project": [dict(r) for r in rows],
        }
```

!!! warning "SQL safety"
    The `where` fragment uses an interpolated literal because it's a
    hardcoded keyword. User input flows only through `%s` params. If
    you let callers pick column names or operators, validate against
    an allowlist — never `f-string` user input into SQL.

Restart the MCP server (`exocortex serve` or your supervisor), and the
tool appears in `tools/list`.

### 5. Register a wiki domain compiler

A domain compiler renders one slice of the wiki. The engine calls
`compile(ctx)` once per scheduled run; your job is to write Markdown
files under `ctx.output_root / self.name / …`.

```python
# exocortex_plugin_acme/wiki/__init__.py
from pathlib import Path
from typing import Any
from exocortex.wiki.domains.base import DomainCompiler


class AcmeDomainCompiler(DomainCompiler):
    @property
    def name(self) -> str:
        return "acme"

    def compile(self, ctx: Any) -> list[Path]:
        from exocortex.db import query_all
        # one index file + one per quarter
        out_dir = ctx.output_root / "acme"
        out_dir.mkdir(parents=True, exist_ok=True)

        quarters = [r["quarter"] for r in (query_all(
            "SELECT DISTINCT metadata->>'quarter' AS quarter "
            "  FROM thoughts WHERE metadata->>'client' = 'acme' "
            "  ORDER BY 1"
        ) or [])]

        index = out_dir / "_index.md"
        index.write_text(
            "# ACME — quarterly reviews\n\n"
            + "\n".join(f"- [[acme/{q}]]" for q in quarters) + "\n"
        )

        written = [index]
        for q in quarters:
            page = out_dir / f"{q}.md"
            page.write_text(f"# ACME — {q}\n\n(populated by synthesis)\n")
            written.append(page)
        return written
```

Run with:

```bash
exocortex compile --domain acme
```

Pages land under `$EXOCORTEX_VAULT_PATH/acme/`. Re-run is idempotent if
your writes are content-based; the bundled compilers hash-compare
before overwriting.

## Installing the plugin

### Dev-time — drop into `plugins/`

For iterative work, drop the package directly:

```bash
mkdir -p plugins/acme
cp -r path/to/exocortex_plugin_acme plugins/acme/
```

Layout becomes:

```
plugins/
└── acme/
    └── exocortex_plugin_acme/
        ├── __init__.py
        ├── perspectives.py
        └── ...
```

`Registry.discover()` scans `plugins/*/` at startup, imports each
sub-package, and calls its `setup()`. No `pip install` required —
edits land on next CLI invocation.

### Production — entry point

For deployments declare the entry point in *your plugin's*
`pyproject.toml`:

```toml
[project]
name = "exocortex-plugin-acme"
version = "0.1.0"
dependencies = ["exocortex>=0.1"]

[project.entry-points."exocortex.plugins"]
acme = "exocortex_plugin_acme:setup"
```

Then `pip install -e .` (or publish to a private index) inside the
same environment as Exocortex. The engine's
`importlib.metadata.entry_points(group="exocortex.plugins")` call
discovers it on next start.

You can ship both — `pip install` for prod, `plugins/` for dev. They
don't conflict; the registry is last-write-wins per `.name`.

## Verifying your plugin is loaded

```bash
exocortex query --diag plugins
```

Expected output (your name will appear in one of the five buckets):

```
perspectives:       acme_client_review, client, frp, ...
mcp_tools:          acme_quarterly_status, ask, search_thoughts, ...
compile_domains:    acme, work, 3d, ...
capture_processors: notion-task-sync, rss, ...
live_sections:      open_action_items, ...
```

If your plugin is missing:

| Symptom | Likely cause |
|---|---|
| Not in any bucket | `setup()` not called — check entry-point declaration or `plugins/<name>/__init__.py` exposes `setup` |
| `entry_points discovery failed` in logs | `pip install` was run against a different Python env than the one running `exocortex` |
| Name collision (e.g. `acme` overwrites built-in) | Last write wins — check `discover()` log lines |

## Cookbook

### Synthesise on a custom cadence

Don't hard-code "daily". Use the synth scheduler — your perspective
just needs to be addressable by `(perspective_type, perspective_key)`.
A weekly cron then runs `exocortex synth --perspective my_perspective
--key 2026-w22`.

### Read from the graph in an MCP tool

```python
from exocortex.graph import traverse_edges

def handler(self, args):
    paths = traverse_edges(
        seed_thought_id=args["thought_id"],
        edge_types=["supports", "contradicts"],
        max_depth=2,
    )
    return {"paths": [p.to_dict() for p in paths]}
```

`traverse_edges` is a Cypher wrapper over Apache AGE. Edge types are
declared in `schema/0X_edge_types.sql`; you can register new ones,
but the upstream 35-type taxonomy is usually enough.

### Live section bound to a Notion change

Register a `SectionGenerator` whose `.bound_to_event` is the
`notion_globex_updated` event the Notion source emits. The scheduler
fires your generator within ~15 s of the change and patches the
section in-place in the target wiki file (replacing the block
delimited by `<!-- live:my_section START/END -->`).

See [`docs/F16-live-sections-design.md`](https://github.com/hretheum/exocortex/blob/main/docs/F16-live-sections-design.md)
for the full event spec.

## Limits and known sharp edges

- **Two-phase init.** The synth runner constructs `PerspectiveType`
  instances *before* tenant context is available; do all DB / network
  work in `select_thoughts`, not `__init__`.
- **MCP tool schemas are JSON Schema 7-ish.** Anthropic's MCP client
  is permissive but Claude Desktop validates. Stick to plain
  `object`/`string`/`integer` with `description`.
- **Domain compilers must be idempotent.** The wiki output is
  source-controlled in many setups; non-deterministic order will
  churn the diff.
- **Plugin discovery is not idempotent.** `Registry.discover()`
  called twice will call `setup()` twice — last write wins per key,
  but two separate calls to `register_*` for the same instance is
  generally fine. The CLI calls it once per process.

## Where to go next

- [`examples/acme-corp/README.md`](https://github.com/hretheum/exocortex/blob/main/examples/acme-corp/README.md)
  — the full smoke-tested showcase, including the `notes/` corpus the
  CI job ingests.
- [Architecture overview](../architecture/overview.md) — L1/L2/L3 in
  short form. Understanding this prevents the "I edited the wiki and
  synth overwrote my changes" class of mistake.
- [`EXOCORTEX.md`](https://github.com/hretheum/exocortex/blob/main/EXOCORTEX.md)
  — the long design doc, including the source-of-truth rule and the
  full plugin system section.
