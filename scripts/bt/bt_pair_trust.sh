#!/usr/bin/env bash
set -euo pipefail

DEVICE_MAC="${BT_DEVICE_MAC:-}"
PAIR_PIN="${BT_PAIR_PIN:-}"

if [[ -z "$DEVICE_MAC" ]]; then
  echo "BT_DEVICE_MAC is required"
  exit 1
fi

if [[ -n "$PAIR_PIN" ]]; then
  echo "NOTE: BT_PAIR_PIN is currently informational only; bluetoothctl non-interactive PIN entry is not reliable across adapters."
fi

echo "=== bluetoothctl show ==="
bluetoothctl show || true
echo "=== paired-devices ==="
bluetoothctl paired-devices || true

echo "Attempting pair/trust/connect for ${DEVICE_MAC}"
bluetoothctl <<BTCTL
power on
agent on
default-agent
discoverable off
pairable on
pair $DEVICE_MAC
trust $DEVICE_MAC
connect $DEVICE_MAC
pairable off
BTCTL

echo "=== device status ==="
bluetoothctl info "$DEVICE_MAC" || true
