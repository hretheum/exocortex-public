---
title: MCP tools reference
---

# MCP tools reference

Exocortex exposes its capabilities to LLM clients through the Model
Context Protocol (MCP). Run the server with:

```bash
exocortex serve            # stdio transport, default for Claude Desktop
exocortex serve --http     # HTTP/SSE, default for browser clients
```

Once connected, the client sees one tool per registered `McpTool`
subclass. The table below is the **built-in** tool set. Plugins add
their own — call `tools/list` from your client to see the full
inventory of a running server.

## Built-in tools

Source of truth: `exocortex/mcp/tools/*.py`. The "Class" column is
the file/class you'd grep for if you want to read the implementation.

### Knowledge tools

| Tool name | Class | Purpose | LLM call? |
|---|---|---|---|
| `search_thoughts` | `SearchThoughts` | pgvector cosine top-K over `thoughts` | embed only |
| `expand_node` | `ExpandNode` | Apache AGE Cypher traversal, 1–2 hops, filterable by edge type | no |
| `synthesize` | `SynthesizeFetch` | Fetch the latest active row from `syntheses` for a `(perspective_type, perspective_key)` pair | no |
| `find_action_items` | `FindActionItems` | Parser over meeting markdown — open `[ ]` items, filterable by owner / client / due date | no |
| `find_contradictions` | `FindContradictions` | Unresolved `contradicts` edges in the graph | no |
| `ask` | `Ask` | Full GraphRAG: vector retrieval + graph traversal + LLM answer with inline citations | yes |
| `gap_analysis` | `GapAnalysis` | Detects four gap types in the graph: dense clusters with no synthesis, orphan thoughts >30 days old, unresolved `contradicts` edges, and `mentions_*` edges with no `addresses_problem` follow-through | no |

### FRP workflow tools

Drive the Futures Reading Protocol lifecycle from an MCP client. These
read and write `content_queue`, `frp_sessions`, and `thoughts`; none
call the LLM directly (the prompt LLM is the client itself).

| Tool name | Class | Purpose |
|---|---|---|
| `query_content_queue` | `QueryContentQueue` | Score-sorted reading queue, joined with `raw_sources` |
| `create_frp_session` | `CreateFrpSession` | Open a new FRP session anchor — `(frame ∈ A/B/C, level ∈ 1/2/3)` |
| `append_session_thought` | `AppendSessionThought` | Add a step thought + auto `session_contains` edge (+ optional entity edges) |
| `complete_session` | `CompleteSession` | Record 1–5 resonance, schedule `revisit_due = now + 48h`, mark queue item used |
| `enqueue_generated_frp_story` | `EnqueueGeneratedFrpStory` | Persist a generated story as a curated `generated-frp` queue item — UPSERTs `raw_sources` + `content_queue` + scored `thoughts` row + `acquired_from` edge in one call. Idempotent on `SHA256(body)[:16]` URI |
| `add_revisit` | `AddRevisit` | Append a `frp_revisit` thought + emit a `revisits` edge, optional `materializes_as` edge |

### Promotion tools

Wikilink-aware bridges that move structured items between the graph
and Markdown surfaces (vault TODO files).

| Tool name | Class | Purpose |
|---|---|---|
| `promote_action_items` | `PromoteActionItems` | Promote selected action items into `wiki/work/TODO/*.md` |
| `unpromote` | `Unpromote` | Reverse a promotion — remove the wiki block, leave the graph row |
| `list_promoted` | `ListPromoted` | Show which action items are currently surfaced in TODO files |

### Live sections

Inject scheduled or event-driven Markdown blocks into wiki pages.
See the [`F16-live-sections-design.md`](https://github.com/hretheum/exocortex/blob/main/docs/F16-live-sections-design.md)
spec for the event model.

| Tool name | Class | Purpose |
|---|---|---|
| `list_live_sections` | `ListLiveSections` | Inventory of registered `SectionGenerator` instances + their bindings |
| `trigger_live_section` | `TriggerLiveSection` | Force-render a section now, regardless of its schedule or event binding |

## Calling a tool

From an MCP client, the call is whatever your client wraps `tools/call`
as. From the CLI:

```bash
exocortex query "ask" --args '{"question": "what shipped this quarter?"}'
```

`--args` is JSON matching the tool's input schema. The schema is
served alongside the tool via `tools/list`.

## Adding your own

Plugins register new tools through the `McpTool` extension point. See
[Writing a plugin → Register an MCP tool](writing-a-plugin.md#4-register-an-mcp-tool)
for the contract (`.name`, `.schema`, `handler(args) -> result`) and
a worked example.

## Verification

```bash
exocortex query --diag plugins
```

The `mcp_tools` bucket lists every registered tool name. Tools from
plugins appear alongside the built-ins; last-write-wins per `.name`,
so plugin tools can shadow built-ins if you want them to.
