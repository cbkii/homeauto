#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: sudo ./install.sh [options]

Options:
  --rotate-mqtt-password   Regenerate mosquitto password file from .env
  --preflight-only         Validate host/platform/dependencies and exit
  --start                  Start stack after install (default)
  --no-start               Do not start stack
  -h, --help               Show this help
USAGE
}

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

ROTATE_MQTT_PASSWORD=0
START_STACK=1
PREFLIGHT_ONLY=0

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
    --preflight-only)
      PREFLIGHT_ONLY=1
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

check_platform_support() {
  # Platform compatibility map (Debian-family):
  # - bookworm (Debian 12 / Raspberry Pi OS Bookworm): fully supported.
  # - trixie   (Debian 13 / Raspberry Pi OS Trixie): compatibility candidate.
  #   Expected package names currently: docker.io docker-compose-plugin bluez adb mosquitto-clients
  #   Validate on target host and track evidence in FINALIZATION_CHECKLIST.md (S37).
  local os_id os_codename os_version
  os_id="unknown"
  os_codename="unknown"
  os_version="unknown"
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    os_id="${ID:-unknown}"
    os_codename="${VERSION_CODENAME:-unknown}"
    os_version="${VERSION_ID:-unknown}"
  fi

  case "$os_codename" in
    bookworm)
      echo "Platform: ${os_id} ${os_version} (${os_codename}) — supported baseline."
      ;;
    trixie)
      echo "Platform: ${os_id} ${os_version} (${os_codename}) — compatibility candidate."
      echo "Run preflight and smoke tests before production use."
      ;;
    *)
      echo "WARNING: ${os_id} ${os_version} (${os_codename}) is outside declared support boundaries."
      echo "Supported baseline: Debian/Pi OS Bookworm; compatibility candidate: Trixie."
      ;;
  esac
}

check_or_install_packages() {
  local mode="$1"
  local missing_packages=()
  local pkg
  local required_packages=(docker.io docker-compose-plugin bluez adb mosquitto-clients)

  for pkg in "${required_packages[@]}"; do
    if dpkg -s "$pkg" >/dev/null 2>&1; then
      echo "Dependency present: $pkg"
    else
      missing_packages+=("$pkg")
    fi
  done

  if [[ ${#missing_packages[@]} -eq 0 ]]; then
    echo "All required packages are already installed."
    return 0
  fi

  echo "Missing packages: ${missing_packages[*]}"
  if [[ "$mode" == "preflight" ]]; then
    echo "Preflight mode: install required packages before running install."
    return 0
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  if ! apt-get install -y "${missing_packages[@]}"; then
    echo "Failed to install required packages: ${missing_packages[*]}"
    echo "Check package availability for your distro release and retry."
    exit 1
  fi
}

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and update values."
  exit 1
fi

check_platform_support
if [[ $PREFLIGHT_ONLY -eq 1 ]]; then
  check_or_install_packages preflight
else
  check_or_install_packages install
fi

# shellcheck disable=SC1091
source .env

required_vars=(
  TZ
  ZIGBEE_DEVICE
  MQTT_USER
  MQTT_PASS
  MARIADB_ROOT_PASSWORD
  MARIADB_DATABASE
  MARIADB_USER
  MARIADB_PASSWORD
)
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

if [[ $PREFLIGHT_ONLY -eq 1 ]]; then
  echo "Preflight checks complete. No changes were made."
  exit 0
fi

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
{
  printf 'MQTT_HOST=127.0.0.1\n'
  printf 'MQTT_PORT=1883\n'
  printf 'MQTT_USER=%s\n' "${MQTT_USER}"
  printf 'MQTT_PASS=%s\n' "${MQTT_PASS}"
} >> /etc/ha-action-bridge.env

install -m 0644 scripts/ha-action-bridge/ha-action-bridge.service \
  /etc/systemd/system/ha-action-bridge.service
systemctl daemon-reload
systemctl enable --now ha-action-bridge

# ---------------------------------------------------------------------------
# Config directories and example files
# ---------------------------------------------------------------------------
install -d -m 0755 \
  ha \
  zigbee2mqtt \
  esphome \
  nodered \
  mariadb \
  mosquitto/config \
  mosquitto/data \
  mosquitto/log

if [[ ! -f ha/configuration.yaml ]]; then
  cp ha/configuration.yaml.example ha/configuration.yaml
fi

if [[ ! -f ha/secrets.yaml ]] && [[ -f ha/secrets.yaml.example ]]; then
  cp ha/secrets.yaml.example ha/secrets.yaml
fi

if [[ ! -f zigbee2mqtt/configuration.yaml ]]; then
  cp zigbee2mqtt/configuration.yaml.example zigbee2mqtt/configuration.yaml
fi

if grep -q "REPLACE_ME" zigbee2mqtt/configuration.yaml 2>/dev/null; then
  echo ""
  echo "WARNING: zigbee2mqtt/configuration.yaml still contains REPLACE_ME credentials."
  echo "         Edit it and set mqtt.user / mqtt.password to match .env MQTT_USER / MQTT_PASS"
  echo "         before starting the stack, or Zigbee2MQTT will fail to connect to MQTT."
  echo ""
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
