#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "shellcheck is required but not installed"
  exit 1
fi

mapfile -t shell_files < <(rg --files -g '*.sh')
if [[ ${#shell_files[@]} -eq 0 ]]; then
  echo "No shell scripts found"
  exit 1
fi

shellcheck "${shell_files[@]}"
docker compose config >/dev/null

echo "QA checks passed"
