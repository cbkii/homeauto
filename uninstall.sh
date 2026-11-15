#!/usr/bin/env bash
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 3
exec python3 "$ROOT_DIR/scripts/stack/uninstall.py" "$@"
