---
title: Source Pipeline Pattern
---

# Source Pipeline Pattern

> **Status:** Canonical pattern for all ingestion into Exocortex.
> **Audience:** Module authors adding a new source adapter.

Every piece of data that enters the graph — Obsidian notes, emails,
RSS items, meeting transcripts, Notion records, webhook payloads —
flows through the **same entry point**: the Capture API. There is no
back door. Workers that bypass it are an anti-pattern and will be
rejected in review.

## Pattern A — the canonical flow

```
External event / Polling adapter (workers/sources/{name}.py)
  │  POST /capture {source_type, uri, payload}
  ▼
Capture API (port 8000, bearer auth, idempotent ON CONFLICT)
  │  pg_notify('new_source', {source_id, source_type})
  ▼
Router (LISTEN/NOTIFY consumer in scorer)
  │  dispatch by source_type
  ▼
Processor (workers/processors/{source_type}.py)
  │  parse → write PG → emit_live_event()
  ▼
Graph (thoughts + edges + syntheses)
```

Five built-in sources follow this pattern today:

| Adapter             | source_type   | Processor                              | Mode         |
|---------------------|---------------|----------------------------------------|--------------|
| `sources/gmail.py`  | `gmail-*`     | `email_thread.py`, `newsletter.py`     | Polling      |
| `sources/rss.py`    | `rss-frp`     | `frp_source.py`                        | Polling      |
| `vault_watcher.py`  | per-folder    | `article.py`, etc.                     | File events  |
| External webhook    | `manual-url`  | various                                | Push         |
| Bulk ingest         | `article`     | `article.py`                           | One-shot     |

**Five sources, one entry point.**

## Why the bypass is rejected

It is tempting, when adding a new source, to write directly to the
`thoughts` table from a worker. Don't. Here is what you give up:

| Capability          | Pattern A                  | Direct-to-PG bypass        |
|---------------------|----------------------------|----------------------------|
| Idempotency         | `UNIQUE` at the API        | Per-worker DIY             |
| Auth                | Single bearer              | Each worker DIY            |
| Telemetry           | Pipeline-runs hooks        | Per-worker DIY             |
| Replay              | Re-POST the stored payload | No standard path           |
| Schema validation   | Pydantic at the boundary   | Per-processor DIY          |
| Routing             | Auto dispatch by type      | Manual coupling            |
| Debugging           | One tcpdump on port 8000   | N entry points             |

The marginal benefit of bypassing — saving two lines in
`capture_api.py` — never justifies the cost.

## Rules for new sources

### Rule 1: Polling sources go in `workers/sources/{name}.py`

- Read configuration from `config/sources.yaml` or
  `config/{name}_config.yaml`.
- Poll the external API on a systemd timer (or your equivalent
  scheduler — supercronic, cron, Celery beat).
- POST each item to `/capture` with an appropriate `source_type`.
- Keep cursor state in a single state file (e.g.
  `/var/lib/exocortex/{name}.state`).
- **Never write to Postgres directly.**

### Rule 2: Processors go in `workers/processors/{source_type}.py`

- Receive `(source_id, source_type, payload, metadata)` from the
  router.
- Parse the payload, write to domain tables, optionally emit a live
  event.
- **Never accept data from anywhere except the router.**

### Rule 3: External writebacks go in `workers/sinks/{target}.py`

- Triggered either by a processor as a side effect, or by a separate
  LISTEN/NOTIFY consumer.
- Writes to an external system (e.g. a mirror database, Slack,
  vault files).
- **Does not read from sources directly** — it always observes the
  graph or a processor's output.

### Rule 4: Capture API additions are two-line changes

```python
ALLOWED_SOURCE_TYPES = {
    # ... existing ...
    'my-new-source',  # added by module X
}
```

A string addition to a set literal. Git merges it automatically;
deployments are trivial. A source worker should include a startup
guard so that it exits gracefully if its `source_type` is not yet
registered — this lets you ship the worker and the API change as
separate commits without coordination headaches.

## What this means in practice

The pattern is sound and consistently applied. The discipline is
simple: **don't bypass it when it would be convenient.** If you find
yourself reaching for `psycopg.connect()` inside a source worker,
stop and POST to `/capture` instead.

## Related

- [Architecture overview](overview.md)
- [Module System](module-system.md)
- [Knowledge Layers](knowledge-architecture.md)
