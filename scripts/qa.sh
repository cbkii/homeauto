#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 3
cd "$SCRIPT_DIR/.." || exit 3
command -v shellcheck >/dev/null || { echo 'BLOCK: shellcheck required'; exit 2; }
mapfile -d '' -t files < <(find . -type f -name '*.sh' -not -path './.git/*' -print0)
for file in "${files[@]}"; do bash -n "$file" || exit 2; done
shellcheck "${files[@]}" || exit 2
python3 -m compileall -q scripts tests || exit 2
python3 -m unittest discover -s tests -v || exit 2
./scripts/qa/check-support-consistency.sh || exit 2
if command -v docker >/dev/null; then
  # 3 profiles x optional Bluetooth overlay = 16 combinations, as install.py composes them.
  for mask in {0..15}; do
    args=(-f docker-compose.yml)
    if (( mask & 8 )); then args+=(-f deploy/q8b/compose.bluetooth.yaml); fi
    if (( mask & 1 )); then args+=(--profile zigbee); fi
    if (( mask & 2 )); then args+=(--profile extras); fi
    if (( mask & 4 )); then args+=(--profile mariadb); fi
    docker compose --env-file .env.example "${args[@]}" config --quiet || exit 2
  done
  # Preserved reference for existing MariaDB-era deployments must still parse.
  docker compose --env-file .env.example -f deploy/legacy/docker-compose.yml config --quiet 2>/dev/null || exit 2
else
  echo 'BLOCK: Docker CLI/Compose required for complete QA'
  exit 2
fi
echo 'SUCCESS: source QA (runtime qualification remains separate)'
