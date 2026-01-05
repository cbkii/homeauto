#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -ne 0 ]] && echo "Run as root (sudo)" && exit 1

source .env

if [[ -z ${ZIGBEE_DEVICE-} || $ZIGBEE_DEVICE == *"XXXX"* ]]; then
  echo "[!] ZIGBEE_DEVICE not set, running auto-discovery"
  ./system/zigbee-discover.sh
  echo "Update .env with the selected ZIGBEE_DEVICE and re-run install."
  exit 1
fi

apt update
apt install -y docker.io docker-compose-plugin bluez adb mosquitto-clients

systemctl enable --now docker bluetooth

install -d /usr/local/bin/ha-actions
cp scripts/bt/*.sh scripts/adb/*.sh /usr/local/bin/ha-actions/
chmod +x /usr/local/bin/ha-actions/*.sh

install -d mosquitto/config
cat >mosquitto/config/mosquitto.conf <<EOF
listener 1883
allow_anonymous false
password_file /mosquitto/config/passwd
EOF

docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto \
  mosquitto_passwd -b /mosquitto/config/passwd "$MQTT_USER" "$MQTT_PASS"

docker compose up -d

echo "Home Assistant available at http://$(hostname -I | awk '{print $1}'):8123"
