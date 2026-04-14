#!/usr/bin/env bash
set -euo pipefail

DEVICE_MAC="${BT_DEVICE_MAC:-}"
PAIR_PIN="${BT_PAIR_PIN:-}"

if [[ -z "$DEVICE_MAC" ]]; then
  echo "BT_DEVICE_MAC is required"
  exit 1
fi

if [[ -n "$PAIR_PIN" ]]; then
  bluetoothctl <<BTCTL
power on
agent KeyboardOnly
default-agent
discoverable off
pairable on
scan on
pair $DEVICE_MAC
trust $DEVICE_MAC
connect $DEVICE_MAC
scan off
pairable off
BTCTL
else
  bluetoothctl <<BTCTL
power on
agent on
default-agent
discoverable off
pairable on
scan on
pair $DEVICE_MAC
trust $DEVICE_MAC
connect $DEVICE_MAC
scan off
pairable off
BTCTL
fi
