---
title: "Why Exocortex — the long version"
---


# Exocortex

> *A personal knowledge OS that thinks while you sleep, speaks on its
> own, and refuses to let you forget. Notion is just one of its faces.*

Exocortex is not a notes app. It is an **autonomic reasoning engine**
— a typed graph plus an LLM synthesiser plus a hybrid retriever — that
ingests what you read, hear, and decide, and compiles knowledge from
it on its own schedule. Obsidian, Notion, Telegram, and the shell are
interchangeable **surfaces**. The brain lives in Postgres.

This document is the long-form companion to [`README.md`](https://github.com/hretheum/exocortex/blob/main/README.md).
Read it if you want to know *why* the architecture looks the way it
does, what problems it actually solves, and what is explicitly **not**
solved yet.

## 1. Why Exocortex

Every popular "second brain" template — PARA, Notion Ultimate Brain,
Tiago Forte's *Building a Second Brain*, the Roam/Logseq family — is,
underneath, a tidy relational database with backlinks. The user is the
only active processor. The system waits.

That passivity is the root cause of the five PKM pain points that
recur in every honest review of these systems:

1. **Notes never come back.** You wrote it; you forgot you wrote it.
   The graph keeps the link, but nothing surfaces the note when you
   need it. Spaced repetition tools exist, but they operate on
   flashcards, not contextually-relevant atoms.
2. **Collector's fallacy.** Saving an article feels productive; it is
   not. Without something that distils the captured material into a
   position you can act on, the inbox grows and your *thinking* about
   any given topic does not.
3. **System decay.** Templates start tidy and entropy wins. After 12
   months, a typical PKM looks like a yard sale of half-formed pages
   and dead links. The system has no mechanism to repair itself.
4. **Fragmentation across tools.** Notion for tasks, Obsidian for
   prose, Apple Notes for the thought you had on the bus, Telegram for
   the link a friend sent, Gmail for the newsletter. No single place
   *knows* what you know.
5. **Output gap.** You read a lot. You decide a lot. You ship very
   little of it. The knowledge stays in your head and the system has
   no idea you're sitting on a draft.

These five problems share a single shape: **the system is passive and
the user is the only processor.** Templates can dress this up with
better UX, but they cannot fix it. You need a different architecture.

## 1b. What this looks like in practice

Before the architecture: what does a day with Exocortex actually look like?

**05:00 UTC** — Night Shift runs. It queries the last 24 hours of ingested thoughts, checks for new contradictions in the active graph neighbourhood, computes term-frequency spikes vs the 30-day baseline, surfaces overdue action items. Telegram push arrives: 2–5 sentences of plain narrative. Not a metrics dump.

**09:00** — You open your vault (or Notion, or just Telegram). Client pages updated overnight. Meeting summaries synthesised. Contradiction flags listed. Nothing is stale.

**11:00** — Fireflies finishes a transcript from last night's call. The vault watcher picks it up within the minute. Edge extraction runs: 2 new `decided_in` edges, 1 `contradicts` edge noted. Both land in the graph before lunch.

**14:00** — On your phone, Telegram bot: *"What did we decide about the X redesign last quarter?"* GraphRAG 3-hop traversal, cited answer, 3 seconds.

**Friday** — Gap Radar weekly nudge: *"40 thoughts about AI governance, zero synthesis. 8 are 60+ days old. Seed available."* You run `synthesize("tag", "AI governance")`. Edit. Publish.

The system runs on its own schedule. You do other things.

→ [Use cases and personas →](use-cases.md)

## 2. Architecture (L1 / L2 / L3)

Exocortex separates **storage** from **rendering** by a layer most
notes apps collapse:

```
   L1 — sources of truth
   ─────────────────────
   Files you (or systems on your behalf) write:
     · vault/*.md (Obsidian, edited by hand)
     · Gmail "Read Later" label
     · RSS feeds you subscribed to
     · Fireflies meeting transcripts
     · Notion (when integrated as a source surface)
                              │
                              ▼   write-time fork
                                  (Karpathy LLM-Wiki pattern)
   L2 — the graph (canonical)
   ──────────────────────────
   Postgres 16 + pgvector + Apache AGE:
     · thoughts (atomic, embedded, addressable)
     · edges (35 typed kinds: contradicts, supersedes, decided_in, …)
     · syntheses (LLM-generated, perspective-typed, versioned)
                              │
                              ▼   query-time fork
                                  (Open Brain pattern)
   L3 — surfaces
   ─────────────
   Projections of L2 the user actually reads:
     · wiki/*.md (compiled nightly, by domain)
     · MCP tools (search, ask, expand_node, …)
     · Telegram pushes
     · Notion mirror
     · HTTP API
```

The **write-time fork** (Karpathy, *LLM Wiki for Notion*, April 2026)
runs at ingestion: parse a source, embed it, extract typed entities
and relations, store atoms and edges. Then a nightly compiler renders
domain-shaped Markdown into the vault — meetings under
`wiki/work/meetings/`, people under `wiki/work/people/`, newsletters
under `wiki/news/`, and so on. This output is *dereferenceable*: every
synthesised page links back to the thoughts and edges that produced
it.

The **query-time fork** (Nate Jones, *The hybrid I'd actually build
next*, April 2026 — the "Open Brain" pattern) does not pre-compile.
When you ask a question, GraphRAG walks the graph, fuses vector
similarity with typed-edge traversal, and asks an LLM to compose an
answer with citations. Nothing is rendered eagerly; everything is
rendered when asked.

Most systems pick one fork. Notion templates are write-time only (you
render once; the rendering is the truth). Pure RAG stacks are
query-time only (no compiled surface; every interaction re-queries).
Exocortex runs both forks against the **same graph**, because the
forks answer different questions: *"what is the current state of
topic X?"* (write-time → compiled wiki page) versus *"given everything
I know, how should I think about Y?"* (query-time → live synthesis).

### Typed edges, not just links

The 35 edge types in `schema/edges_kind_enum` are the load-bearing
piece. A backlink in Obsidian says *"these two pages mention each
other"*. An Exocortex edge says *one of:*

- `decided_in` — this thought records a decision made at this meeting
- `contradicts` — these two thoughts make incompatible claims
- `supersedes` — this thought replaces an earlier one
- `addresses_problem` — this synthesis answers this open question
- `cites` — this newsletter quotes this source
- `mentions_person` / `mentions_client` / `mentions_project`
- `derived_from` — this synthesis was generated from these thoughts
- … and 27 more

Typed edges let GraphRAG return reasoning paths, not just similar
fragments: *"A contradicts B, which was superseded by C, sourced
from meeting X (human-authored)."* That is the difference between
retrieval and reasoning.

## 3. The plugin system

The core ships zero domain knowledge. Everything specific — what
counts as a meeting, how a newsletter gets parsed, which MCP tools
the server exposes — comes from plugins.

A plugin is a Python package with a `setup(registry)` function that
calls the appropriate registration method for each thing it provides.
There are five extension points:

| Extension point | Base class | What it does | Example |
|---|---|---|---|
| **Source adapters** | `Source` | Pulls items from somewhere into the capture API | Gmail label, RSS feed, Fireflies webhook |
| **Capture processors** | `Processor` | Turns a raw captured item into typed thoughts + edges | `notion-task-sync`, `newsletter`, `youtube` |
| **Perspective types** | `PerspectiveType` | Generates a synthesis for a given key (client, project, topic, …) | `client`, `frp`, `news_cluster` |
| **MCP tools** | `McpTool` | Exposes a callable tool over the MCP protocol | `search_thoughts`, `find_contradictions` |
| **Wiki domains** | `DomainCompiler` | Renders a part of the compiled wiki | `work/`, `news/`, `frp/` |
| **Live sections** | `SectionGenerator` | Contributes a section to the home dashboard | `open_action_items`, `coming_back_to_you` |

A plugin's `setup()` looks like:

```python
from exocortex.core.registry import Registry

def setup(registry: Registry) -> None:
    registry.register_perspective(MyClientPerspective())
    registry.register_mcp_tool(MyTool())
    registry.register_compile_domain(MyDomainCompiler())
```

Plugins are discovered two ways. In development, drop a package
under `plugins/` and it loads via `Registry.discover_dev()`. In
production, declare an entry point in your plugin's `pyproject.toml`:

```toml
[project.entry-points."exocortex.plugins"]
my-plugin = "my_plugin:setup"
```

`pip install` your plugin and the core picks it up via
`importlib.metadata.entry_points`. Plugins do not import each other;
they only talk to the registry and to the core engine. This is what
keeps the engine generic — there is no place in `exocortex/` that
knows the name of any domain.

The reference example is [`examples/acme-corp/`](https://github.com/hretheum/exocortex/tree/main/examples/acme-corp/):
a fictional company plugin in ~150 lines that adds a custom
perspective, an MCP tool, and a domain compiler.

## 4. The source-of-truth rule

There is one architectural law in Exocortex, paraphrasing Nate:

> **The DB stays the source of truth. The wiki is never edited
> directly. Errors are fixed in source, then regenerated. The wiki
> never drifts from reality because it's always rebuilt from
> reality.**

Practically, this means:

- **Every write goes to L1.** Edits to a meeting note happen in the
  vault `.md` (or via the Capture API). The wiki page in
  `wiki/work/meetings/2026-05-24-foo.md` is *compiler output* — it
  will be overwritten on the next run.
- **Edges and syntheses are never hand-edited.** They are derived
  artefacts. To "correct" a synthesis, you correct the underlying
  thought (or mark the synthesis as superseded); the next compile
  picks it up.
- **The Notion surface is read-mostly.** When Two-Way Cockpit
  (Feature 3, v0.2) lands, checking off an action item in Notion will
  fire a `POST /capture` with `source_type=notion-cockpit-action` —
  i.e. it writes to **L1**, not directly to the graph node. Even the
  fanciest surface is a thin shim over the canonical write path.

This rule is what keeps the system from decaying. Notes apps decay
because the user is editing the same artefact over and over and the
edits accumulate cruft. In Exocortex, *the cruft has nowhere to live*
— every compile starts from scratch.

The cost of this rule is that **the compiler must be cheap to run**.
A full vault rebuild takes ~2 minutes on a $24/mo droplet, with LLM
synthesis costs around $0.10–0.20/day at typical volumes. That's the
budget the rule has to fit inside.

## 5. The six features

v0.1 ships the engine: ingestion, the graph, GraphRAG, the compiler,
the MCP server, and a plugin system. The six features below are
implementations layered on top of that engine; all six are running
on the maintainer's reference instance and ship as code in the
public repo. They are not bells and whistles — each one targets a
specific pain point from Section 1.

### Feature 1 — Nightly Shift (briefing while you sleep)

A 05:00 UTC cron runs a perspective called `night_shift_briefing`. It
delta-queries the last 24 hours of thoughts, asks `find_contradictions`
for new conflicts in the graph neighbourhood, runs a pattern detector
(term-frequency spike + embedding drift versus a 30-day baseline) over
the day's atoms, and surfaces overdue action items. The LLM (Qwen,
cheap) writes 2–5 sentences of Polish narrative — *not* a wall of
numbers. Telegram gets a push.

**Guardrail:** contradictions are surfaced as a *list*, never
narrated. *"3 new contradictions: A vs B, C vs D, E vs F — decide"* —
not *"there's some tension between A and B."* The LLM describes
patterns; it does not adjudicate.

Solves pain points 1 (notes don't come back) and 5 (output gap — the
system tells you what you have, ready to ship).

### Feature 2 — Resurfacing Engine (notes return on their own)

A daily worker maintains `resurfacing_state` (SM2 algorithm:
`ease_factor`, `next_due`, `review_count`) for every thought. The
scoring combines:

- the SM2 forgetting curve (when should this come back?)
- graph proximity to *today's* active nodes (is it relevant *now*?)
- provenance weight (human authored > validated AI > unvalidated)
- an orphan boost (a thought with no recent edges gets a small bump)

3–5 notes resurface per day in a "Wraca do ciebie" / "Coming back to
you" home dashboard section. **This is graph-aware spaced repetition
of whole notes, not flashcards.** The novelty is that surfacing is
driven by current relevance, not just temporal decay.

Solves pain point 1 (notes don't come back).

### Feature 3 — Two-Way Notion Cockpit

Today Notion is a read-only mirror of the compiled wiki; the publish
pipeline overwrites it nightly. v0.2 makes a property-whitelisted set
of Notion fields bidirectional:

- Check a task → `POST /capture` with `source_type=notion-cockpit-action` →
  processor updates the action item's edge to `status=done` → next
  compile shows it ticked everywhere
- Type a question into a *"Ask the brain"* field → MCP `ask` runs → the
  answer is written into a reply field within ~5 seconds
- Toggle `human_validated: true` on an `ai_authored` synthesis →
  provenance ranking bumps it from 0.70 to 0.85

The hardest piece is **conflict resolution**: vault `.md` is the
canonical source, Notion is a surface, but humans edit both. The rule
is property-level last-write for booleans, manual merge for free
text, and a Notion-side "this is stale, repull?" banner when the
two diverge by more than a threshold.

Solves pain point 4 (fragmentation) — the same checkbox affects every
surface.

### Feature 4 — Telegram (mobile brain access)

Native Obsidian and Notion apps already solve *reading* on mobile.
The actual gap is **GraphRAG access** (the reasoning layer is
MCP-stdio-only, effectively dead outside a Claude Desktop session)
and **proactive push** (the brain finds something; you have no idea).

A thin Telegram bot on the host, using an allowFrom-style ID
allowlist, polling (no webhook needed behind NAT), and optional LLM
intent routing for ambiguous queries, exposes:

1. `Ask the brain` from your phone — GraphRAG query, cited answer
2. Push notifications — morning briefing, contradiction alerts,
   overdue action items
3. Capture-via-Telegram — anything you send becomes a `POST /capture`
4. (v0.2 stretch) Document drop → graph-backed fact-check: send a
   Markdown file, get back a list of claims with `supports` /
   `contradicts` / `decided_in` edges from your own history

This is qualitatively different from a Perplexity-style fact-check:
an internet-backed bot asks the world; Exocortex asks **you, six
months ago**.

Solves pain point 4 (fragmentation — your phone is now a surface)
and reinforces 1, 2, 5.

### Feature 5 — Gap Radar (what you don't know)

A new MCP tool, `gap_analysis`, and a `gap_radar` synthesis
perspective. Pure graph queries — no new schema:

- Dense clusters of thoughts with **no `synthesis` node** → *"40
  thoughts about X, zero decision-grade synthesis. Want a draft?"*
- Topics with `mentions_*` edges but **no `addresses_problem`** → dead
  knowledge: you keep reading about AI governance but never connected
  it to a project
- `contradicts` edges with **no `supersedes`** resolution → open
  conflicts older than 30 days
- Orphans older than 30 days → thoughts that never grew an edge

The output feeds into the newsletter pipeline as a **nudge sink** —
*"you've been quiet on X and you have material; here's a 200-word
seed."*

Solves pain points 2 (collector's fallacy) and 5 (output gap)
directly.

### Feature 6 — Wiki Compiler Refactor

This one is not user-facing — it's structural. `workers/wiki_compiler.py`
is currently a ~10k-line monolith with 218 top-level definitions and 5
module-level globals. Each new feature above adds a section to a home
dashboard rendered from a 1100-line function. Two LLM agents touching
the file at once produce merge hell.

v0.2 splits it into a `wiki_compiler/` package with ~30 modules
(`core/`, `util/`, `domains/`), a `RunContext` dataclass replacing
the globals, and an explicit public API for the invariants that
matter — most importantly `core/user_state.py`, which preserves the
hand-toggled `[x]` / ✅ markers in meeting notes byte-identically
across compiles.

Without this refactor, Features 1, 2, and 5 each add 200–400 lines to
already-1100-line functions. With it, each feature is one new file
under `domains/home/sections.py`.

Acceptance is byte-identical output versus a pinned baseline (1172
files in the reference vault). The refactor must be *invisible*.

## 6. Compared to the alternatives

### vs. Notion templates (Ultimate Brain, PARA, PPV)

| | Notion templates | Exocortex |
|---|---|---|
| Storage | Relational DB + manual relations | Append-only graph, 35 typed edges, vector embeddings |
| Active processor | The user | The user + LLM synthesisers on schedule |
| Retrieval | Keyword search + Notion AI (RAG against the page text) | GraphRAG (pgvector HNSW + AGE traversal + RRF fusion) |
| Quality signal | None | Provenance-aware ranking (human / validated / unvalidated) |
| Conflict surfacing | None | Active `find_contradictions` over the graph |
| Self-rebuild | Manual | Nightly compile from a canonical graph |

Notion's API fundamentally lacks vector search, graph traversal, and
embeddings. No template can fix that — the limit is the platform.

### vs. RAG frameworks (LangChain, LlamaIndex, Haystack)

RAG frameworks are libraries; Exocortex is a system. The frameworks
give you primitives for *one* fork (query-time). They have no opinion
on:

- the typed edge schema (Exocortex has one — 35 kinds)
- the write-time compile (Exocortex has a nightly wiki compiler)
- the source-of-truth rule (Exocortex enforces L1-only writes)
- the surfaces (Exocortex ships an MCP server, capture API, Telegram
  bot, Notion mirror)
- the operational shape (Exocortex runs on a $24/mo droplet with
  pg_cron, systemd timers, and a known cost envelope)

You could *build* Exocortex on top of LangChain. We didn't, because
the abstractions point the wrong way for a system whose canonical
form is a typed graph in Postgres.

### vs. its private upstream

Exocortex was extracted from a private "second brain" repo in Q2
2026. The upstream contained domain plugins specific to its author
(client engagements, audience-specific publishing pipelines, regional
language configurations) and operational tooling that wasn't
generically useful. Exocortex is the **engine** — the parts that
survive removing one person's notes from the picture.

The extraction kept:
- the graph schema, the synthesizer, the compiler, the GraphRAG layer
- the plugin registries (sources, processors, perspectives, MCP
  tools, wiki domains)
- the configuration loader, the migration CLI, the `init` command,
  the Docker stack
- two example plugins: `hello-world` and `acme-corp` (fictional)

It removed:
- the author's vault content
- author-specific domain plugins (which live in the private repo)
- proprietary audience definitions for downstream Notion publishing
- vault paths, tenant IDs, and other personal configuration

The two repos share `llm-router` (currently bundled inside the
`exocortex-os` wheel; a Stage 1 task splits it into its own
`exocortex-llm-router` PyPI package) and the schema/migration story.
Engine bug fixes flow from public Exocortex into the private
upstream, not the other way around.

## 7. Design principles

Five rules that the engine commits to and that anything you build on
top of it should respect:

1. **Append-only event log.** Thoughts are never updated in place —
   only superseded. The history of *what was once true* is part of
   the data; you can ask the graph what you used to believe and
   when you changed your mind. Compaction happens through edges
   (`supersedes`, `contradicts` + `decided_in`), not deletion.
2. **Source-of-truth rule.** L1 sources beat L2 graph state beat L3
   syntheses beat L3 compiled wiki. Errors are always fixed in the
   highest-priority layer that contains them, then everything below
   is rebuilt. The wiki never drifts from reality because it is
   always rebuilt from reality.
3. **Write-time extraction beats query-time retrieval at scale.**
   Tagging, embedding, edge extraction, and synthesis all happen on
   ingest or on a schedule, not when you ask a question. Query-time
   does graph traversal and LLM composition over already-extracted
   structure. This keeps query latency bounded and lets the cost of
   "understanding" your data amortise over time.
4. **Plugins are the right boundary.** Domain knowledge — what
   counts as a meeting, which fields a client page has, how a
   newsletter category is named — lives in plugins. The core does
   not know your domains by name. New domains are new plugins, not
   patches to the engine.
5. **LLM as compiler, not oracle.** The LLM compiles structured
   inputs (a set of thoughts, a perspective prompt, a graph
   neighbourhood) into structured outputs (a synthesis, a typed
   edge, a wiki page). It does not get to decide what is true. The
   typed schema, the provenance ranking, and the
   `find_contradictions` tool are what keep it honest.

## 8. Roadmap

| Phase | What | Status |
|---|---|---|
| **v0.1.0** | First public release — engine, plugins, examples, docs; Night Shift, Resurfacing, Two-Way Cockpit, Telegram bot, Gap Radar, and Wiki Compiler refactor all running on the reference instance | Shipped 2026-05-24 |
| **Stage 1** | Developer-package polish — `bootstrap_vps.sh`, systemd renames, CLI wheel install, architecture docs migration, `llm_router` on PyPI | In progress (~10 h remaining) |
| **Stage 2** | One-command Docker deploy — every worker as a service, supercronic scheduler, GHCR-built DB image, nginx + TLS overlay, E2E CI smoke | Next (~32 h) |
| **v0.2** | MCP HTTP/SSE transport, Module System extraction (Notion/Gmail/Telegram as installable extras) | Designed, queued after Stage 2 |
| **v0.3+** | Scoped MCP tokens, query memory promotion (Question/Answer nodes), multi-tenant team deployment, calendar as source | Designed; Q4 2026+ |

Each phase ships independent value. The roadmap is the maintainer's
plan; community contributions can re-order it. The
[Roadmap page](roadmap.md) tracks day-to-day status with the current
checklist.

## 9. Agentic framing — what this is really for

Exocortex is a UX for one person now. It is also a **compiled
substrate for future agents**.

The graph (L2) with its typed edges, provenance-aware ranking, and
versioned syntheses is exactly the artefact a planning agent wants
to read. An agent preparing a meeting can query GraphRAG for context,
list open action items, and check for contradictions before
proposing an agenda. An agent drafting a newsletter can seed itself
from Gap Radar output. An agent validating a decision can check
provenance — *"this synthesis is `ai_authored` and `human_validated:
false`; ask the human before citing it"*.

The difference from traditional RAG, again, is that graph traversal
returns **typed paths**, not just similar fragments. An agent can
reason about the *state* of your knowledge — *"this claim is
contested; the most recent decision was X; the contradicting source
was superseded but the contradiction edge wasn't resolved"* — not
just retrieve text that mentions the claim.

The design rule that follows: **every new feature exposes its output
as an MCP tool**, read-only, alongside any UI it ships. The Notion
mirror is for you; the MCP tool is for whatever you (or you-as-an-agent)
build next.

## 10. Open questions

Things v0.1 explicitly does **not** solve, listed honestly:

- **Multi-tenant security.** Today everything in the database is
  one tenant. Scoped MCP tokens (`scope=['client_a']` cannot see
  `client_b` data) are sketched in `schema/24` but not enforced in
  retrievers. Don't deploy Exocortex as a shared service yet.
- **Conflict resolution for Two-Way Cockpit.** Property-level
  last-write is the plan; whether that survives contact with real
  Notion editing patterns is unproven. Feature 3 is the highest-risk
  item on the roadmap.
- **Trust calibration on proactive output.** A system that pushes
  Telegram briefings every morning *must* be terse and have a high
  confidence threshold. The router-monthly-report incident in the
  upstream project taught us that walls-of-numbers-with-no-narrative
  get muted within a week.
- **Calendar as a source.** Meetings exist in your calendar before
  Fireflies records them. Pulling tomorrow's calendar in as
  `pending_meeting` thoughts would let the system pre-brief you.
  Not yet built.
- **Backups.** The reference deployment uses a single DigitalOcean
  droplet. Postgres backups are *off* by default in the docker-compose.
  Turn them on before the system becomes critical to you.
- **The compiler's appetite for new domains.** Feature 6 shipped in
  v0.1.0, so adding a domain is now a new file under
  `exocortex/wiki/domains/` plus an entry-point registration — no
  monolith edit required. Post-refactor audit findings (`clippings`
  overwrite, JSONPath injection, F11.4 silent `OSError`) are tracked
  as follow-up work in the public issue tracker.
- **LLM cost ceiling under heavy load.** The reference workload (one
  user, ~500 thoughts/week) sits well inside the cost envelope. A
  team workload (10 users, 5000 thoughts/week) has not been measured
  end-to-end. The router has cost stops; whether the cost stops *fire
  at the right place* under that load is unknown.

These are the honest gaps, not the marketing pitch. If any of them
matters to your use case, open an issue and we can talk about
whether v0.2 should reprioritise.

---

*Last updated 2026-05-24. Sources: this document is adapted from the
internal vision file at `source/backlog/_second-brain/F31-EXOCORTEX.md`
in the private upstream, with PL → EN translation, scope adjustment
for the public engine, and the conceptual prior art credited per
[`ATTRIBUTION.md`](https://github.com/hretheum/exocortex/blob/main/ATTRIBUTION.md). Karpathy's "LLM Wiki for Notion"
and Nate Jones's "Open Brain" are the two essays the architecture
sits on top of; everything else is implementation.*
