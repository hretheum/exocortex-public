---
title: "Module System"
description: "How Exocortex modules are loaded, discovered, and extended"
---

> **Status:** Design proposal — module extraction track.
> **Audience:** Exocortex maintainers and third-party module authors.

This document defines the architectural contract for **Exocortex modules** —
optional, pluggable units of functionality (source pollers, mirror sinks,
custom MCP tools, integration adapters) that extend the core engine without
being part of the core distribution.

Core engine = Capture API, Scorer, MCP server, Wiki compiler, Postgres
(pgvector + Apache AGE), Synthesizer. Everything else — Notion sync, Cockpit
bidirectional pipeline, Slack listener, Telegram push, Gmail poller — is, or
should become, a module.

---

## 1. Context & Goals

### 1.1 Why modularity now

Exocortex started as a single-tenant personal knowledge OS. The v0.1.0 launch
(public `hretheum/exocortex`, `pip install exocortex-os`, `exocortex.zone`)
brought a second class of stakeholder: external users who want the **engine**
without the author's tenant-specific integrations (private Notion workspaces,
local vault paths, the Cockpit pipeline still on the original droplet, etc.).

The codebase already shows the pressure:

- `capture_api.ALLOWED_SOURCE_TYPES` is a 21-entry hardcoded list; every new
  source type forces a core release.
- `scorer.ROUTING` is a parallel 16-entry hardcoded dispatch table.
- `sources/notion.py` carries a "concurrent-work guard" (HTTP 422 graceful
  no-op) because it could ship before its source type was registered in core.
- `exocortex/sinks/` exists as a directory but is **empty** — sinks live
  inline in workers (`notion_mirror.py`, `journal_publisher.py`), with no
  contract.
- `notify_listener.py:42` imports the Telegram bot at module top level,
  making it impossible to install Exocortex without the Telegram extra.

### 1.2 Goals

1. **A user who does not use Notion never runs Notion code.** No background
   threads, no token validation, no SQL migrations they don't need.
2. **One repeatable pattern** for every future integration (Slack, custom
   RSS, Linear, Obsidian Web Clipper variants, ML enrichers).
3. **No monolith.** A crash in a third-party module must not bring down the
   core capture pipeline.
4. **Zero-config discovery** — installing a module package is enough; the
   engine finds it on next start.
5. **Operator-friendly deployment** — one CLI to enable/disable/migrate
   modules, render systemd units or docker-compose snippets, and check
   health.

### 1.3 Non-goals

- Cross-language plugins. All modules are Python (subprocess sidecars can
  shell out, but the manifest is Python).
- Hot reload. Module changes require a restart.
- A general dependency-injection container — the engine stays explicit.
- Multi-tenant isolation at the module level — tenants are still a core
  concern (see `EXOCORTEX_TENANT_ID`).

---

## 2. Current State

### 2.1 What already exists

`exocortex/core/registry.py` is the central registry singleton. It defines
five extension points:

| Extension point        | Registered objects                  | Consumer                                  |
|------------------------|-------------------------------------|-------------------------------------------|
| `perspectives`         | `synth.perspectives.base.PerspectiveType` | `synthesizer.py`                          |
| `mcp_tools`            | `mcp.tools.base.McpTool`            | `mcp_server.py`                           |
| `compile_domains`      | `wiki.domains.base.DomainCompiler`  | `wiki_compiler.py` (compile pass)         |
| `capture_processors`   | `processors.base.Processor`         | `scorer.py` (intended; not wired yet)     |
| `live_sections`        | `live_sections.base.SectionGenerator` | `live_sections/` runner                   |

Discovery is two-stage:

1. **Python entry points** under group `exocortex.plugins`. Each value is a
   `setup(registry: Registry) -> None` callable, loaded via
   `importlib.metadata`.
2. **Dev-time fallback:** `plugins/*/` directory at repo root, scanned for
   sub-packages exposing `setup(registry)`.

Packaging extras are already in `pyproject.toml`:

```toml
[project.optional-dependencies]
gmail     = ["google-api-python-client>=2.140", ...]
notion    = ["httpx>=0.28"]
fireflies = []
frp       = []
promotion = []
all       = ["exocortex[gmail,notion,fireflies,frp,promotion]"]
```

The `[project.entry-points."exocortex.plugins"]` table exists but has no
entries yet — extracting bundled plugins is part of this work.

### 2.2 What is core vs optional-extractable

| Component                                  | Today          | Target               |
|--------------------------------------------|----------------|----------------------|
| Capture API (`capture_api.py`)             | core           | core                 |
| Scorer / F6.3 router (`scorer.py`)         | core           | core                 |
| Postgres + AGE schema (`schema/00–28`)     | core           | core                 |
| `synthesizer.py`, `wiki_compiler.py`       | core           | core                 |
| MCP server (`mcp_server.py`)               | core           | core                 |
| `processors/article.py`, `arxiv.py`, `youtube.py`, `recipe.py`, `model_3d.py`, `email_thread.py`, `frp_source.py`, `newsletter.py`, `github.py`, `linkedin.py`, `twitter.py` | core (bundled) | core (bundled — generic) |
| `processors/notion_task.py`, `cockpit_action.py` | core         | **module `notion`** |
| `sources/notion.py`                        | core           | **module `notion`** |
| `sinks/notion_mirror.py` (inlined)         | worker         | **module `notion`** |
| `sources/gmail.py`                         | core           | **module `gmail`**   |
| `sources/rss.py`                           | core           | core (generic)       |
| `telegram_bot.py`, `telegram_intent.py`    | core           | **module `telegram`** |
| `night_shift_briefing.py` (workers)        | core           | core                 |
| Cockpit pipeline (TS, original-host only)  | external repo  | **module `notion-cockpit`** (Python port) |
| Tenant-specific configs (e.g. `projects.yaml::<client>`) | core | private plugin (out of public repo) |

### 2.3 Known import-chain risks

- `notify_listener.py:42` imports `telegram_bot` at module top level. Must
  become a lazy import or move behind the `telegram` module's `start()`.
- `promotion_lib.py:33` imports a private function from `wiki_compiler`.
  The compiler should expose this through a public helper before the
  promotion logic is split.
- `processors/__init__.py` carries a `_BUNDLED_PROCESSORS` registration that
  is currently driven by hand. Once the registry is the source of truth,
  this list disappears.

---

## 3. Module Architecture

### 3.1 Approaches considered

| Approach                                                  | Pros                                                      | Cons                                                                                       | Verdict          |
|-----------------------------------------------------------|-----------------------------------------------------------|--------------------------------------------------------------------------------------------|------------------|
| **A.** `pip install exocortex[notion]` + conditional import | Simplest. No new infrastructure.                          | No discovery — operators must edit a hardcoded list. No crash isolation. No per-module versioning. | Too shallow.     |
| **B.** Entry points (pytest / mkdocs / airflow providers) | Zero-config discovery. Per-package versioning. Standard Python — works with `pip`, `uv`, `pipx`, Docker. Already scaffolded. | All in-process — a third-party module can crash core. No language-agnostic interop.        | **Baseline.**    |
| **C.** Subprocess / sidecar (HTTP / Unix socket)          | Crash isolation. Independent restarts. Natural fit for docker-compose / k8s. | IPC complexity, schema versioning per process, observability per process. Overkill for small pollers. | Selective only.  |
| **D.** Hybrid (entry points + opt-in subprocess)          | Keeps B simple for small modules. Allows C where it matters (long-running listeners, heavy ML workers). One mental model: `EXOCORTEX_MODULES=notion,slack`. | Two runtime modes to support in CLI and supervisor logic.                                  | **Selected.**    |

### 3.2 Chosen approach: **Hybrid (D)**

- **Discovery:** Python entry points under group `exocortex.plugins`. Already
  wired via `exocortex/core/registry.py::Registry.discover()`.
- **Runtime mode per module:** declared in the module's `ModuleManifest`,
  overridable by the operator via `config/modules/{name}.yaml::runtime`:
  - `in_process` — imported into the core process at bootstrap.
  - `subprocess` — spawned as a sidecar; core still registers the module's
    declared `source_types` so Capture API accepts traffic immediately.
- **Operator toggle:** `EXOCORTEX_MODULES=notion-cockpit,slack` selects which
  discovered modules to enable. Unset / empty = all discovered modules are
  enabled (developer-friendly default for local installs).
- **Why hybrid for Notion specifically:** the Notion **source poller** is a
  ~15-minute idempotent cron-style job — `in_process` driven by a systemd
  timer is enough. The **Cockpit mirror sink** (bidirectional diff,
  conflict resolver, dedup hash, throttle) is a long-running consumer with
  more failure modes — `subprocess` gives it its own restart policy without
  affecting Capture API uptime.

### 3.3 Deployment story (end user)

```bash
# 1. Install (extras pull module's optional deps — httpx for Notion, etc.)
pip install "exocortex-os[notion]"

# 2. Enable the module
echo 'EXOCORTEX_MODULES=notion' >> ~/.config/exocortex/.env

# 3. Initialise module config (CLI scaffolds the YAML with TODO placeholders)
exocortex modules init notion
# → writes config/modules/notion.yaml with comments and required env hints

# 4. Fill in secrets / IDs
$EDITOR config/modules/notion.yaml

# 5. Apply module migrations (idempotent — safe to re-run)
exocortex modules migrate notion
# → executes SQL files from the module's migration_dir, recorded per-module
#   in the module_migrations table

# 6. Render deployment descriptors
exocortex modules render-systemd notion | sudo tee /etc/systemd/system/exocortex-notion-*.{service,timer}
# or:
exocortex modules render-compose notion >> docker-compose.override.yml

# 7. Start
systemctl --user enable --now exocortex-notion-poller.timer
exocortex modules status   # name | enabled | runtime | health | last_run
```

Disabling a module is a config change, never a code change:

```bash
exocortex modules disable notion        # removes from EXOCORTEX_MODULES
systemctl --user disable --now exocortex-notion-poller.timer
```

---

## 4. Module Interface Contract

### 4.1 Core types

```python
# exocortex/core/module.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from pydantic import BaseModel


class ModuleRuntime(str, Enum):
    IN_PROCESS = "in_process"   # imported into capture_api / scorer / mcp_server
    SUBPROCESS = "subprocess"   # spawned as a separate OS process (sidecar)


class ModuleHealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class ModuleHealth(BaseModel):
    status: ModuleHealthStatus
    detail: str = ""
    last_success_at: str | None = None     # ISO-8601 UTC
    last_error_at: str | None = None
    metrics: dict[str, float] = {}         # e.g. {"queue_depth": 12.0, "lag_seconds": 3.4}


@dataclass(frozen=True)
class SystemdUnit:
    """One systemd unit emitted by the module's deployment descriptor."""
    name: str                              # 'exocortex-notion-poller'
    kind: str                              # 'service' | 'timer' | 'oneshot'
    exec_start: str                        # full command (module's CLI entry)
    on_calendar: str | None = None         # for timers, e.g. '*:0/15'
    environment_file: str | None = None    # '/etc/exocortex.env'
    after: Sequence[str] = ()
    description: str = ""


@dataclass(frozen=True)
class ComposeService:
    """One docker-compose service emitted by the module."""
    name: str
    image: str | None = None               # None → reuse the exocortex base image
    command: str = ""
    depends_on: Sequence[str] = ()
    healthcheck: dict[str, object] | None = None
    environment: Sequence[str] = ()        # env-var names (not values)
    volumes: Sequence[str] = ()


@dataclass(frozen=True)
class DeploymentDescriptor:
    runtime: ModuleRuntime = ModuleRuntime.IN_PROCESS
    systemd_units: Sequence[SystemdUnit] = ()
    compose_services: Sequence[ComposeService] = ()
    required_env: Sequence[str] = ()       # env-var names validated at startup


@dataclass(frozen=True)
class ModuleManifest:
    name: str                              # 'notion'
    version: str                           # '0.1.0' (semver; recorded in audit log)
    description: str
    source_types: Sequence[str] = ()       # ['notion-task-sync', 'notion-cockpit-action']
    mcp_tools: Sequence[str] = ()          # tool names registered by start()
    migration_dir: Path | None = None      # SQL files applied by `exocortex modules migrate`
    config_schema_class: type[BaseModel] | None = None
    deployment: DeploymentDescriptor = field(default_factory=DeploymentDescriptor)


@runtime_checkable
class ExocortexModule(Protocol):
    """Contract every Exocortex module implements.

    Lifecycle (in_process):
        load_config(path) → start(registry) → [running] → health_check() → stop()

    Lifecycle (subprocess):
        Same, but start() runs inside the spawned child. The parent process
        registers the module's declared source_types and mcp_tools from the
        manifest so that Capture API accepts traffic before the child has
        fully booted.
    """

    manifest: ModuleManifest

    def load_config(self, config_path: Path) -> None:
        """Validate + cache module config (config/modules/{name}.yaml).

        Raises on invalid config so failures surface at startup, not at the
        third poll cycle.
        """

    def start(self, registry: "Registry") -> None:
        """Register processors, MCP tools, sinks, live sections, perspectives."""

    def stop(self) -> None:
        """Idempotent shutdown — close DB pools, cancel tasks, flush state."""

    def health_check(self) -> ModuleHealth:
        """Cheap (<200 ms) status probe used by `exocortex modules status`
        and the `/health/modules` endpoint."""
```

### 4.2 Registry extensions

`exocortex/core/registry.py::Registry` gains:

```python
class Registry:
    # existing fields ...
    sinks: dict[str, "Sink"] = {}                          # NEW: 6th extension point
    module_instances: dict[str, ExocortexModule] = {}      # NEW: enables health probing

    def register_sink(self, sink: "Sink") -> None: ...
    def register_module(self, module: ExocortexModule) -> None: ...
```

`Sink` is a thin ABC mirroring `Processor`:

```python
# exocortex/sinks/base.py
class Sink(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def emit(self, payload: dict) -> None: ...        # idempotent
```

### 4.3 Module YAML config

`config/modules/{name}.yaml` is the **only** file an operator edits per
module. Pydantic validates it through `manifest.config_schema_class`.

Conventions:

- `module: <name>` field for cross-check against `manifest.name`.
- `enabled: true|false` — operator-level on/off (defence in depth on top of
  `EXOCORTEX_MODULES`).
- `runtime: in_process|subprocess` — overrides manifest default.
- Secrets are referenced by env-var name (`${NOTION_TOKEN_SOURCE}`), never
  inlined.
- **Env var prefix convention:** module-specific env vars use
  `EXOCORTEX_<MODULE>_<NAME>` (e.g. `EXOCORTEX_NOTION_SOURCE_DB_ID`,
  `EXOCORTEX_NOTION_TOKEN_SOURCE`). Legacy unprefixed names
  (`NOTION_TOKEN_SOURCE`, `NOTION_SOURCE_DB_ID`) remain accepted as
  `AliasChoices` for backwards compatibility with droplet-era deployments.
  Pydantic Settings handles both via `validation_alias`.

Example (Notion module, abridged):

```yaml
module: notion
enabled: true
runtime: in_process

source:
  database_id: "${NOTION_SOURCE_DB_ID}"
  token_env: NOTION_TOKEN_SOURCE
  poll_interval_seconds: 900
  state_file: ~/.config/exocortex/notion-state.json

mirror:
  enabled: true
  workspace_id: "${NOTION_MIRROR_WORKSPACE_ID}"
  token_env: NOTION_TOKEN_MIRROR
  database_id: "${NOTION_MIRROR_DB_ID}"
  writeback:
    throttle_per_cycle: 50
    dedup: hash
    conflict_resolver: last-write-wins-with-audit

cockpit:
  enabled: true                  # F31.3 two-way cockpit
  whitelist: ["human_validated", "Zapytaj mózg"]
  ask_field:
    enabled: true
    target_field: "Odpowiedź mózgu"
    latency_budget_ms: 30000

observability:
  emit_query_log: true
  source_label: "notion"
```

### 4.4 Health & observability

- `Registry.module_instances[name].health_check()` is called by the engine
  on demand.
- Core exposes `GET /health/modules` (Capture API) returning
  `{module_name: ModuleHealth}` — Prometheus-friendly.
- CLI `exocortex modules status` renders the same data as a table:
  `name | enabled | runtime | status | last_success | metrics`.
- Subprocess modules expose a JSON-RPC `{"method": "health"}` endpoint on
  `/run/exocortex/{name}.sock`; the parent process aggregates results.

---

## 5. Critical Refactors Required (before any module ships)

These three refactors are blocking. Until they land, any new module fights
the same boilerplate the existing Notion source already fights.

### 5.1 `capture_api.ALLOWED_SOURCE_TYPES` → registry-derived

Today: 21-entry hardcoded set. New source types ship in two PRs — once to
add to the set, again to deploy the processor.

Target:

```python
# capture_api.py
def _allowed_source_types() -> set[str]:
    return _CORE_SOURCE_TYPES | set(registry.capture_processors.keys())
```

Effect: a module that registers `notion-task-sync` in its `start()` makes
the source type accepted by `/capture` automatically, no core PR.

Side effect: removes the "graceful HTTP 422 no-op" guard from
`sources/notion.py`.

### 5.2 `scorer.ROUTING` → registry-derived

Today: 16-entry hardcoded `dict[source_type, processor_callable]`.

Target: dispatch via `registry.capture_processors[source_type].process(...)`.
The `_BUNDLED_PROCESSORS` registration in `processors/__init__.py` becomes
an `entry_points` declaration in `pyproject.toml` pointing at a built-in
`setup(registry)` for each bundled processor (article, arxiv, youtube, …).

### 5.3 Sinks become the 6th extension point

`exocortex/sinks/` is currently an empty directory. Promote it to a
first-class extension point:

- Add `Sink` ABC at `exocortex/sinks/base.py`.
- Add `Registry.sinks` + `register_sink`.
- Move the inlined `notion_mirror` write-back logic into the Notion
  module's `Sink` implementation.
- `journal_publisher.py` migrates next.

### 5.4 Lazy imports for optional integrations

- `notify_listener.py:42` — Telegram import moves behind a `_get_bot()`
  factory called only when a notify rule targets Telegram.
- `promotion_lib.py:33` — `wiki_compiler` exposes a public
  `render_action_items_section()` helper; `promotion_lib` imports the
  public name only.

### 5.5 Module-aware migrations table

```sql
CREATE TABLE module_migrations (
    module     text NOT NULL,
    version    text NOT NULL,
    filename   text NOT NULL,
    applied_at timestamptz DEFAULT now(),
    PRIMARY KEY (module, filename)
);
```

`exocortex modules migrate <name>` reads files from `manifest.migration_dir`
in lexicographic order and records each filename. Idempotent: already-applied
files are skipped.

---

## 6. Reference Implementation: Notion Module

The Notion module is the first non-trivial extraction and the template for
all future modules. It bundles four concerns that ship together because
they share configuration, secrets, and a Notion HTTP client: source
polling, mirror write-back, Cockpit bidirectional pipeline, and the
matching MCP tools.

### 6.1 Location

`exocortex/modules/notion/` **in-tree** in the public `hretheum/exocortex`
repository.

Rationale: YAGNI on a separate repo until there is a second maintainer or
the module needs its own release cadence. The packaging extras
(`exocortex-os[notion]`) already give end users the "don't install what you
don't use" experience. Extracting to `hretheum/exocortex-notion` later is
mechanical (entry point + version pin) once the trigger fires.

### 6.2 File tree

```
exocortex/modules/notion/
├── __init__.py              # exports `setup(registry)` for entry point
├── manifest.py              # ModuleManifest definition
├── module.py                # NotionModule class (implements ExocortexModule)
├── settings.py              # NotionSettings (Pydantic, EXOCORTEX_NOTION_* env)
├── config.py                # NotionModuleConfig (loaded from YAML)
├── audience_loader.py       # resolves audience yaml + tenant-specific overrides
├── client.py                # NotionHTTPClient — shared httpx wrapper (auth, retry, rate limit)
├── cli.py                   # `exocortex modules notion <verb>` sub-commands
├── cockpit/
│   ├── __init__.py
│   ├── poller.py            # NotionCockpitPoller (asyncio + httpx)
│   ├── resolver.py          # CockpitResolver — pure functions, zero I/O
│   ├── diff.py              # source ↔ mirror diff computation (pure)
│   ├── state.py             # CockpitStateStore — PG-backed cursor + dedup hashes
│   └── rate_limit.py        # token-bucket aligned with Notion's 3 req/s
├── sink.py                  # NotionMirrorSink (writes back to mirror workspace)
├── processors/
│   ├── __init__.py
│   ├── notion_task.py       # source_type='notion-task-sync'
│   └── cockpit_action.py    # source_type='notion-cockpit-action'
├── mcp_tools/
│   ├── __init__.py
│   └── validate_coe_page.py # human_validated flip (F31.3.5)
├── migrations/
│   ├── 0001_cockpit_actions_pending.sql       # schema/29 — module-owned
│   ├── 0002_notion_mirror_mapping.sql
│   └── 0003_cockpit_state_store.sql           # PG state (replaces JSON file)
├── deploy/
│   ├── systemd/             # rendered templates (Jinja2)
│   │   ├── exocortex-notion-poller.service.j2
│   │   ├── exocortex-notion-poller.timer.j2
│   │   └── exocortex-notion-mirror.service.j2
│   └── compose/
│       └── notion.yml.j2
├── config.example.yaml      # shipped via package-data; copied by `modules init`
└── tests/
    ├── conftest.py          # fixtures: respx Notion mock, respx Capture API mock, fake registry, PG fixture
    ├── test_resolver.py     # ≥95% line coverage target — pure function tests
    ├── test_diff.py         # ≥95% — pure function tests
    ├── test_state.py        # ≥95% — PG state store
    ├── test_poller.py       # ≥85% (asyncio happy path + cursor advance + 422 guard)
    ├── test_processors.py
    └── fixtures/
        ├── notion_page_minimal.json
        ├── cockpit_pending_3items.json
        └── conflict_scenarios.json    # ≥10 scenarios pairwise asserted
```

**Why `cockpit/` is a sub-package**: the Cockpit pipeline (F31.3 — poller +
resolver + diff + state + rate-limit) is internally cohesive and tested
together. Source-only modules (the F21 Notion sync path) need none of it;
keeping it isolated makes future "lite" installs trivial (omit the
sub-package, no Cockpit code loaded).

**Why state moves to Postgres (`0003_cockpit_state_store.sql`)**: the
original implementation used a JSON state file under
`~/.config/exocortex/`. PG-backed state survives container restarts cleanly,
supports multi-instance coordination (when the poller eventually runs in
Kubernetes), and lets us join state metrics into the existing `query_log` /
`pipeline_runs` observability surface. The example YAML in §4.3 still shows
`state_file` for backwards compatibility — modules read the legacy file once
on first run and migrate the cursor into PG.

### 6.3 Class sketches

```python
# exocortex/modules/notion/module.py
class NotionModule:
    manifest = MANIFEST   # imported from .manifest

    def __init__(self) -> None:
        self._cfg: NotionSettings | None = None
        self._poller: NotionCockpitPoller | None = None
        self._last_health: ModuleHealth | None = None

    def load_config(self, path: Path) -> None:
        data = yaml.safe_load(path.read_text())
        self._cfg = NotionSettings.model_validate(data)

    def start(self, registry: Registry) -> None:
        assert self._cfg is not None, "load_config() must run first"
        registry.register_capture_processor(NotionTaskProcessor())
        registry.register_capture_processor(CockpitActionProcessor())
        registry.register_sink(NotionMirrorSink(self._cfg.mirror))
        registry.register_mcp_tool(ValidateCoePageTool())
        self._poller = NotionCockpitPoller(self._cfg, sink=registry.sinks["notion-mirror"])
        # Poller is invoked by systemd timer in production; here we only wire it.

    def stop(self) -> None:
        if self._poller is not None:
            self._poller.close()

    def health_check(self) -> ModuleHealth:
        return self._poller.health() if self._poller else ModuleHealth(
            status=ModuleHealthStatus.UNKNOWN, detail="poller not started"
        )
```

```python
# exocortex/modules/notion/poller.py — I/O-bound, asyncio + httpx
class NotionCockpitPoller:
    """Read Notion source DB → diff vs state → POST /capture for each change.

    Pattern A canonical: this poller NEVER writes to Postgres directly. Every
    new or changed Notion page is emitted as a `notion-task-sync` payload to
    `POST /capture`; the registered processor handles persistence.
    """

    def __init__(self, cfg: NotionSettings, sink: Sink) -> None: ...

    async def run_once(self) -> PollResult: ...
    async def run_forever(self) -> None: ...
    def health(self) -> ModuleHealth: ...
    def close(self) -> None: ...
```

```python
# exocortex/modules/notion/resolver.py — pure function (no I/O imports)
@dataclass(frozen=True)
class ConflictDecision:
    action: Literal["accept_source", "accept_mirror", "merge", "noop"]
    reason: str
    audit_payload: dict


def resolve(source: NotionPage, mirror: NotionPage, prev_hash: str) -> ConflictDecision:
    """Resolve a single source ↔ mirror conflict. No DB, no HTTP, no logging
    side effects — call sites pass everything in.

    Guarantees enforced by tests:
      - last-write-wins by Notion `last_edited_time` unless `human_validated`
        flips, which always win.
      - Identical hashes (dedup) short-circuit to `noop`.
      - At least 10 conflict scenarios in `tests/fixtures/conflict_scenarios.json`.
    """
```

### 6.4 Setup hook

`pyproject.toml` declares the entry point:

```toml
[project.entry-points."exocortex.plugins"]
notion = "exocortex.modules.notion:setup"
```

`exocortex/modules/notion/__init__.py`:

```python
from exocortex.core.registry import Registry
from .module import NotionModule

def setup(registry: Registry) -> None:
    module = NotionModule()
    registry.register_module(module)
```

`load_config()` and `start()` are driven by the engine bootstrapper after
all `setup()` calls have run, so module ordering is not a concern.

### 6.5 Migrations shipped by the module

- `0001_cockpit_actions_pending.sql` — the `cockpit_actions_pending` queue
  (replaces ad-hoc droplet schema, gated by F31.3 G1/G7).
- `0002_notion_mirror_mapping.sql` — source-page ↔ mirror-page dedup table.

Applied via `exocortex modules migrate notion` (idempotent, tracked in
`module_migrations`).

### 6.6 Deployment artifacts

**docker-compose (primary path):**

```yaml
# Rendered by `exocortex modules render-compose notion`
services:
  exocortex-notion:
    image: ghcr.io/hretheum/exocortex:0.1.0
    command: ["exocortex", "modules", "run", "notion"]
    environment:
      - EXOCORTEX_MODULES=notion
      - NOTION_TOKEN_SOURCE
      - NOTION_TOKEN_MIRROR
      - NOTION_SOURCE_DB_ID
      - NOTION_MIRROR_DB_ID
      - NOTION_MIRROR_WORKSPACE_ID
    depends_on: [postgres]
    healthcheck:
      test: ["CMD", "exocortex", "modules", "health", "notion"]
      interval: 30s
    restart: unless-stopped
```

**systemd (VPS fallback):**

```ini
# /etc/systemd/system/exocortex-notion-poller.service
[Service]
User=exocortex
EnvironmentFile=/etc/exocortex.env
ExecStart=/usr/bin/exocortex modules run notion --once
ProtectHome=read-only
PrivateTmp=true
NoNewPrivileges=true
```

```ini
# /etc/systemd/system/exocortex-notion-poller.timer
[Timer]
OnCalendar=*:0/15
Persistent=true
[Install]
WantedBy=timers.target
```

`ProtectHome=read-only` is a **hard default** (lesson from F31.3.3 G15 — the
scorer service originally shipped with `ProtectHome=true` and silently
broke OAuth token reads). The renderer refuses to emit a unit without it.

### 6.7 Test plan

Coverage targets (gated in CI):

- `cockpit/resolver.py` ≥ 95% line coverage. Pure-function —
  `grep -E "db\.|fetch\(|axios|httpx|psycopg" exocortex/modules/notion/cockpit/resolver.py`
  returns 0.
- `cockpit/diff.py` ≥ 95%. Pure-function — same I/O ban.
- `cockpit/state.py` ≥ 95%. Tests run against a tmp Postgres schema
  (existing `pg_fixture` from core test suite).
- `cockpit/poller.py` ≥ 85%. `respx` mocks both Notion API and the
  Exocortex Capture API. Cases: asyncio happy path + cursor advance +
  Notion 429 retry-after + Capture API 422 graceful no-op (until §5.1
  lands, then removed) + dedup-hash short-circuit.
- `processors/*.py` ≥ 90%. Idempotency test: duplicate `edit_id` →
  `created: false`.
- Conflict matrix: ≥ 10 scenarios in `conflict_scenarios.json`, asserted
  pairwise.

**Test stack convention:** `respx` for HTTP mocking (consistent across all
modules that talk to external APIs — Slack, Linear, Notion will share this).
`pytest-asyncio` for async test functions. No real network calls in CI.

---

## 7. Future Modules

The Notion module template carries over directly to:

| Module     | Source types                              | Sinks         | MCP tools                 | Subprocess?           |
|------------|-------------------------------------------|---------------|---------------------------|------------------------|
| `gmail`    | `gmail-newsletter`, `gmail-thread`        | —             | —                         | No (timer-driven poll) |
| `slack`    | `slack-message`, `slack-thread`           | `slack-reply` | `summarize_channel`       | Yes (long-lived RTM)   |
| `rss`      | `rss-feed`                                | —             | —                         | No                     |
| `telegram` | `telegram-message`, `telegram-voice`      | `telegram-push` | `send_digest`           | Yes (long-lived polling) |
| `linear`   | `linear-issue`                            | `linear-comment` | `link_thought_to_issue` | No                     |
| `obsidian-clipper` | `web-clip`                        | —             | —                         | No                     |

Each gets the same three artifacts:

1. `exocortex/modules/<name>/` directory with the same shape.
2. `pyproject.toml`: optional-dependency extra + entry point.
3. `config.example.yaml` shipped via package-data.

The Telegram extraction additionally unblocks the lazy-import refactor in
§5.4: once `telegram_bot.py` moves into `exocortex/modules/telegram/`, the
top-level import in `notify_listener.py` becomes a registry lookup
(`registry.sinks.get("telegram-push")`) that is `None` for installs without
the extra.

---

## 8. Guardrails

Modules **must not**:

1. **Write to Postgres directly.** All persistence flows through `POST
   /capture` (Pattern A canonical). The only exception is migrations
   shipped under `manifest.migration_dir`, applied by the engine, not the
   module itself.
2. **Write to the vault.** Vault writes are a core concern (atomic markdown
   render, `[x]` preservation, F11.4 invariants). Modules emit data; the
   wiki compiler decides whether and where it lands in the vault.
3. **Import another module's internals.** Inter-module dependencies go
   through the registry (e.g. a module looks up `registry.sinks["telegram-push"]`).
4. **Bypass the LLM router.** Modules that need LLM calls use
   `exocortex.llm_routing.route(...)`. Direct SDK calls are forbidden so
   monthly cost reports stay accurate.
5. **Hardcode tenant IDs.** Use `get_tenant_id()` from `exocortex.settings`.
6. **Skip config validation.** `load_config()` must raise on bad YAML;
   silent fallbacks mask production misconfigurations.
7. **Spawn unmanaged threads / asyncio tasks.** Long-running work goes
   through the deployment descriptor (systemd timer or compose service).
   In-process modules expose `stop()` that joins/cancels everything.
8. **Ship systemd units without `ProtectHome=read-only`, `User=exocortex`,
   and `NoNewPrivileges=true`.** The CLI renderer refuses non-compliant
   templates.

Modules **may**:

- Register additional MCP tools.
- Register additional sinks, processors, perspectives, live sections, and
  compile domains.
- Ship their own migrations under `manifest.migration_dir`.
- Expose CLI sub-commands via `exocortex modules <name> <verb>`.
- Declare optional Python dependencies via their own pyproject.toml extras.

---

## 9. Refactoring Plan

Estimates are rough engineering hours assuming one person familiar with the
codebase. They cover code + tests + smoke + docs but **not** the
operational deploy (systemd unit installation, droplet config).

### 9.1 P0 — unblock all module work (~14 h)

| # | Item                                                                     | Est. |
|---|--------------------------------------------------------------------------|------|
| 1 | `Registry.sinks` + `Sink` ABC + `register_sink()`                        | 2 h  |
| 2 | `Registry.register_module()` + `module_instances` map + health probing   | 2 h  |
| 3 | `capture_api.ALLOWED_SOURCE_TYPES` → derived from `registry.capture_processors` | 2 h  |
| 4 | `scorer.ROUTING` → registry-driven dispatch                              | 3 h  |
| 5 | Bundled processors moved to entry-point `setup()` callables              | 3 h  |
| 6 | `module_migrations` table + `exocortex modules migrate` CLI              | 2 h  |

### 9.2 P1 — module tooling (~10 h)

| # | Item                                                       | Est. |
|---|------------------------------------------------------------|------|
| 1 | `exocortex modules {init, render-systemd, render-compose, status, health, run, disable}` CLI | 5 h  |
| 2 | `ModuleManifest`, `DeploymentDescriptor`, `ExocortexModule` Protocol (the types in §4.1) | 2 h  |
| 3 | `/health/modules` endpoint on Capture API                  | 1 h  |
| 4 | Subprocess supervisor + Unix-socket health JSON-RPC        | 2 h  |

### 9.3 P2 — Notion module extraction (~22 h)

| # | Item                                                       | Est. |
|---|------------------------------------------------------------|------|
| 1 | `exocortex/modules/notion/` skeleton + manifest + setup hook | 1 h  |
| 2 | Move `sources/notion.py` → `modules/notion/poller.py`      | 3 h  |
| 3 | Move `processors/notion_task.py` + `cockpit_action.py`     | 2 h  |
| 4 | Port the TypeScript resolver (existing reference impl) → `modules/notion/resolver.py` as pure Python | 5 h  |
| 5 | `state_store.py` + `sink.py` (mirror write-back)           | 3 h  |
| 6 | Migrations `0001_cockpit_actions_pending.sql`, `0002_notion_mirror_mapping.sql` | 2 h  |
| 7 | Test suite (resolver / state / poller / processors)        | 5 h  |
| 8 | `config.example.yaml` + `deploy/` Jinja templates          | 1 h  |

### 9.4 P3 — lazy imports & follow-up extractions (~8 h)

| # | Item                                                       | Est. |
|---|------------------------------------------------------------|------|
| 1 | `notify_listener.py:42` Telegram lazy import / move to module | 2 h  |
| 2 | `promotion_lib.py:33` public helper in `wiki_compiler`     | 1 h  |
| 3 | Telegram module extraction (skeleton + manifest)           | 3 h  |
| 4 | Gmail module extraction (skeleton + manifest)              | 2 h  |

**Total to a shippable F31.3 Notion module: ~46 h** (P0 + P1 + P2). Future
extractions (Slack, Telegram, Gmail) reuse P0/P1 and average ~10 h each.

---

## Appendix A — Glossary

- **Core engine.** Capture API, Scorer, MCP server, Wiki compiler,
  Synthesizer, Postgres schema. Ships with every install.
- **Module.** An entry-point-discovered package that registers extension
  points (processors, sinks, MCP tools, live sections, perspectives,
  domain compilers). Optional; installed via `pip install exocortex-os[<name>]`.
- **Pattern A canonical.** All persistence flows through `POST /capture`.
  Modules emit; core stores.
- **Registry.** `exocortex/core/registry.py::Registry` — central object
  that collects extension-point registrations.
- **Sink.** A module-provided egress writer (Notion mirror, Telegram push,
  Slack reply). 6th extension point added by this proposal.

## Appendix B — Related design docs

- [Source Pipeline Pattern](source-pipeline-pattern.md) — Pattern A details
  (Capture API as the single ingress).
- [Knowledge Layers](knowledge-architecture.md) — L1/L2/L3 layers.
