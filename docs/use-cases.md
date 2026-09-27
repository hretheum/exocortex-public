---
title: "Use cases"
---

# Who uses Exocortex, and how

Three problems. One engine.

---

## The Consultant — context that travels with you

**The situation:** Five clients, five contexts. Client A's jargon leaks into Client B's proposals. You forget what you decided six weeks ago. Your Notion "second brain" is full of pages you wrote once and never re-read.

**What changes with Exocortex:**

Every meeting auto-ingests. Every decision lands in the graph as a typed edge — `decided_in`, `mentioned_client`, `addresses_problem`. Client contexts stay separate; queries respect that boundary.

You wake up to a Telegram message: *"2 new contradictions in Client A context. Overdue action item from 3 weeks ago. Pattern shift: 'budget' mentioned 3× more than your baseline."*

You open your vault. The Client A page was rebuilt overnight. The summary is current. You didn't write it.

**Day in the life:**
- **05:00** — Night Shift Telegram ping: contradictions + overdue items + pattern shifts.
- **09:00** — Vault pages are updated. You read, not write.
- **11:00** — In a meeting, Telegram: *"what did we decide about the X redesign?"* → cited answer in 3 seconds.

---

## The Developer — a typed knowledge substrate for agents

**The situation:** You're building an AI product and need a knowledge backend for your agents. Pure vector search misses typed relationships. Pure graph traversal misses semantic similarity. You want both — and you want to own the data.

**What changes with Exocortex:**

16 MCP tools expose GraphRAG: typed path traversal over 35 edge kinds, fused with pgvector HNSW similarity. `expand_node` returns a thought's full typed neighbourhood. `find_contradictions` returns claims that conflict — with the edge path that proves it.

The plugin system lets you add your own source adapters, MCP tools, and wiki domains in ~150 lines. The core doesn't know your domain names. Your domain ships as a plugin.

```python
# Any MCP-compatible client
result = mcp.call("ask", {
    "question": "What's our current position on X?",
    "max_hops": 3
})
# Returns: cited answer, reasoning path, provenance scores
```

→ [MCP tools reference](guides/mcp-tools.md) · [Writing a plugin](guides/writing-a-plugin.md)

---

## The Researcher — synthesis that finds itself

**The situation:** You read constantly. You highlight. You save. Readwise, Instapaper, Obsidian — the queue grows. You have opinions but can't find the notes that support them.

**What changes with Exocortex:**

Gap Radar finds what you've been reading about but never synthesized. *"40 thoughts about AI governance and zero synthesis of them into a position. 8 are older than 60 days."*

`synthesize("tag", "AI governance")` returns a cited draft of your current position — not a hallucination, a compilation from your own notes with edge citations. Edit it. Publish it.

The "Coming back to you" section surfaces relevant past notes when current reading connects to them. Not because of a keyword match — because the graph knows they're related.

**Typical week:**
1. Read → save (Obsidian web clipper, Telegram link, RSS)
2. Exocortex ingests, embeds, extracts typed edges. You're not involved.
3. Friday: read Gap Radar output. What clusters have no synthesis?
4. Run `synthesize`. Edit. Ship.

---

## Not the right fit

Exocortex is **not** for you if:

- You want **managed SaaS** — we don't run your data. You do. (This is a feature, not a bug, if you care about privacy.)
- You want a **mobile-first app** — the primary surfaces are your desktop vault, Claude via MCP, and Telegram for notifications. There is no Exocortex mobile app.
- You need **multi-tenant team deployment today** — v0.1 is single-tenant. Scoped MCP tokens are roadmap. Don't deploy as a shared service yet.
- You don't want to run **Postgres** — it's the only storage backend and the design is not changing.

On the fence? [Open questions →](why-exocortex.md#10-open-questions) is an honest list of what v0.1 does not solve.
