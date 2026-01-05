#!/usr/bin/env bash
set -euo pipefail

TV_IP="${ANDROID_TV_IP:-192.168.1.60}"

# Ensure target is RFC1918
case "$TV_IP" in
  10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*)
    ;;
  *)
    echo "Refusing to connect to non-LAN IP"
    exit 1
    ;;
esac

adb connect "$TV_IP" >/dev/null 2>&1 || true
adb -s "$TV_IP" shell input keyevent 26
