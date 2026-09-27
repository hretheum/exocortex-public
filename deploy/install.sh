#!/usr/bin/env bash
#
# F31.12.3 — Install Exocortex systemd units.
#
# Copies all exocortex-*.{service,timer} from deploy/systemd/ to
# /etc/systemd/system/, runs daemon-reload, then enables + starts every
# *.timer unit (services are triggered by their timers; oneshot/long-running
# services not paired with a timer are left for the operator to enable
# manually, per their wake-up semantics).
#
# Usage:
#   sudo bash deploy/install.sh              # real install
#        bash deploy/install.sh --dry-run    # preview, no changes

set -euo pipefail

DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: install.sh [--dry-run]

Options:
  --dry-run   Print actions without copying files or running systemctl.
  -h, --help  Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "error: unknown flag: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_SRC="${SCRIPT_DIR}/systemd"
SYSTEMD_DST="/etc/systemd/system"

if [[ ! -d "${SYSTEMD_SRC}" ]]; then
  echo "error: missing systemd source dir: ${SYSTEMD_SRC}" >&2
  exit 1
fi

shopt -s nullglob
SERVICE_FILES=( "${SYSTEMD_SRC}"/exocortex-*.service )
TIMER_FILES=( "${SYSTEMD_SRC}"/exocortex-*.timer )
shopt -u nullglob

if [[ ${#SERVICE_FILES[@]} -eq 0 && ${#TIMER_FILES[@]} -eq 0 ]]; then
  echo "error: no exocortex-*.service or exocortex-*.timer files found in ${SYSTEMD_SRC}" >&2
  exit 1
fi

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY RUN] Would run: $*"
  else
    "$@"
  fi
}

copy() {
  local src="$1"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY RUN] Would copy ${src#${SCRIPT_DIR}/../} → ${SYSTEMD_DST}/"
  else
    install -m 0644 "${src}" "${SYSTEMD_DST}/$(basename "${src}")"
  fi
}

# 1. Copy unit files.
for f in "${SERVICE_FILES[@]}" "${TIMER_FILES[@]}"; do
  copy "${f}"
done

# 2. Reload systemd.
run systemctl daemon-reload

# 3. Enable + start every timer. Services without a timer (long-running daemons,
# socket-activated units, ExecStartPre helpers) are left for the operator.
for t in "${TIMER_FILES[@]}"; do
  unit="$(basename "${t}")"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY RUN] Would enable+start: ${unit}"
  else
    run systemctl enable --now "${unit}"
  fi
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo
  echo "[DRY RUN] No changes made. Re-run without --dry-run to apply."
fi
