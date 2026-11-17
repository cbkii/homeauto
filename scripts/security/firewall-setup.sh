#!/usr/bin/env bash
# Compatibility entrypoint: intentionally a read-only planner.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 3
exec python3 "$SCRIPT_DIR/firewall-plan.py" "$@"
