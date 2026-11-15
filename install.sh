#!/usr/bin/env bash
# No caller-directory dependency, package installation, or sourced environment.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 3
exec python3 "$SCRIPT_DIR/scripts/stack/install.py" "$@"
