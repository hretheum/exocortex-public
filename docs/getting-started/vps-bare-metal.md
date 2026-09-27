# VPS / Bare Metal Setup

Deploy Exocortex on a fresh Ubuntu 24.04 server. After following this guide you will have PostgreSQL 16 with pgvector + Apache AGE, a Python venv, and all systemd services installed.

## Prerequisites

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 24.04 LTS |
| CPU | 2 vCPU |
| RAM | 4 GB |
| Disk | 20 GB SSD |
| Network | public IPv4, outbound HTTPS |

A DigitalOcean `s-2vcpu-4gb` droplet in any region works well (~$24/month).

## Quick start

```bash
git clone https://github.com/hretheum/exocortex /opt/exocortex
cd /opt/exocortex
sudo bash scripts/bootstrap_vps.sh
```

The script installs all dependencies, creates the `exocortex` system user, sets up a Python venv, and generates `/etc/exocortex.env` from the bundled template.

Preview what it would do without making any changes:

```bash
sudo bash scripts/bootstrap_vps.sh --dry-run
```

## Step-by-step

### 1. System dependencies

The bootstrap script runs:

```bash
apt-get install -y postgresql-16 postgresql-contrib libpq-dev \
  python3.12 python3.12-venv python3.12-dev git build-essential pkg-config
```

### 2. pgvector

Compiled from source and installed as a PostgreSQL extension:

```bash
git clone --depth 1 https://github.com/pgvector/pgvector /tmp/pgvector
cd /tmp/pgvector && make && make install
sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Apache AGE

Graph extension compiled against PG 16:

```bash
git clone --depth 1 --branch PG16 https://github.com/apache/age /tmp/age
cd /tmp/age && make PG_CONFIG=$(pg_config) && make install
sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS age;"
```

### 4. System user and directories

```bash
useradd --system --shell /bin/bash --home-dir /opt/exocortex --create-home exocortex
```

Logs go to `/var/log/exocortex/` (owned by `exocortex`).

### 5. Python venv

```bash
python3.12 -m venv /opt/exocortex/.venv
/opt/exocortex/.venv/bin/pip install -r /opt/exocortex/requirements.txt
```

### 6. Environment file

The bootstrap copies `config/.env.example` to `/etc/exocortex.env` (mode 600, owner `exocortex`). It will **not** overwrite an existing file.

## Post-install configuration

Edit `/etc/exocortex.env` and fill in at minimum:

```env
DATABASE_URL=postgresql://exocortex:yourpassword@localhost/exocortex
EXOCORTEX_VAULT_PATH=/home/youruser/vault
ANTHROPIC_API_KEY=sk-ant-...
TENANT_ID=your-tenant-id
```

Then run the database migrations:

```bash
sudo -u exocortex /opt/exocortex/.venv/bin/exocortex migrate
```

And install systemd services:

```bash
sudo bash /opt/exocortex/deploy/install.sh
```

Preview the install first:

```bash
sudo bash /opt/exocortex/deploy/install.sh --dry-run
```

## Verification

```bash
systemctl list-timers exocortex-* --no-pager
sudo -u exocortex /opt/exocortex/.venv/bin/exocortex --help
```

## Troubleshooting

**PostgreSQL not starting**
Check `journalctl -u postgresql` — usually a locale or data directory issue. Run `pg_lsclusters` to see cluster state.

**AGE extension missing after install**
Ensure `postgresql.conf` includes `shared_preload_libraries = 'age'` and restart PostgreSQL. The bootstrap script does this via `CREATE EXTENSION`; a manual restart may be needed if the line was not already present.

**Permission errors on `/etc/exocortex.env`**
The file must be owned by `exocortex` and have mode 600. Fix with:
```bash
sudo chown exocortex:exocortex /etc/exocortex.env && sudo chmod 600 /etc/exocortex.env
```

**`exocortex` command not found after install**
The CLI is installed inside the venv:
```bash
/opt/exocortex/.venv/bin/exocortex --help
```
Add `/opt/exocortex/.venv/bin` to `PATH` or create a symlink in `/usr/local/bin`.
