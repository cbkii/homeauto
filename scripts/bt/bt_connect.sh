#!/usr/bin/env bash
set -euo pipefail

DEVICE_MAC="${BT_DEVICE_MAC:-}"
if [[ -z "$DEVICE_MAC" ]]; then
  echo "BT_DEVICE_MAC is required"
  exit 1
fi

bluetoothctl <<BTCTL
power on
agent off
discoverable off
pairable off
connect $DEVICE_MAC
BTCTL
