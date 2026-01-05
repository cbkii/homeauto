#!/usr/bin/env bash
set -euo pipefail

echo "[*] Discovering Zigbee coordinator..."

candidates=$(ls /dev/serial/by-id/* 2>/dev/null || true)

if [[ -z "$candidates" ]]; then
  echo "No Zigbee USB devices found."
  exit 1
fi

echo "Found:"
select dev in $candidates; do
  [[ -n "$dev" ]] || exit 1
  echo "ZIGBEE_DEVICE=$dev"
  exit 0
done
