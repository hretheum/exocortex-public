---
title: "Quickstart: Consultant"
description: "Set up Exocortex for client knowledge management and weekly briefings"
---

If you bill by the hour and your value depends on remembering what every client said three weeks ago, this is for you.

## What you get

- **Morning briefing in Telegram** — every day at 07:00, a synthesis of what's new across clients, what's overdue, and what's contradictory
- **Auto-captured Fireflies meeting notes** — every Fireflies call lands in your vault, tagged by client, with action items extracted
- **Notion sync for deliverables** — your client-facing Notion stays in sync with your private vault; you write once, it appears in both
- **Contradiction alerts** — when a client says X on Monday and Y on Friday, Exocortex tells you

## Prerequisites

- Docker (Desktop or engine) on Linux/macOS/Windows
- A Fireflies account with API access (Pro plan or higher)
- Optional: a Telegram bot token for morning briefings (free, ~2 min to set up via @BotFather)

## Screenshot

![Morning briefing in Telegram](/screenshots/placeholder-telegram-briefing.svg)

## Step 1: Start the stack

```bash
git clone https://github.com/hretheum/exocortex
cd exocortex
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up -d --build
```

Wait ~2 minutes for the database and workers to come up. Check health:

```bash
curl http://localhost:8000/health
```

## Step 2: Connect Fireflies

Edit `.env`:

```bash
FIREFLIES_API_KEY=fk_your_key_here
```

Restart the Fireflies worker:

```bash
docker compose restart fireflies-sync
```

The next time you finish a meeting, the transcript and summary will appear in your vault within ~30 minutes.

## Step 3: Set up Telegram notifications

1. Message **@BotFather** on Telegram, run `/newbot`, follow the prompts. Save the token it gives you.
2. Message your new bot once (just say "hi") so it can DM you.
3. Get your chat ID: `curl https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `"chat":{"id": ...}`
4. Add to `.env`:

```bash
TG_BOT_TOKEN=123456:ABC...
TG_CHAT_ID=987654321
```

5. Enable the Telegram profile:

```bash
docker compose --profile telegram up -d
```

## Step 4: First night shift

The Night Shift runs at 03:00 UTC by default. To trigger it manually right now:

```bash
docker compose exec api python -m exocortex.workers.synthesizer --once
docker compose exec api python -m exocortex.workers.telegram_daily_digest
```

Within seconds, you'll get a Telegram message with the morning briefing.

## A day in the life

| Time | What happens |
|---|---|
| **07:00** | Telegram briefing lands. Skim it on your phone. You see one new contradiction flagged (client said "approved" Friday, "let's revisit" today). |
| **10:00** | Standup with Client A. Fireflies records it. |
| **10:30** | Meeting ends. ~5 min later, the transcript is in your vault under `wiki/work/meetings/2026-05-25-client-a-standup.md`, tagged `client-a`. Action items extracted automatically. |
| **14:00** | Client B call. Same thing. |
| **17:00** | You glance at `wiki/work/clients/client-a.md` — auto-compiled dashboard shows the last 5 meetings, open action items, decisions made this month. |
| **Friday** | Gap Radar weekly report drops. You see one client cluster with 4 meetings but no synthesized decisions. Prompt to review. |

## Next steps

- [Configure your sources](/getting-started/configuration/) — connect Gmail, RSS, Notion mirror
- [Read about Two-Way Cockpit](/why-exocortex/) — how to make Notion your client-facing surface while keeping your private graph
- [MCP tools reference](/guides/mcp-tools/) — ask questions in Claude Desktop with your knowledge as context
