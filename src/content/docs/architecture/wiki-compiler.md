---
title: "Wiki Compiler"
description: "Modular wiki compiler architecture introduced in F31.6"
---

The wiki compiler (`exocortex/wiki/`) transforms your vault's raw Markdown notes and database records into a structured, interlinked wiki output. This page documents the modular architecture introduced in F31.6 (2026-05-24).

## Package Structure

```
exocortex/wiki/
├── __init__.py          # Public API: compile_all, parse_source_file
├── wiki_compiler.py     # Thin facade (419 lines) — globals, re-exports, CLI
├── runner.py            # Registry-based compile_all orchestrator
├── core/
│   ├── io.py            # File I/O: _write_with_frontmatter, write_wiki
│   ├── edges.py         # Graph edge lookups (pgvector + AGE)
│   ├── user_state.py    # F11.4 invariant guardian: _merge_user_done_state
│   └── context.py       # RunContext dataclass (F31.6.5+)
├── util/
│   ├── slugs.py         # _safe_slug, slugify helpers
│   ├── dates.py         # Date formatting, timezone-aware
│   ├── classification.py # Tag/category classification helpers
│   └── coercion.py      # Type coercion utilities
└── domains/
    ├── base.py          # _LegacyDomainCompiler ABC
    ├── synthesis_render.py  # Shared synthesis renderers (F31.6.5+)
    ├── work/            # Meetings, clients, people, TODO, monthly
    ├── news/            # News aggregator, by-source/topic/category
    ├── frp/             # Futures Reading Protocol sessions
    ├── home/            # Cross-domain home dashboard
    ├── clippings.py     # Web clippings
    ├── live_sections.py # Live section event handler
    └── cross_domain.py  # Cross-domain link/backlink logic
```

## Layering Rule

Strict one-way import graph. Violations are tracked as audit BLOCKERs:

```
wiki_compiler.py (facade)
    ↓ imports
runner.py + domains/*
    ↓ imports
core/* + synthesis_render.py
    ↓ imports
util/*
    ↓ imports
(stdlib, psycopg, exocortex.db)
```

**Core may not import from domains or wiki_compiler.** Any `import exocortex.wiki_compiler` inside `core/` is an architecture violation.

## F11.4 Invariant

The most safety-critical invariant in the wiki compiler:

> `count([x] completed tasks in vault meetings) >= count([x] in DB action_items)`

Users manually toggle `[x]` checkboxes in meeting notes. These must survive every `compile_all` run unchanged.

**Guardian:** `wiki/core/user_state.py::_merge_user_done_state(new_body, existing_body)` — called unconditionally before every meeting page write. If the existing file is unreadable, a `log.warning` is emitted (never a silent `None`).

## RunContext (F31.6.5+)

After F31.6.5.1, globals are replaced by an explicit context object passed through the call chain:

```python
@dataclass
class RunContext:
    dry_run: bool = False
    current_run_id: str = ""
    full_rebuild: bool = False
    pages_written: list[str] = field(default_factory=list)
    llm_tokens_used: int = 0
```

`wiki_compiler.py` constructs `RunContext` from environment, passes it to `runner.compile_all(ctx)`.

## Domain Registry

Domains register themselves via Python entry-points:

```toml
# pyproject.toml
[project.entry-points."exocortex.wiki_domains"]
work = "exocortex.wiki.domains.work:WorkDomain"
news = "exocortex.wiki.domains.news:NewsDomain"
```

`runner.py` discovers them dynamically. New domains in plugins inherit `_LegacyDomainCompiler` and implement `compile(ctx: RunContext)`.

## Known Audit Findings

A post-refactor audit (2026-05-24, three parallel review agents — architecture, quality, defense) identified the following follow-up work. Status is tracked in the public [issue tracker](https://github.com/hretheum/exocortex/issues).

| Severity | Finding |
|---|---|
| BLOCKER | `clippings.py` overwrites user notes on each compile — fix: route through `_write_with_frontmatter` |
| BLOCKER | F11.4 `OSError` is silent (no log, no alert) — fix: `log.warning` + runtime alert |
| BLOCKER | JSONPath injection via `topic_slug` in news domain — fix: whitelist regex or parameterised query |
| BLOCKER | `core/io.py` cyclically imports the facade via `_wc` — fix: explicit `RunContext` migration |
| BLOCKER | Duplicate `compile_all` (hardcoded + registry-based) — fix: drop the hardcoded path once parity is proven |
| BLOCKER | `_safe_slug(pk) or pk` path traversal fallback in `frp/__init__.py` — fix: raise `ValueError` instead |
| WARNING | O(N²) `set(rel_sids)` inside list comprehension (`work/__init__.py`) |
| WARNING | 19/21 wiki files fail `ruff format --check` |
