#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="${1:-${ROOT_DIR}/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_DIR="${BACKUP_DIR}/homeauto-backup-${STAMP}"
BACKUP_FILE="${WORK_DIR}.tar.gz"

mkdir -p "$BACKUP_DIR" "$WORK_DIR"
cd "$ROOT_DIR"

for d in ha zigbee2mqtt mosquitto esphome nodered; do
  [[ -d "$d" ]] && cp -a "$d" "$WORK_DIR/"
done

[[ -f .env ]] && install -m 0600 .env "$WORK_DIR/.env"

db_dump_status="skipped"
if command -v docker >/dev/null 2>&1 && docker compose --profile core ps mariadb >/dev/null 2>&1; then
  echo "Creating MariaDB logical dump..."
  if docker compose --profile core exec -T mariadb sh -lc 'exec mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --all-databases --single-transaction --quick --routines --events' > "$WORK_DIR/mariadb-logical.sql"; then
    db_dump_status="ok"
  else
    db_dump_status="failed"
    echo "ERROR: MariaDB logical dump failed. Backup archive will be marked partial." >&2
  fi
fi

chmod -R go-rwx "$WORK_DIR" || true
printf 'db_logical_dump_status=%s\n' "$db_dump_status" > "$WORK_DIR/backup-manifest.txt"

tar -czf "$BACKUP_FILE" -C "$BACKUP_DIR" "$(basename "$WORK_DIR")"
rm -rf "$WORK_DIR"

if [[ "$db_dump_status" == "failed" ]]; then
  echo "Backup complete (PARTIAL - DB logical dump failed): $BACKUP_FILE"
  exit 2
fi

echo "Backup complete: $BACKUP_FILE"
