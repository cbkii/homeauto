#!/usr/bin/env bash
set -euo pipefail

require_lan_ip() {
  local ip="$1"
  case "$ip" in
    10.*|192.168.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*)
      ;;
    *)
      echo "Refusing to connect to non-LAN IP: $ip" >&2
      exit 1
      ;;
  esac
}

require_tv_ip() {
  local ip="${ANDROID_TV_IP:-}"
  if [[ -z "$ip" ]]; then
    echo "ANDROID_TV_IP is required" >&2
    exit 1
  fi
  require_lan_ip "$ip"
  printf '%s' "$ip"
}

adb_connect() {
  local ip="$1"
  adb connect "$ip" >/dev/null 2>&1 || true
}
