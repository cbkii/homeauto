# Operations Guide

Day-to-day reference for running and maintaining the homeauto stack.

---

## Prerequisites

- Debian 12 / Raspberry Pi OS Bookworm (64-bit)
- User with `sudo` access
- Internet access for package and image pulls
- Zigbee coordinator connected (if using Zigbee2MQTT)

---

## First-time setup

### 1. Configure environment

```bash
cp .env.example .env
nano .env
```

Required variables:

| Variable | Description |
|---|---|
| `TZ` | Timezone (e.g. `Europe/London`) |
| `ZIGBEE_DEVICE` | Stable coordinator path under `/dev/serial/by-id/` |
| `MQTT_USER` | MQTT broker username |
| `MQTT_PASS` | MQTT broker password (choose a strong value) |

Optional variables (used as defaults by helper scripts):

| Variable | Description |
|---|---|
| `ANDROID_TV_IP` | LAN IP of Android TV device |
| `BT_DEVICE_MAC` | Bluetooth device MAC address |
| `BT_PAIR_PIN` | PIN for Bluetooth pairing (leave empty if not required) |

### 2. Discover Zigbee coordinator path

```bash
./system/zigbee-discover.sh
```

Copy the output path into `.env` as `ZIGBEE_DEVICE`.

### 3. Update Zigbee2MQTT credentials

Edit `zigbee2mqtt/configuration.yaml.example` before first install (or edit
`zigbee2mqtt/configuration.yaml` after install) to set:

```yaml
mqtt:
  user: <your MQTT_USER>
  password: <your MQTT_PASS>
```

These must match the values in `.env`.

### 4. Install the stack

```bash
sudo ./install.sh
```

This will:
- Install system packages (`docker.io`, `docker-compose-plugin`, `bluez`, `adb`, `mosquitto-clients`)
- Enable `docker` and `bluetooth` systemd services
- Install helper scripts to `/usr/local/bin/ha-actions/`
- Install and enable the `ha-action-bridge` systemd service
- Create config directories and copy example files (without overwriting existing ones)
- Generate the MQTT password file
- Start the Docker Compose stack

After install, Home Assistant is available at `http://<host-ip>:8123`.

---

## Useful install flags

| Flag | Effect |
|---|---|
| `--no-start` | Install without starting the stack |
| `--rotate-mqtt-password` | Regenerate the MQTT password file from `.env` |

---

## Updating

### Pull new images and restart

```bash
./update.sh --restart
```

### Pull images only (no restart)

```bash
./update.sh --pull-only
```

### Reconcile host dependencies and restart

```bash
./scripts/stack/upgrade.sh
```

This re-runs `install.sh --no-start` (to reconcile host packages and helper
scripts) then restarts the stack.

---

## Uninstalling

### Remove containers, preserve data

```bash
sudo ./uninstall.sh --yes
```

### Remove containers and all stack data

```bash
sudo ./uninstall.sh --yes --purge-data
```

Uninstall removes:
- All Docker Compose containers and volumes
- `ha-action-bridge` systemd service and credentials
- `/usr/local/bin/ha-actions/` and `/usr/local/bin/ha-action-bridge.sh`
- `/etc/ha-action-bridge.env`

With `--purge-data` also removes: `ha/`, `zigbee2mqtt/`, `mosquitto/`.

---

## Service management

### Docker Compose stack

```bash
docker compose ps          # check status
docker compose up -d       # start/restart
docker compose down        # stop
docker compose logs -f     # tail logs (all services)
docker compose logs -f homeassistant   # HA logs only
docker compose logs -f mosquitto
docker compose logs -f zigbee2mqtt
```

### ha-action-bridge service

```bash
systemctl status ha-action-bridge
journalctl -fu ha-action-bridge   # follow logs
systemctl restart ha-action-bridge
```

---

## MQTT password rotation

1. Update `MQTT_PASS` in `.env`.
2. Update `ha/secrets.yaml` (`mqtt_password`).
3. Update `zigbee2mqtt/configuration.yaml` (`mqtt.password`).
4. Re-run install to rotate the password file and restart:

```bash
sudo ./install.sh --rotate-mqtt-password --start
```

---

## Triggering helper actions from Home Assistant

Actions are triggered from HA automations by publishing to MQTT topics.
See [docs/ARCHITECTURE.md](ARCHITECTURE.md) for the full topic and payload schema.

**Example HA automation (UI or YAML):**

```yaml
action:
  - action: mqtt.publish
    data:
      topic: ha/actions/tv_power
      payload: "192.168.1.60"
```

To use an input helper dynamically:

```yaml
action:
  - action: mqtt.publish
    data:
      topic: ha/actions/tv_power
      payload: "{{ states('input_text.android_tv_ip') }}"
```

---

## Zigbee2MQTT frontend

Available at `http://<host-ip>:8080` after the stack is running.

---

## Backup and restore

### Create a backup

```bash
./scripts/stack/backup.sh
```

Creates a timestamped archive at `./backups/homeauto-backup-<timestamp>.tar.gz`
containing `ha/`, `zigbee2mqtt/`, `mosquitto/`, and `.env`.

To write the archive elsewhere:

```bash
./scripts/stack/backup.sh /path/to/backup-dir
```

### Restore from a backup

```bash
tar -xzf backups/homeauto-backup-<timestamp>.tar.gz
sudo ./install.sh --no-start   # reconcile host state (packages, helper scripts)
docker compose up -d
```

### What is backed up

| Path | Contents |
|---|---|
| `ha/` | HA configuration, automations, history DB |
| `zigbee2mqtt/` | Zigbee2MQTT config and device/coordinator state |
| `mosquitto/` | MQTT config, password file, persistent session data |
| `.env` | Credentials and runtime configuration |

Container images are **not** included — they are re-pulled on restore.

### Off-site and scheduled backups

No automated scheduling or off-site transfer is included in v1.
For scheduled backups, add a cron job:

```bash
# Example: daily backup at 02:00, keeping 14 days
0 2 * * * cd /path/to/homeauto && ./scripts/stack/backup.sh >> /var/log/homeauto-backup.log 2>&1
find /path/to/homeauto/backups -name 'homeauto-backup-*.tar.gz' -mtime +14 -delete
```
