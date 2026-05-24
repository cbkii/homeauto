#!/usr/bin/env bash
set -euo pipefail

MIN_DOCKER_VERSION="23.0.0"

usage() {
  cat <<USAGE
Usage: sudo ./install.sh [options]

Options:
  --rotate-mqtt-password   Regenerate mosquitto password file from .env
  --start                  Start stack after install (default)
  --no-start               Do not start stack
  --profiles <csv>         Optional Compose profiles to enable (default: none)
  --with-zigbee            Shortcut for --profiles zigbee
  --with-extras            Shortcut for --profiles extras
  --with-all               Shortcut for --profiles zigbee,extras
  --generate-secrets       Generate strong placeholder-safe credentials into .env
  -h, --help               Show this help
USAGE
}

version_ge() {
  local a="${1%%[-+]*}" b="${2%%[-+]*}"
  [[ "$(printf '%s\n%s\n' "$b" "$a" | sort -V | tail -n1)" == "$a" ]]
}

require_docker_runtime() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found. Install Docker Engine ${MIN_DOCKER_VERSION}+ and retry."
    exit 1
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is required (docker compose)."
    exit 1
  fi

  local server_version
  if ! server_version="$(docker version --format '{{.Server.Version}}' 2>/dev/null)" || [[ -z "$server_version" ]]; then
    echo "Cannot read Docker Server version (daemon unavailable or permission denied)."
    echo "If you were just added to the docker group, log out and back in, then retry."
    exit 1
  fi

  if ! version_ge "$server_version" "$MIN_DOCKER_VERSION"; then
    echo "Docker Engine ${server_version} is too old. Minimum supported version is ${MIN_DOCKER_VERSION}."
    echo "Remediation: upgrade Docker Engine on Debian/Raspberry Pi OS and rerun install."
    exit 1
  fi
}

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

ROTATE_MQTT_PASSWORD=0
START_STACK=1
PROFILES=""
GENERATE_SECRETS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rotate-mqtt-password) ROTATE_MQTT_PASSWORD=1 ;;
    --start) START_STACK=1 ;;
    --no-start) START_STACK=0 ;;
    --profiles) PROFILES="${2:-}"; shift ;;
    --with-zigbee) PROFILES="zigbee" ;;
    --with-extras) PROFILES="extras" ;;
    --with-all) PROFILES="zigbee,extras" ;;
    --generate-secrets) GENERATE_SECRETS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
  shift
done

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and update values."
  exit 1
fi

gen_secret() { tr -dc 'A-Za-z0-9!@#%^*_+=-' </dev/urandom | head -c 32; }
set_env_var() {
  local key="$1" value="$2"
  sed -i -E "s|^${key}=.*$|${key}=${value}|" .env
}

if [[ $GENERATE_SECRETS -eq 1 ]]; then
  set_env_var "MQTT_PASS" "$(gen_secret)"
  set_env_var "MARIADB_ROOT_PASSWORD" "$(gen_secret)"
  set_env_var "MARIADB_PASSWORD" "$(gen_secret)"
  echo "Generated fresh credentials for MQTT_PASS/MARIADB_ROOT_PASSWORD/MARIADB_PASSWORD in .env"
fi

# shellcheck disable=SC1091
source .env

required_vars=(TZ MQTT_USER MQTT_PASS MARIADB_ROOT_PASSWORD MARIADB_DATABASE MARIADB_USER MARIADB_PASSWORD)
if [[ ",$PROFILES," == *",zigbee,"* ]]; then
  required_vars+=(ZIGBEE_DEVICE)
fi
for v in "${required_vars[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "Missing required variable in .env: $v"
    exit 1
  fi
done

is_unsafe() {
  local v="$1"
  [[ -z "$v" || "$v" =~ ^(replace_with_strong_password|replace_with_strong_root_password|replace_with_strong_db_password|REPLACE_ME|changeme|password|1234)$ ]]
}

for secret_name in MQTT_PASS MARIADB_ROOT_PASSWORD MARIADB_PASSWORD; do
  if is_unsafe "${!secret_name}"; then
    echo "Unsafe placeholder value detected for ${secret_name} in .env."
    echo "Edit .env manually or run: sudo ./install.sh --generate-secrets"
    exit 1
  fi
done

if [[ ",$PROFILES," == *",zigbee,"* ]] && [[ ! -e "$ZIGBEE_DEVICE" ]]; then
  echo "ZIGBEE_DEVICE does not exist: $ZIGBEE_DEVICE"
  echo "Run ./system/zigbee-discover.sh and set ZIGBEE_DEVICE in .env"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-plugin bluez adb mosquitto-clients
systemctl enable --now docker bluetooth

require_docker_runtime

install -d -m 0755 /usr/local/bin/ha-actions
cp scripts/bt/*.sh scripts/adb/*.sh /usr/local/bin/ha-actions/
chmod 0755 /usr/local/bin/ha-actions/*.sh
install -m 0755 scripts/ha-action-bridge/ha-action-bridge.sh /usr/local/bin/ha-action-bridge.sh

install -m 0600 /dev/null /etc/ha-action-bridge.env
{
  printf 'MQTT_HOST=127.0.0.1\n'
  printf 'MQTT_PORT=1883\n'
  printf 'MQTT_USER=%s\n' "${MQTT_USER}"
  printf 'MQTT_PASS=%s\n' "${MQTT_PASS}"
} >> /etc/ha-action-bridge.env

install -m 0644 scripts/ha-action-bridge/ha-action-bridge.service /etc/systemd/system/ha-action-bridge.service
systemctl daemon-reload

install -d -m 0755 ha zigbee2mqtt esphome nodered mariadb mosquitto/config mosquitto/data mosquitto/log
[[ -f ha/configuration.yaml ]] || cp ha/configuration.yaml.example ha/configuration.yaml
if [[ ! -f ha/secrets.yaml ]] && [[ -f ha/secrets.yaml.example ]]; then
  cp ha/secrets.yaml.example ha/secrets.yaml
fi
[[ -f zigbee2mqtt/configuration.yaml ]] || cp zigbee2mqtt/configuration.yaml.example zigbee2mqtt/configuration.yaml
[[ -f mosquitto/config/mosquitto.conf ]] || cp mosquitto/config/mosquitto.conf.example mosquitto/config/mosquitto.conf

if grep -Eq 'REPLACE_ME|replace_with_strong_|changeme|password' ha/secrets.yaml zigbee2mqtt/configuration.yaml; then
  echo "Unsafe placeholders found in ha/secrets.yaml or zigbee2mqtt/configuration.yaml."
  echo "Update those files before starting services."
  exit 1
fi

if [[ ! -f mosquitto/config/passwd ]] || [[ $ROTATE_MQTT_PASSWORD -eq 1 ]]; then
  docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
    mosquitto_passwd -b -c /mosquitto/config/passwd "$MQTT_USER" "$MQTT_PASS"
  chmod 0600 mosquitto/config/passwd
fi

if [[ $START_STACK -eq 1 ]]; then
  systemctl stop ha-action-bridge 2>/dev/null || true
  if [[ -n "$PROFILES" ]]; then
    docker compose $(printf -- '--profile %s ' ${PROFILES//,/ }) up -d
  else
    docker compose up -d
  fi
  systemctl enable --now ha-action-bridge
  echo "Home Assistant available at http://$(hostname -I | awk '{print $1}'):8123"
else
  echo "Install complete. Stack not started (--no-start)."
fi
