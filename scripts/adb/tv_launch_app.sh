#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_adb_common.sh"

APP_ID="${1:-}"
if [[ -z "$APP_ID" ]]; then
  echo "Usage: tv_launch_app.sh <android.package.id>"
  exit 1
fi

TV_IP="$(require_tv_ip)"
ADB_SERIAL="$(adb_connect "$TV_IP")"
adb -s "$ADB_SERIAL" shell monkey -p "$APP_ID" -c android.intent.category.LAUNCHER 1 >/dev/null
