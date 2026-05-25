#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_adb_common.sh"

TV_IP="$(require_tv_ip)"
ADB_SERIAL="$(adb_connect "$TV_IP")"
adb -s "$ADB_SERIAL" shell input keyevent 3
