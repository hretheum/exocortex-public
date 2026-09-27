---
title: "Docker Deployment"
description: "Run the full Exocortex stack with a single docker compose command"
---

Exocortex ships a `docker-compose.yml` that starts the full stack — database, capture API, workers, and optional Telegram bot — with a single command.

## Prerequisites

- Docker Engine ≥ 24 and Docker Compose ≥ 2.20
- 4 GB RAM (8 GB recommended for the LLM synthesis step)
- First build takes ~3–5 min (Apache AGE compiles from source). Subsequent builds use the layer cache.

## Quickstart

```bash
git clone https://github.com/hretheum/exocortex.git
cd exocortex

# Copy and customise the override template
cp docker-compose.override.yml.example docker-compose.override.yml
# Edit docker-compose.override.yml: set EXOCORTEX_VAULT_PATH

docker compose up -d --build
curl localhost:8000/health   # → {"status":"ok"}
```

After a successful start, `docker compose ps` should show **7+ running containers**:
`db`, `api`, `notify-listener`, `scorer`, `vault-watcher`, `scheduler`, and any profile services.

## Services

| Service | Description | Profile |
|---|---|---|
| `db` | Postgres 16 + pgvector + Apache AGE | always |
| `api` | Capture API (FastAPI, port 8000) | always |
| `notify-listener` | pg\_notify → Telegram push daemon | always |
| `scorer` | Content acquisition scorer (F6.3) | always |
| `vault-watcher` | Vault file watcher → /capture | always |
| `scheduler` | supercronic — ingest/synth/compile crons | always |
| `telegram-bot` | Telegram bot (polling) | `--profile telegram` |
| `syncthing` | Bidirectional vault sync | `--profile full` |

## Environment variables

Minimal required in `.env` (or `docker-compose.override.yml`):

| Variable | Default | Description |
|---|---|---|
| `EXOCORTEX_VAULT_PATH` | `/opt/exocortex-vault` | Host path to your Obsidian vault |
| `TENANT_ID` | `00000000-...0001` | Your tenant UUID |
| `CAPTURE_API_TOKEN` | `dev-token` | Auth token for /capture endpoint |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required for LLM synthesis |
| `DEEPINFRA_API_KEY` | _(empty)_ | Optional LLM fallback |

## Pre-built database image

The `db` service builds Apache AGE from source (~2 min). To skip this on every fresh install, pull the pre-built image:

```bash
docker pull ghcr.io/hretheum/exocortex-db:latest
```

Then edit `docker-compose.yml` (or `docker-compose.override.yml`) and change the `db` service to use:

```yaml
services:
  db:
    image: ghcr.io/hretheum/exocortex-db:latest
    # remove the build: block
```

## Optional profiles

### Telegram bot

```bash
# Set in .env or docker-compose.override.yml:
TG_BOT_TOKEN=1234567890:AABBCCdd...
TG_ALLOWED_USER_IDS=123456789

docker compose --profile telegram up -d telegram-bot
```

### Syncthing

```bash
docker compose --profile full up -d syncthing
# Syncthing UI: http://localhost:8384
```

## Scheduler (supercronic)

The `scheduler` service runs cron jobs inside the container without a cron daemon:

| Schedule | Command |
|---|---|
| Every hour `:00` | `exocortex ingest --from $EXOCORTEX_VAULT_PATH` |
| Every hour `:30` | `python -m exocortex.rss_ingester --once` |
| 03:00 UTC daily | `exocortex synth --all` |
| 04:00 UTC daily | `exocortex compile --domain all` |
| Every 15 min | `python -m exocortex.live_sections --once` |

Logs: `docker logs scheduler`

## Health checks

```bash
# All services
docker compose ps

# Capture API
curl localhost:8000/health

# Database
docker compose exec db pg_isready -U exocortex -d exocortex
```

## Stopping

```bash
docker compose down          # stop containers, keep volumes (data preserved)
docker compose down -v       # stop + wipe all volumes (fresh start)
```

## Troubleshooting

**Port 5432 already in use**
```bash
# Check what's using the port
lsof -i :5432
# Change the mapped port in docker-compose.override.yml:
# ports: ["15432:5432"]
```

**API container starts before migrations finish**
The `api` container runs `exocortex migrate up` before starting uvicorn. If migrations fail, the container exits with a non-zero code. Check `docker logs api` for details.

**Vault watcher not picking up files**
Make sure `EXOCORTEX_VAULT_PATH` is set to the same path in all worker services and the volume is correctly mounted.

## See also

- [VPS / Bare Metal deployment](vps-bare-metal.md)
- [Migration from systemd](../migration/systemd-to-docker.md)
- [Configuration reference](configuration.md)
