#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "shellcheck is required but not installed"
  exit 1
fi

mapfile -t shell_files < <(find . -name '*.sh' -not -path '*/.git/*' | sort)
if [[ ${#shell_files[@]} -eq 0 ]]; then
  echo "No shell scripts found"
  exit 1
fi

shellcheck "${shell_files[@]}"

if command -v docker >/dev/null 2>&1; then
  docker compose config >/dev/null
  docker compose --profile zigbee config >/dev/null
  docker compose --profile extras config >/dev/null
  docker compose --profile zigbee --profile extras config >/dev/null
else
  echo "WARNING: docker not available; skipping compose config checks"
fi

./scripts/test/test_release_hardening.sh

echo "QA checks passed"
