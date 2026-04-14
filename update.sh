#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: ./update.sh [options]

Options:
  --pull-only   Pull newer images only
  --restart     Pull and restart stack (default)
  -h, --help    Show this help
USAGE
}

ACTION="restart"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull-only)
      ACTION="pull"
      ;;
    --restart)
      ACTION="restart"
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

docker compose pull

if [[ "$ACTION" == "restart" ]]; then
  docker compose up -d
fi
