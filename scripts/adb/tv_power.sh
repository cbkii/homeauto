#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_adb_common.sh"

TV_IP="$(require_tv_ip)"
adb_connect "$TV_IP"
adb -s "$TV_IP" shell input keyevent 26
