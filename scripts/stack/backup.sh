#!/usr/bin/env bash
# backup.sh — create a timestamped archive of homeauto stack data.
#
# Backs up: ha/, zigbee2mqtt/, mosquitto/, and .env (if present).
# Does NOT back up container images (re-pulled on restore).
#
# Usage:
#   ./scripts/stack/backup.sh [backup-dir]
#
# Arguments:
#   backup-dir   Directory to write the archive to (default: ./backups)
#
# The archive is a gzip-compressed tar named:
#   homeauto-backup-<YYYYMMDDTHHMMSSZ>.tar.gz
#
# Restore:
#   tar -xzf homeauto-backup-<timestamp>.tar.gz
#   sudo ./install.sh --no-start   # reconcile host state
#   docker compose up -d
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

BACKUP_DIR="${1:-${ROOT_DIR}/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/homeauto-backup-${STAMP}.tar.gz"

cd "$ROOT_DIR"

mkdir -p "$BACKUP_DIR"

TARGETS=()

for d in ha zigbee2mqtt mosquitto; do
  if [[ -d "$d" ]]; then
    TARGETS+=("$d")
  fi
done

if [[ -f .env ]]; then
  TARGETS+=(.env)
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "Nothing to back up — no data directories or .env found."
  exit 1
fi

echo "Backing up: ${TARGETS[*]}"
echo "Writing to: ${BACKUP_FILE}"

tar -czf "$BACKUP_FILE" "${TARGETS[@]}"

echo "Backup complete: ${BACKUP_FILE}"
echo ""
echo "To restore:"
echo "  tar -xzf ${BACKUP_FILE}"
echo "  sudo ./install.sh --no-start   # reconcile host state after restore"
echo "  docker compose up -d"
