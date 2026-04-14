#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: sudo ./uninstall.sh [options]

Options:
  --yes         Do not prompt for confirmation
  --purge-data  Remove ha/, zigbee2mqtt/, mosquitto/ data directories
  -h, --help    Show this help
USAGE
}

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

ASSUME_YES=0
PURGE_DATA=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      ;;
    --purge-data)
      PURGE_DATA=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Stop and remove stack containers? [y/N] " yn
  [[ "$yn" == "y" || "$yn" == "Y" ]] || exit 0
fi

docker compose down -v --remove-orphans || true

rm -rf /usr/local/bin/ha-actions

if [[ $PURGE_DATA -eq 1 ]]; then
  rm -rf ha zigbee2mqtt mosquitto
  echo "Containers removed. Data purged."
else
  echo "Containers removed. Data preserved (pass --purge-data to remove)."
fi
