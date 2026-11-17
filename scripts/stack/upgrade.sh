#!/usr/bin/env bash
# Stage persisted image tags only. Restarting onto new images requires a verified
# backup and the staged-upgrade procedure; this helper never restarts services.
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$ROOT_DIR/scripts/stack/update.py" --pull-only "$@"
