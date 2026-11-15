#!/usr/bin/env bash
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 3
cd "$ROOT_DIR" || exit 3
exec python3 -m unittest discover -s tests -v
