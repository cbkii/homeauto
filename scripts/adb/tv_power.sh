#!/usr/bin/env bash
set -euo pipefail
TV_IP="${ANDROID_TV_IP:-192.168.1.60}"
adb connect "$TV_IP" >/dev/null 2>&1 || true
adb -s "$TV_IP" shell input keyevent 26
