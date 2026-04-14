#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: sudo ./install.sh [options]

Options:
  --rotate-mqtt-password   Regenerate mosquitto password file from .env
  --start                  Start stack after install (default)
  --no-start               Do not start stack
  -h, --help               Show this help
USAGE
}

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

ROTATE_MQTT_PASSWORD=0
START_STACK=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rotate-mqtt-password)
      ROTATE_MQTT_PASSWORD=1
      ;;
    --start)
      START_STACK=1
      ;;
    --no-start)
      START_STACK=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and update values."
  exit 1
fi

# shellcheck disable=SC1091
source .env

required_vars=(TZ ZIGBEE_DEVICE MQTT_USER MQTT_PASS)
for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required variable in .env: $v"
    exit 1
  fi
done

if [[ ! -e "$ZIGBEE_DEVICE" ]]; then
  echo "ZIGBEE_DEVICE does not exist: $ZIGBEE_DEVICE"
  echo "Run ./system/zigbee-discover.sh and set ZIGBEE_DEVICE in .env"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-plugin bluez adb mosquitto-clients

systemctl enable --now docker bluetooth

# ---------------------------------------------------------------------------
# Helper scripts: installed to host /usr/local/bin/ha-actions (host-only use)
# NOTE: these scripts are NOT mounted into the HA container.  They are
# executed on the host by the ha-action-bridge service below.
# ---------------------------------------------------------------------------
install -d -m 0755 /usr/local/bin/ha-actions
cp scripts/bt/*.sh scripts/adb/*.sh /usr/local/bin/ha-actions/
chmod 0755 /usr/local/bin/ha-actions/*.sh

# ---------------------------------------------------------------------------
# ha-action-bridge: host-side MQTT subscriber that executes helper scripts
# ---------------------------------------------------------------------------
install -m 0755 scripts/ha-action-bridge/ha-action-bridge.sh \
  /usr/local/bin/ha-action-bridge.sh

# Write environment file with MQTT credentials (not world-readable)
install -m 0600 /dev/null /etc/ha-action-bridge.env
cat > /etc/ha-action-bridge.env <<ENV
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USER=${MQTT_USER}
MQTT_PASS=${MQTT_PASS}
ENV

install -m 0644 scripts/ha-action-bridge/ha-action-bridge.service \
  /etc/systemd/system/ha-action-bridge.service
systemctl daemon-reload
systemctl enable --now ha-action-bridge

# ---------------------------------------------------------------------------
# Config directories and example files
# ---------------------------------------------------------------------------
install -d -m 0755 ha zigbee2mqtt mosquitto/config mosquitto/data mosquitto/log

if [[ ! -f ha/configuration.yaml ]]; then
  cp ha/configuration.yaml.example ha/configuration.yaml
fi

if [[ ! -f ha/secrets.yaml ]] && [[ -f ha/secrets.yaml.example ]]; then
  cp ha/secrets.yaml.example ha/secrets.yaml
fi

if [[ ! -f zigbee2mqtt/configuration.yaml ]]; then
  cp zigbee2mqtt/configuration.yaml.example zigbee2mqtt/configuration.yaml
fi

if [[ ! -f mosquitto/config/mosquitto.conf ]]; then
  cp mosquitto/config/mosquitto.conf.example mosquitto/config/mosquitto.conf
fi

if [[ ! -f mosquitto/config/passwd ]] || [[ $ROTATE_MQTT_PASSWORD -eq 1 ]]; then
  docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
    mosquitto_passwd -b -c /mosquitto/config/passwd "$MQTT_USER" "$MQTT_PASS"
  chmod 0600 mosquitto/config/passwd
fi

if [[ $START_STACK -eq 1 ]]; then
  docker compose up -d
  echo "Home Assistant available at http://$(hostname -I | awk '{print $1}'):8123"
else
  echo "Install complete. Stack not started (--no-start)."
fi
