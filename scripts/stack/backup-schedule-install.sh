#!/usr/bin/env bash
# backup-schedule-install.sh — install a systemd timer for daily automated backups.
#
# !! THIS SCRIPT IS OPT-IN.  It is NOT run by install.sh. !!
# The timer is installed in disabled state; you must enable it explicitly.
#
# What it does:
#   - Installs homeauto-backup.service and homeauto-backup.timer to /etc/systemd/system/.
#   - Does NOT enable or start the timer automatically.
#   - You enable it with:  sudo systemctl enable --now homeauto-backup.timer
#
# Usage:
#   sudo ./scripts/stack/backup-schedule-install.sh [backup-dir]
#
# Arguments:
#   backup-dir   Directory to write archives to (default: <repo-root>/backups).
#                Written into the unit file — change by re-running this script
#                with the new path.
#
# Rollback:
#   sudo ./scripts/stack/backup-schedule-remove.sh
#
# Requirements:
#   - Requires root.
#   - Requires systemd.
set -euo pipefail

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

BACKUP_DIR="${1:-${ROOT_DIR}/backups}"
BACKUP_SCRIPT="${ROOT_DIR}/scripts/stack/backup.sh"

if [[ ! -f "$BACKUP_SCRIPT" ]]; then
  echo "Backup script not found: ${BACKUP_SCRIPT}"
  exit 1
fi

echo "Installing homeauto backup timer."
echo "  Repo root:  ${ROOT_DIR}"
echo "  Backup dir: ${BACKUP_DIR}"
echo ""

# ---- homeauto-backup.service -------------------------------------------
cat > /etc/systemd/system/homeauto-backup.service <<UNIT
[Unit]
Description=homeauto stack backup
After=network.target

[Service]
Type=oneshot
ExecStart=${BACKUP_SCRIPT} ${BACKUP_DIR}
WorkingDirectory=${ROOT_DIR}
StandardOutput=journal
StandardError=journal
UNIT

# ---- homeauto-backup.timer ---------------------------------------------
# Default: daily at 02:00 local time, randomised by up to 10 minutes.
cat > /etc/systemd/system/homeauto-backup.timer <<UNIT
[Unit]
Description=homeauto stack daily backup timer

[Timer]
OnCalendar=*-*-* 02:00:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload

echo "Units installed.  Timer is NOT yet enabled."
echo ""
echo "To enable and start the daily backup timer:"
echo "  sudo systemctl enable --now homeauto-backup.timer"
echo ""
echo "To check the timer:"
echo "  systemctl list-timers homeauto-backup.timer"
echo "  journalctl -u homeauto-backup.service"
echo ""
echo "To run a backup immediately:"
echo "  sudo systemctl start homeauto-backup.service"
echo ""
echo "To remove: sudo ./scripts/stack/backup-schedule-remove.sh"
