#!/usr/bin/env bash
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
  for mask in {0..7}; do
    profiles=()
    (( mask & 1 )) && profiles+=(--profile zigbee)
    (( mask & 2 )) && profiles+=(--profile extras)
    (( mask & 4 )) && profiles+=(--profile mariadb)
    docker compose --env-file .env.example "${profiles[@]}" config --quiet || exit 2
  done
else
  echo 'BLOCK: Docker CLI/Compose required for complete QA'
  exit 2
fi
echo 'SUCCESS: source QA (runtime qualification remains separate)'
