#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu 24.04 VPS for Exocortex.
# Usage: sudo bash scripts/bootstrap_vps.sh [--dry-run] [--help]
set -euo pipefail

DRY_RUN=false
REPO_URL="${REPO_URL:-}"
INSTALL_DIR="/opt/exocortex"
EXOCORTEX_USER="exocortex"
LOG_DIR="/var/log/exocortex"
ENV_FILE="/etc/exocortex.env"

usage() {
  cat <<EOF
Usage: sudo bash scripts/bootstrap_vps.sh [--dry-run] [--help]

Bootstrap a fresh Ubuntu 24.04 VPS for Exocortex.

Options:
  --dry-run   Print what would be done, make no changes (exit 0).
  --help      Show this help message.

Environment:
  REPO_URL    Git repository URL to clone (optional).
              If unset, the script creates /opt/exocortex but skips clone.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then
    echo "[DRY RUN] $*"
  else
    eval "$@"
  fi
}

step() {
  echo ""
  echo "==> $1"
}

# ---------------------------------------------------------------------------
step "System dependencies"
run "apt-get update -qq"
run "apt-get install -y --no-install-recommends \
  postgresql-16 postgresql-contrib libpq-dev \
  python3.12 python3.12-venv python3.12-dev \
  git build-essential pkg-config"

# ---------------------------------------------------------------------------
step "pgvector extension"
run "git clone --depth 1 https://github.com/pgvector/pgvector /tmp/pgvector"
run "cd /tmp/pgvector && make && make install"
run "sudo -u postgres psql -c \"CREATE EXTENSION IF NOT EXISTS vector;\""

# ---------------------------------------------------------------------------
step "Apache AGE 1.6 extension"
run "git clone --depth 1 --branch PG16 https://github.com/apache/age /tmp/age"
run "cd /tmp/age && make PG_CONFIG=\$(pg_config) && make install"
run "sudo -u postgres psql -c \"CREATE EXTENSION IF NOT EXISTS age;\""

# ---------------------------------------------------------------------------
step "System user: $EXOCORTEX_USER"
if $DRY_RUN; then
  echo "[DRY RUN] Would create system user '$EXOCORTEX_USER' (if not exists)"
else
  if ! id "$EXOCORTEX_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --home-dir "$INSTALL_DIR" --create-home "$EXOCORTEX_USER"
  else
    echo "User '$EXOCORTEX_USER' already exists — skipping."
  fi
fi

# ---------------------------------------------------------------------------
step "Install directory: $INSTALL_DIR"
run "mkdir -p $INSTALL_DIR"
if [[ -n "$REPO_URL" ]]; then
  run "git clone $REPO_URL $INSTALL_DIR"
else
  if $DRY_RUN; then
    echo "[DRY RUN] REPO_URL not set — would skip clone (manual step required)"
  else
    echo "REPO_URL not set — skipping clone. Copy your exocortex source to $INSTALL_DIR manually."
  fi
fi
run "chown -R $EXOCORTEX_USER:$EXOCORTEX_USER $INSTALL_DIR"

# ---------------------------------------------------------------------------
step "Python venv"
run "python3.12 -m venv $INSTALL_DIR/.venv"
run "$INSTALL_DIR/.venv/bin/pip install --quiet --upgrade pip"
if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
  run "$INSTALL_DIR/.venv/bin/pip install --quiet -r $INSTALL_DIR/requirements.txt"
else
  if $DRY_RUN; then
    echo "[DRY RUN] Would install requirements.txt (file not yet present)"
  fi
fi

# ---------------------------------------------------------------------------
step "Environment file: $ENV_FILE"
if $DRY_RUN; then
  echo "[DRY RUN] Would copy config/.env.example → $ENV_FILE (if not exists)"
  echo "[DRY RUN] Would run: chmod 600 $ENV_FILE && chown $EXOCORTEX_USER:$EXOCORTEX_USER $ENV_FILE"
else
  if [[ -f "$ENV_FILE" ]]; then
    echo "WARNING: $ENV_FILE already exists — not overwriting."
  elif [[ -f "$INSTALL_DIR/config/.env.example" ]]; then
    cp "$INSTALL_DIR/config/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    chown "$EXOCORTEX_USER:$EXOCORTEX_USER" "$ENV_FILE"
    echo "Created $ENV_FILE. Edit it before starting services."
  else
    echo "WARNING: config/.env.example not found in $INSTALL_DIR — create $ENV_FILE manually."
  fi
fi

# ---------------------------------------------------------------------------
step "Log directory: $LOG_DIR"
run "mkdir -p $LOG_DIR"
run "chown $EXOCORTEX_USER:$EXOCORTEX_USER $LOG_DIR"

# ---------------------------------------------------------------------------
echo ""
if $DRY_RUN; then
  echo "[DRY RUN] Dry-run complete — no changes made."
else
  echo "Bootstrap complete."
  echo ""
  echo "Next steps:"
  echo "  1. Edit $ENV_FILE — set DATABASE_URL, API keys, EXOCORTEX_VAULT_PATH"
  echo "  2. Run:  sudo -u $EXOCORTEX_USER $INSTALL_DIR/.venv/bin/exocortex migrate"
  echo "  3. Install services: sudo bash $INSTALL_DIR/deploy/install.sh"
fi
