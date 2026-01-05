#!/usr/bin/env bash
set -euo pipefail

DEVICE_MAC="AA:BB:CC:DD:EE:FF"

bluetoothctl <<EOF
power on
agent off
discoverable off
pairable off
connect $DEVICE_MAC
EOF
