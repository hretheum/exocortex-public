---
title: "Knowledge Layers"
description: "Three-layer architecture: source, graph, query memory"
---

> **Status:** Long-term architectural target.
> **Audience:** Contributors thinking about how source files, graph
> structure, and query history relate to one another.

Exocortex treats source files, graph nodes, and queries as **three
layers of the same knowledge organism**, with explicit interfaces
between them. This document explains the layering, the data flow, and
the boundaries each layer enforces.

## The three layers

```
┌──────────────────────────────────────────────────────────┐
│  L1: SOURCE (human-authored)                             │
│  vault/{domain}/{section}/{subsection}/{file}.md         │
│  • Markdown + frontmatter + wikilinks                    │
│  • User controls layout, naming, taxonomy                │
│  • Stable mental model for the human author              │
└──────────────────────────┬───────────────────────────────┘
                           │ parse: frontmatter + content + links + path
                           │ extract: entities, claims, decisions, metrics
                           ▼
┌──────────────────────────────────────────────────────────┐
│  L2: KNOWLEDGE GRAPH (semantic)                          │
│  AGE graph + pgvector + typed edges                      │
│  • Nodes: SourceFile, Concept, Entity (Person, Project,  │
│    Decision, Metric, Pillar, etc.)                       │
│  • Edges: WIKILINK_TO, MENTIONS, INFORMS, DERIVED_FROM,  │
│    BELONGS_TO_SECTION, CROSS_CUTS                        │
│  • Embeddings on chunks (chunked by section heading)     │
│  • Multi-inheritance via edges (a doc can belong to many │
│    sections at once)                                     │
└──────────────────────────┬───────────────────────────────┘
                           │ enrich:
                           │  • query memory (recursive)
                           │  • LLM extraction (entities, claims)
                           │  • cross-domain matching
                           ▼
┌──────────────────────────────────────────────────────────┐
│  L3: QUERY MEMORY (recursive enrichment)                 │
│  query_log table + Question/Answer nodes                 │
│  • Nodes: Question, Answer, AnsweredBy                   │
│  • Edges: ASKED_BY (user), RETRIEVED (sources used),     │
│    VALIDATED_BY (human review)                           │
│  • Sources: Claude Desktop, GraphRAG MCP, web clients    │
└──────────────────────────────────────────────────────────┘
```

Surfaces (Obsidian wiki, Notion mirror, Telegram digest, CLI output)
are compiled from L2 — never written into directly. Compiled views
are disposable; the graph is canonical.

## L1: Source files

Source files live in a folder hierarchy that makes sense to the human
author. A typical client knowledge base might look like this:

```
vault/work/{client}/{domain}/
  00_HOME/                  ← MOCs, dashboards (cross-cutting)
  01_STRATEGY/              ← strategy documents
  02_OPERATING_MODEL/       ← roles, governance
  03_GOVERNANCE/            ← decision types, log
  04_ROADMAP/               ← phases, gates
  05_<pillar-a>/            ← topic area
  06_<pillar-b>/
  ...
  15_MEETINGS_AND_RITUALS/  ← cadence
  16_TEMPLATES/             ← reusable templates
  99_ARCHIVE/               ← historical
```

**What's strong about this layout:**

- Numbered sections are a stable mental model.
- Thematic grouping is easy to author iteratively.
- Frontmatter already carries taxonomy (`tags`, `type`, `status`).
- Wikilinks express cross-section relationships explicitly.

**What's weak for retrieval:**

- Hierarchy is **single inheritance** — a file lives in one folder —
  but real concepts cross-cut. A single document may logically belong
  to five sections at once.
- Folder names aren't in the graph by default (a chunk from
  `06_DESIGN_SYSTEM/Tokens/` doesn't know it's "DS / Tokens" unless
  the parser captures it from the path).
- Frontmatter `type` drifts (`policy` vs `decision-type` vs
  `playbook`). The boundary between taxonomy and folksonomy needs to
  be explicit.
- Wikilinks are user-curated — high quality but low recall.

## L1 → L2: parsing source into the graph

For each file in `vault/`, the parser emits:

1. **`SourceFile` node** with properties:
   - `path` (relative to the vault root)
   - `section_path` (e.g. `["01_STRATEGY", "02_Pillars"]` — array,
     queryable)
   - `title` (from H1, frontmatter `title`, or filename)
   - `tags` (from frontmatter)
   - `type`, `status` (from frontmatter)
   - `last_modified` (file mtime)
   - `content` (full markdown)
   - `content_embedding` (vector, per chunk)

2. **Wikilink → `WIKILINK_TO` edge** — explicit user-curated
   relations.

3. **Frontmatter taxonomy → typed nodes:**
   - `tags: [pillar/p2-design-system]` → `BELONGS_TO_PILLAR` edge
     to a `Pillar P2 - DS` node
   - `tags: [decision]` → typed as a `Decision` node
   - `tags: [governance]` → typed as a `Governance` node

4. **Path-based edges:**
   - `BELONGS_TO_SECTION` → section node (e.g. `01_STRATEGY`)
   - Section nodes carry `PARENT_OF` edges for hierarchy.

5. **Content-extracted edges (via LLM):**
   - Person mentions → `MENTIONS_PERSON`
   - Project mentions → `CLASSIFIED_AS_PROJECT`
   - Metric mentions → `DEFINES_METRIC` / `REFERENCES_METRIC`
   - Decision references → `INFORMED_BY_DECISION`
   - Roadmap items → `IMPLEMENTS_ROADMAP_ITEM`

6. **Cross-cutting concepts (multi-inheritance):**
   A document in `10_TOPIC_X/` may semantically belong to several
   pillars at once. LLM extraction detects "this doc cross-references
   Pillar X, Stack Y, Metric Z" and emits `CROSS_CUTS` edges.

**What this gives you:**

- "Show all docs about Topic X" — graph query traverses
  `BELONGS_TO_PILLAR` + `CROSS_CUTS` edges, returns canonical files
  plus cross-referencing material.
- "What decisions affect Pillar 2?" — `INFORMED_BY_DECISION` edges
  filtered by pillar.
- "What's Person A's view on Topic Y?" — `MENTIONS_PERSON` edges
  where speaker matches.

## L2 → wiki: compiled views

The wiki is not a copy of the source with UUID filenames. It is a
set of **deliberate compiled views** of the graph.

A reasonable layout for a client knowledge base:

```
wiki/work/{client}/{domain}/
├── _index.md                   ← MOC: section nav + recent activity
├── by-section/                 ← mirrors source structure (links)
│   ├── 00-home.md
│   ├── 01-strategy.md
│   ├── ...
│   └── 99-archive.md
├── by-pillar/                  ← canonical pillar pages
│   ├── p1-quality.md           ← aggregates all docs tagged p1
│   ├── p2-design-system.md
│   ├── ...
├── by-tag/                     ← all frontmatter tags
├── by-type/                    ← decision, playbook, gate, etc.
└── concepts/                   ← extracted entity pages
    ├── decisions.md
    ├── metrics.md
    ├── people.md
    └── roadmap-items.md
```

Each `wiki/` page is a **view of the graph**, not a copy of source.
Links from wiki pages point back to `vault/{actual_path}` with the
original naming and structure preserved.

A user landing on `wiki/work/<client>/<domain>/by-pillar/p4-topic.md`
sees:

- All source files tagged P4 (with real titles, not UUIDs).
- Cross-references to other pillars.
- Related decisions, metrics, people.
- Recent meetings touching P4.

**The wiki becomes a GraphRAG-rendered semantic map, not a file
flatten.**

## Cross-cluster relations

A real client engagement is rarely a single folder. It tends to span
multiple corners of the vault and external systems:

```
vault/work/{client}/{domain}/          ← primary knowledge base
vault/work/{client}/{other-domain}/    ← e.g. pricing, contracts
wiki/work/clients/{client}.md          ← client overview (compiled)
wiki/work/{client}/{domain}/           ← compiled views
backlog/work/{client}/                 ← kanban tasks
wiki/work/meetings/src/                ← meeting notes
wiki/work/people/{names}.md            ← people involved
+ Notion (via sync module)             ← tasks
+ Email threads                        ← already in graph
+ Meeting transcripts                  ← via transcript module
```

**Goal:** all of these layers connect into **one client supercluster**
in the graph:

```
Client: <name>
├── Domain: KnowledgeBase (N source files)
│   ├── Section: 01_STRATEGY (subgraph)
│   ├── Section: 04_ROADMAP (subgraph)
│   ├── ...
│
├── Domain: Roadmap (kanban tasks) ──── IMPLEMENTS_ROADMAP_ITEM
│
├── Domain: People
│   ├── PersonA ── WORKS_ON ── Sections
│   ├── PersonB ── APPROVES ── Phase Gates
│   └── Vendors ── DELIVERS ── Roadmap items
│
├── Domain: Meetings
│   ├── Sync ── DISCUSSES ── Decisions
│   └── Action items ── ASSIGNED_TO ── People
│
└── Domain: External (CMS stack, analytics, etc.)
```

Cross-cluster queries then become natural:

- "What does Client A have in common with Client B?" (similar
  challenges, shared patterns)
- "Vendor performance across clients" (cross-client scorecard)

## Should queries feed the graph?

**Yes, but with explicit boundaries.** Three levels of escalation:

### Level 1: Telemetry (always on)

Every query is logged as:

- Question text + timestamp
- Source (`claude_desktop_mcp`, `graph_rag_api`, etc.)
- Retrieved nodes (which chunks / files were served)
- Latency, tokens, cost

**Value:** you see what you ask about, how often, and where the
knowledge gaps are. A "10 most-asked questions this month" dashboard
is a natural growth opportunity.

**Schema:**

```sql
CREATE TABLE query_log (
  id UUID PRIMARY KEY,
  tenant_id UUID,
  source TEXT,                   -- 'claude_desktop_mcp', etc.
  question TEXT,
  question_embedding VECTOR(1536),
  retrieved_node_ids UUID[],     -- audit trail
  latency_ms INT,
  tokens INT,
  cost_usd NUMERIC,
  asked_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Level 2: Question as searchable entity (opt-in)

Question nodes in the graph, with embeddings:

- A future query similar to a past one returns "you asked something
  like this 3 weeks ago, here was the answer + sources".
- Builds a personal FAQ.
- Detects: same question asked 5× → candidate for a canonical doc.

**Risks:**

- Privacy: queries can be sensitive ("how much did we pay vendor X").
- Pollution: random one-off questions add noise.
- Recursive: question references question → potentially infinite
  loop.

**Mitigation:**

- Off by default, explicit opt-in per source (e.g. Claude Desktop
  yes, ad-hoc MCP no).
- Auto-prune questions with fewer than 2 retrieved nodes (low
  signal).
- TTL: questions older than 90 days without re-use → archived.

### Level 3: Answer as validated knowledge (manual promotion)

Some Q&A turns out useful enough that the user promotes the answer
into a `SourceFile`-like node:

- User clicks "save answer to vault" in the client.
- Becomes a new file in `vault/work/{domain}/answers/{ts}-{slug}.md`.
- Goes through the normal source → graph pipeline.
- **BUT** tagged `provenance: ai_answer` so future retrieval can
  deprioritize it if a better human-authored source emerges.

This is a critical guardrail: **AI answers do not become
automatically authoritative.** They must be human-curated.
Otherwise the feedback loop — AI cites AI answers — drifts away
from ground truth.

### Recommended phasing

| Phase | Scope                            | Risk profile           |
|-------|----------------------------------|------------------------|
| 1     | Telemetry only                   | Zero risk, all reward  |
| 2     | Question nodes for trusted srcs  | Low — opt-in, audited  |
| 3     | Answer promotion w/ human review | Bounded — manual gate  |

## Provenance: the AI-cites-AI guardrail

Every file Exocortex writes into the vault carries a `provenance`
frontmatter field. Retrieval ranking respects it:

```
human  >  ai_assisted  >  ai_extracted  >  ai_authored (validated)  >  ai_authored (unvalidated)
```

This prevents the failure mode where AI-generated synthesis is
re-ingested, re-cited, and gradually crowds out the human source of
truth.

See the [Module System](module-system.md) for how plugins should
declare provenance on the artifacts they emit.

## Related

- [Architecture overview](overview.md)
- [Source Pipeline Pattern](source-pipeline-pattern.md)
- [Module System](module-system.md)
- [Wiki Compiler](wiki-compiler.md)
