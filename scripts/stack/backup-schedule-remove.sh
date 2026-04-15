#!/usr/bin/env bash
# backup-schedule-remove.sh — remove the homeauto backup systemd timer.
#
# Reverses backup-schedule-install.sh.
# Data and backup archives are NOT removed.
#
# Usage:
#   sudo ./scripts/stack/backup-schedule-remove.sh
set -euo pipefail

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

echo "Removing homeauto backup timer..."

systemctl stop homeauto-backup.timer 2>/dev/null || true
systemctl disable homeauto-backup.timer 2>/dev/null || true
rm -f /etc/systemd/system/homeauto-backup.service
rm -f /etc/systemd/system/homeauto-backup.timer
systemctl daemon-reload

echo "Backup timer removed.  Existing backup archives are preserved."
