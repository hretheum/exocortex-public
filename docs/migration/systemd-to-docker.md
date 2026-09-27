# Migration: systemd → Docker

This guide covers migrating an existing Exocortex installation running under
systemd (the original deployment model) to the Docker Compose stack.

## Before you start

- Read the [Docker deployment guide](../getting-started/docker-deployment.md) first.
- The migration is **zero-downtime** if you follow the steps in order.
- All steps support `--dry-run` mode where applicable.

## Overview

| Old (systemd) | New (Docker) |
|---|---|
| `exocortex-capture.service` | `api` container |
| `exocortex-scorer.service` | `scorer` container |
| `exocortex-notify-listener.service` | `notify-listener` container |
| `exocortex-vault-watcher.service` | `vault-watcher` container |
| `exocortex-ingest.timer` | `scheduler` container (supercronic) |
| `exocortex-synth.timer` | `scheduler` container (supercronic) |
| `exocortex-compile.timer` | `scheduler` container (supercronic) |
| `exocortex-telegram-bot.service` | `telegram-bot` container (`--profile telegram`) |
| Local Postgres 16 | `db` container (or existing external Postgres) |

## Step 1: Export existing database (if moving DB)

If you want to move the data from your bare-metal Postgres to the Docker volume:

```bash
# On the old host — export
sudo -u postgres pg_dump -Fc second_brain > /tmp/exocortex_$(date +%Y%m%d).dump

# Copy to new host (or keep locally if same machine)
scp /tmp/exocortex_*.dump new-host:/opt/exocortex/
```

## Step 2: Stop systemd services (gracefully)

```bash
# Stop in reverse dependency order
sudo systemctl stop \
  exocortex-telegram-bot.service \
  exocortex-notify-listener.service \
  exocortex-vault-watcher.service \
  exocortex-scorer.service \
  exocortex-capture.service

# Stop timers (safe to leave enabled — they won't fire while services are stopped)
sudo systemctl stop \
  exocortex-ingest.timer \
  exocortex-synth.timer \
  exocortex-compile.timer \
  exocortex-rss.timer
```

## Step 3: Prepare docker-compose.override.yml

```bash
cd /opt/exocortex   # or wherever you cloned the repo
cp docker-compose.override.yml.example docker-compose.override.yml
```

Edit `docker-compose.override.yml`:

```yaml
services:
  api:
    environment:
      # Point at your existing vault
      EXOCORTEX_VAULT_PATH: /opt/exocortex-vault
      CAPTURE_API_TOKEN: <your existing token>
      ANTHROPIC_API_KEY: <your key>
```

## Step 4: Start Docker stack

```bash
docker compose up -d --build
```

Wait for all services to be healthy:

```bash
docker compose ps
# All should show "running" or "healthy"
```

## Step 5: Import existing database (if migrating data)

If you exported data in Step 1:

```bash
# Restore into the Docker Postgres
docker compose exec -T db pg_restore \
  -U exocortex -d exocortex -Fc --clean --if-exists \
  < /opt/exocortex/exocortex_*.dump
```

Verify row counts after restore:

```bash
docker compose exec db psql -U exocortex -d exocortex -c \
  "SELECT 'thoughts' tbl, count(*) FROM thoughts
   UNION ALL SELECT 'edges', count(*) FROM edges
   UNION ALL SELECT 'syntheses', count(*) FROM syntheses WHERE superseded_by IS NULL"
```

## Step 6: Smoke test the new stack

```bash
# Health endpoint
curl http://localhost:8000/health

# Quick ingest (dry-run)
docker compose exec api exocortex ingest --from $EXOCORTEX_VAULT_PATH --dry-run --limit 5

# Scheduler log (confirm cron lines)
docker logs scheduler 2>&1 | grep -E "ingest|synth|compile"
```

## Step 7: Disable systemd units

Once you've confirmed the Docker stack is working:

```bash
sudo systemctl disable --now \
  exocortex-capture.service \
  exocortex-scorer.service \
  exocortex-notify-listener.service \
  exocortex-vault-watcher.service \
  exocortex-telegram-bot.service \
  exocortex-ingest.timer \
  exocortex-synth.timer \
  exocortex-compile.timer \
  exocortex-rss.timer
```

## Step 8: (Optional) Migrate external Postgres to Docker volume

If you want all data inside Docker:

```bash
# Already done in steps 1 + 5 above.
# Stop bare-metal Postgres:
sudo systemctl disable --now postgresql
```

## Rollback

If anything goes wrong, restart the systemd units:

```bash
docker compose down
sudo systemctl start \
  exocortex-capture.service \
  exocortex-scorer.service \
  exocortex-ingest.timer \
  exocortex-synth.timer
```

## `exocortex migrate up` — idempotent migrations

The `api` container runs `exocortex migrate up` on every start. This command applies all pending schema migrations from `schema/*.sql` in order and is **idempotent** — re-running on an existing database skips already-applied migrations.

```bash
# Run manually (dry-run):
docker compose exec api exocortex migrate up --dry-run

# Run for real:
docker compose exec api exocortex migrate up
```

The migration table is `schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)`.
Migrations are applied in lexicographic filename order (`00_`, `01_`, …, `32_`, …).

## See also

- [Docker deployment](../getting-started/docker-deployment.md)
- [VPS / Bare metal](../getting-started/vps-bare-metal.md)
