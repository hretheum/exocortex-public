---
title: "Quickstart: Developer"
description: "Set up Exocortex as your engineering second brain with MCP integration"
---

If you write code, design systems, and make architectural decisions you'll need to justify in 18 months — this is for you.

## What you get

- **MCP tools in Claude Desktop** — `ask()`, `search_thoughts()`, `find_contradictions()` available natively while you code
- **Graph search across decisions and architecture notes** — typed edges (`supports`, `contradicts`, `derives_from`) make recall structural, not just semantic
- **Contradiction detection in technical choices** — when an old ADR says "we use Postgres" and a new RFC says "let's try Mongo," the graph surfaces it
- **Synthesis of architecture patterns** — overnight, the synthesizer clusters related decisions into perspective documents

## Screenshot

![MCP ask() in Claude Desktop](/screenshots/placeholder-ask-response.svg)

## Prerequisites

- Docker (Desktop or engine)
- Claude Desktop (for MCP integration)
- Python 3.11+ (for local CLI tools, optional)

## Step 1: Start the stack

```bash
git clone https://github.com/hretheum/exocortex
cd exocortex
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up -d --build
```

Wait ~2 minutes, then verify:

```bash
docker compose ps
curl http://localhost:8000/health
```

## Step 2: Configure Claude Desktop MCP

Add to your Claude Desktop MCP config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "exocortex": {
      "command": "docker",
      "args": ["compose", "-f", "/path/to/exocortex/docker-compose.yml", "exec", "-T", "api", "python", "-m", "exocortex.mcp_server"]
    }
  }
}
```

Restart Claude Desktop. You should see Exocortex MCP tools available in the tool picker.

## Step 3: Capture your first decision

Two options.

**Option A — POST to the capture API:**

```bash
curl -X POST http://localhost:8000/capture \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "manual-decision",
    "uri": "decisions/2026-05-25-postgres-choice",
    "title": "Decision: PostgreSQL over Mongo",
    "content": "We chose Postgres because of pgvector + AGE. Mongo would have forced us into a separate vector DB."
  }'
```

**Option B — drop a `.md` file in your vault** (if you have one configured at `EXOCORTEX_VAULT_PATH`):

```markdown
---
title: Decision: PostgreSQL over Mongo
tags: [decision, architecture, database]
---

We chose Postgres because of pgvector + AGE. Mongo would have forced us into a separate vector DB.
```

The vault watcher picks it up within seconds.

## Step 4: Ask a question

In Claude Desktop:

> Use exocortex `ask` tool: What was the rationale for choosing PostgreSQL?

You'll get an answer grounded in your captured note, with the source path cited.

## Extending it

**Write a custom plugin** — sources, processors, sinks, and MCP tools are pluggable. See [Writing a Plugin](/guides/writing-a-plugin/).

**Add custom MCP tools** — expose your own functions to Claude Desktop. The [MCP Tools Reference](/guides/mcp-tools/) shows the patterns.

**Connect to your team's Notion** — use the Two-Way Cockpit (F21) to mirror engineering decisions out to a shared Notion DB without giving the team your full private graph. See the [Knowledge Layers architecture](/architecture/knowledge-architecture/).

## Useful MCP queries while coding

```text
ask("What did we decide about retry semantics in the API client?")
find_contradictions("authentication strategy")
search_thoughts("circuit breaker", limit=10)
```
