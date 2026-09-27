---
title: "Lessons Learned"
description: "Cross-cutting lessons from building and operating Exocortex"
---

## Wiki Compiler Refactor (F31.6)

### What we gained

- `wiki_compiler.py`: 8 066 → 429 lines (−95%). Each domain lives in its own module.
- Layering rule: `util/*` → `core/*` → `domains/*` — zero circular imports.
- The F11.4 checkbox invariant (`[x]` / ✅) extracted to `wiki/core/user_state.py` as a public API — any domain can call it without re-implementing the merge logic.
- Easier onboarding: adding a new domain means creating one file in `wiki/domains/` with a `setup(registry)` entry point.

### What it cost

- ~16 h across 5 extraction batches (iterative, one commit per domain).
- Globals (`DRY_RUN`, `current_run_id`, `_pages_written`) could not be eliminated — they remain in `wiki_compiler.py` accessible via lazy import (`_wc.*`). Proper `RunContext` migration is a follow-up.
- Top-level import of `exocortex.wiki.core.edges` in the news module pulls in DB/settings at import time — pre-existing pattern, not introduced by the refactor.

### Reusable patterns

1. **Byte-invariant baseline before refactoring** — snapshot MD5 of all wiki output files + an idempotency test gates every commit. If the new code produces different bytes, the test catches it before merge.
2. **Thin wrapper → full implementation** — every domain starts as a `_LegacyDomainCompiler` stub that delegates to the old code. Swap in the real implementation while keeping tests green at both steps.
3. **Lazy import for shared globals** — `import exocortex.wiki_compiler as _wc` inside a function body, never at module top-level. Prevents circular import chains and defers the DB/settings load to first call.

---

## Postgres / psycopg3

- `autocommit=True` means every `c.execute()` commits immediately — `with conn() as c:` does **not** roll back on exception. Ensure all required columns are set on every INSERT; do not rely on a wrapping transaction.
- psycopg3's strict `%`-placeholder lexer rejects any stray `%` in SQL literals, even escaped LIKE patterns like `'frp\_%'`. Pass the LIKE pattern as a `%s` parameter instead.
- Multi-statement SQL sent via separate `c.execute()` calls uses different connections from the pool. Send the entire SQL file in a single `c.execute(sql)` call — psycopg3 supports multi-statement on `autocommit=True`.

## Apache AGE 1.6.0

- `MERGE` without an index on `properties->id` is an O(n) sequential scan — performance drops below 0.1 writes/s at 1 500+ vertices. Create a BTREE expression index on `agtype_access_operator(properties, '"id"'::agtype)` (not a JSONB `->>'id'` operator). Requires `SET search_path = ag_catalog, public` at `CREATE INDEX` time.
- Typed variable-length paths (`[r:type1|type2*1..N]`) are not supported and raise `SyntaxError at "|"`. Use untyped `[r*1..N]` traversal and post-filter in Python on an allow-list.

## Idempotency

- Layered idempotency: in-memory hash cache → database `UNIQUE` constraint → `ON CONFLICT DO NOTHING` → `pg_notify` only on new `INSERT`. Re-posting the same payload is a no-op with zero side effects.
- `metadata.processors` stamp beats a separate `processed_sources` table. Per-source state is co-located with the source row, requires no JOINs, and is naturally tenant-scoped.
- Idempotency hash format: `SHA256(prompt_version | sorted_input_ids:body_hash)[:12]`. Changing the rendering format changes the hash and triggers a rewrite — potentially losing user edits. Mitigation: stable rendering + diff-merge pattern.

## Schema / data integrity

- Schema enforcement at the ingest boundary is a single fix point. Normalise data *before* saving; all downstream queries then see clean data.
- `CHECK` constraints on `perspective_type` must stay in sync with the Python tuple of valid values. Adding a value in Python without updating the constraint causes `CheckViolation` at insert time.
- The app user is not the owner of all tables (migrations run via `sudo -u postgres psql`). `ALTER TABLE` statements must go through the table owner.

## LLM patterns

- `claude-haiku` occasionally ignores a strict tool schema — returns a raw string instead of the expected `{value, confidence}` dict. Add a defensive normalisation helper that coerces LLM output to the expected shape.
- LLM-emitted UUIDs must be validated — `claude-haiku` sometimes writes a meeting title instead of a UUID. A defensive `_is_uuid()` check prevents `InvalidTextRepresentation` errors in downstream SQL.
- `max_tokens=2048` clips multi-section synthesis. Use 4 096 for synthesis runs; raise the budget ceiling for bulk runs.

## Deployment

- `rsync --delete` on shared system directories (`/etc/…`) will remove OS-managed symlinks (e.g. `do-agent`, `droplet-agent`). Use per-file copy or explicit `--include`/`--exclude` filters.
- Unbuffered stdout (`#!/usr/bin/env -S python3 -u`) is critical under cron/systemd — without it, logs are 0-byte until the process exits.
- The MCP server does **not** auto-reload after a code commit. The Claude Code session must be restarted to pick up changes to `workers/mcp_server.py`.

## GraphRAG

- Latency is dominated by the Anthropic LLM call (~5–7 s); embedding + vector search + graph expansion together take ~500 ms. Aggressive cache and pre-computed popular queries are the primary levers for interactive UX.
- AGE wins for single-hop point queries (~30% of traffic); relational (`pg`) wins for multi-hop joins with indexed columns (~50%). Use AGE for 1–2 hop traversals, relational for aggregation.
- "Honesty over hallucination" as a prompt rule: return "I could not find X" rather than confabulate. Enforced via `edges = BACKGROUND ONLY` system prompt and strict tool schema requiring `source_thought_id`.
