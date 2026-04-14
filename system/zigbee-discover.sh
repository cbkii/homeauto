#!/usr/bin/env bash
set -euo pipefail

shopt -s nullglob

echo "[*] Discovering Zigbee coordinator..."

candidates=(/dev/serial/by-id/*)

if [[ ${#candidates[@]} -eq 0 ]]; then
  echo "No Zigbee USB devices found under /dev/serial/by-id/."
  exit 1
fi

echo "Found devices:"
PS3="Select device number (or Ctrl+C to cancel): "
select dev in "${candidates[@]}"; do
  if [[ -z "${dev:-}" ]]; then
    echo "Invalid selection"
    continue
  fi

  echo "ZIGBEE_DEVICE=$dev"
  exit 0
done
