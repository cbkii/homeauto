#!/usr/bin/env bash
set -euo pipefail

read -rp "Remove HA stack and configs? [y/N] " yn
[[ $yn != "y" ]] && exit 0

docker compose down -v
rm -rf ha zigbee2mqtt mosquitto
rm -rf /usr/local/bin/ha-actions
echo "Removed."
