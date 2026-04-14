#!/usr/bin/env bash
# ha-action-bridge — host-side MQTT action executor
#
# Subscribes to ha/actions/# on the MQTT broker and dispatches to the
# helper scripts in /usr/local/bin/ha-actions/.  Run as a systemd
# service so that Home Assistant can trigger host binaries (adb,
# bluetoothctl) by publishing MQTT messages rather than relying on
# shell_command (which runs inside the HA container where those binaries
# are not available).
#
# Payload format (plain text per topic):
#   ha/actions/tv_power        <android-tv-ip>
#   ha/actions/tv_home         <android-tv-ip>
#   ha/actions/tv_back         <android-tv-ip>
#   ha/actions/tv_launch_app   <android-tv-ip> <app.package.id>
#   ha/actions/bt_connect      <bt-mac>
#   ha/actions/bt_pair_trust   <bt-mac> [pin]
#
# Environment / /etc/ha-action-bridge.env:
#   MQTT_HOST   broker hostname/IP (default: 127.0.0.1)
#   MQTT_PORT   broker port       (default: 1883)
#   MQTT_USER   broker username
#   MQTT_PASS   broker password
set -euo pipefail

# Scripts are installed to this fixed host path by install.sh.
ACTIONS_DIR="/usr/local/bin/ha-actions"

ENV_FILE="/etc/ha-action-bridge.env"
# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"

MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_USER="${MQTT_USER:-}"
MQTT_PASS="${MQTT_PASS:-}"

if [[ -n "${MQTT_USER:-}" && -z "${MQTT_PASS:-}" ]]; then
  printf 'ERROR: MQTT_USER is set but MQTT_PASS is empty\n' >&2
  exit 1
fi

auth_args=()
if [[ -n "${MQTT_USER:-}" ]]; then
  auth_args+=(-u "$MQTT_USER" -P "$MQTT_PASS")
fi

log() { printf '%s [ha-action-bridge] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

dispatch() {
  local topic="$1"
  local payload="$2"
  local action
  action="${topic##ha/actions/}"
  log "action=${action} payload=${payload}"

  case "$action" in
    tv_power|tv_home|tv_back)
      [[ -z "$payload" ]] && log "ERROR: ${action} requires IP payload" && return 1
      ANDROID_TV_IP="$payload" "$ACTIONS_DIR/${action}.sh"
      ;;
    tv_launch_app)
      # payload format: "<ip> <app.package>" — read assigns remainder to app
      read -r ip app <<< "$payload"
      if [[ -z "${ip:-}" || -z "${app:-}" ]]; then
        log "ERROR: tv_launch_app requires '<ip> <app.package>' payload"
        return 1
      fi
      ANDROID_TV_IP="$ip" "$ACTIONS_DIR/tv_launch_app.sh" "$app"
      ;;
    bt_connect)
      [[ -z "$payload" ]] && log "ERROR: bt_connect requires MAC payload" && return 1
      BT_DEVICE_MAC="$payload" "$ACTIONS_DIR/bt_connect.sh"
      ;;
    bt_pair_trust)
      # payload format: "<mac> [pin]" — pin is optional
      read -r mac pin <<< "$payload"
      if [[ -z "${mac:-}" ]]; then
        log "ERROR: bt_pair_trust requires '<mac> [pin]' payload"
        return 1
      fi
      BT_DEVICE_MAC="$mac" BT_PAIR_PIN="${pin:-}" "$ACTIONS_DIR/bt_pair_trust.sh"
      ;;
    *)
      log "WARN: unknown action '${action}' — ignored"
      ;;
  esac
}

log "Starting (broker=${MQTT_HOST}:${MQTT_PORT}, topic=ha/actions/#)"

# mosquitto_sub -v outputs lines as: "<topic> <payload>"
# Using read with two variables: topic gets the first word, payload gets
# all remaining text (including any internal spaces) up to end-of-line.
mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" "${auth_args[@]}" \
  -t "ha/actions/#" -v |
while IFS=' ' read -r topic payload; do
  dispatch "$topic" "${payload:-}" || log "dispatch error: topic=${topic}"
done
