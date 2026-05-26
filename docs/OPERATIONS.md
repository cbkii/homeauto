# Operations Guide

Day-to-day reference for running and maintaining the homeauto stack.

---

## Prerequisites

- Debian 12 / Raspberry Pi OS Bookworm (64-bit) baseline
- Debian 13 / Raspberry Pi OS Trixie (64-bit) compatibility candidate
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
| `MARIADB_ROOT_PASSWORD` | Root password for MariaDB container |
| `MARIADB_DATABASE` | Shared application database name (default `homeauto`) |
| `MARIADB_USER` | Non-root application DB user |
| `MARIADB_PASSWORD` | Password for `MARIADB_USER` |

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

### 3. Update Zigbee2MQTT + Home Assistant DB credentials

Edit `zigbee2mqtt/configuration.yaml.example` before first install (or edit
`zigbee2mqtt/configuration.yaml` after install) to set:

```yaml
mqtt:
  user: <your MQTT_USER>
  password: <your MQTT_PASS>
```

These must match the values in `.env`.

Edit `ha/secrets.yaml.example` (before first install) or `ha/secrets.yaml`
(after install) so `recorder_db_url` matches the MariaDB values from `.env`:

```yaml
recorder_db_url: mysql://<MARIADB_USER>:<MARIADB_PASSWORD>@127.0.0.1:3306/<MARIADB_DATABASE>?charset=utf8mb4
```

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
Additional UIs:
- Zigbee2MQTT: `http://<host-ip>:8080`
- ESPHome: `http://<host-ip>:6052`
- Node-RED: `http://<host-ip>:1880`

---

## Useful install flags

| Flag | Effect |
|---|---|
| `--no-start` | Install without starting the stack |
| `--rotate-mqtt-password` | Regenerate the MQTT password file from `.env` |
| `--preflight-only` | Run platform and dependency checks without changing the host |

### Trixie package variance troubleshooting

On some Debian 13 / Pi OS Trixie hosts, package naming or repository state can
drift over time. Run:

```bash
sudo ./install.sh --preflight-only
```

If preflight reports missing packages, resolve apt repository issues first, then
re-run install.

---

## Updating

### Pull new images and restart

```bash
./update.sh --restart
```

To use explicit pinned image versions:

```bash
docker compose -f docker-compose.yml -f docker-compose.pinned.yml pull
docker compose -f docker-compose.yml -f docker-compose.pinned.yml up -d
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

With `--purge-data` also removes: `ha/`, `zigbee2mqtt/`, `esphome/`, `nodered/`,
`mariadb/`, `mosquitto/`.

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
docker compose logs -f esphome
docker compose logs -f nodered
docker compose logs -f mariadb
```

### ha-action-bridge service

```bash
systemctl status ha-action-bridge
journalctl -fu ha-action-bridge   # follow logs
systemctl restart ha-action-bridge
```

---

## Release smoke verification

Non-destructive verification:

```bash
./scripts/smoke/run_release_smoke.sh --mode verify
```

Full lifecycle on a target host:

```bash
sudo ./scripts/smoke/run_release_smoke.sh --mode full
```

Capture bridge dispatch evidence and purge data at end:

```bash
sudo ./scripts/smoke/run_release_smoke.sh \
  --mode full \
  --bridge-test \
  --bridge-payload "192.168.1.60" \
  --uninstall-mode purge
```

The script writes a markdown report to `./artifacts/` by default.
See `docs/SMOKE_TEST_RUNBOOK.md` for the release sign-off checklist.

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

## ESPHome dashboard

Available at `http://<host-ip>:6052` after the stack is running.

## Node-RED editor

Available at `http://<host-ip>:1880` after the stack is running.

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
| `esphome/` | ESPHome project YAML and device configs |
| `nodered/` | Node-RED flows and settings |
| `mariadb/` | MariaDB data directory (HA recorder DB and app workloads) |
| `.env` | Credentials and runtime configuration |

Container images are **not** included — they are re-pulled on restore.

### Off-site and scheduled backups

**Scheduled backup via systemd timer (opt-in):**

```bash
# Install the timer (does NOT enable it automatically):
sudo ./scripts/stack/backup-schedule-install.sh

# Enable and start daily backups:
sudo systemctl enable --now homeauto-backup.timer

# Check timer status:
systemctl list-timers homeauto-backup.timer

# View backup logs:
journalctl -u homeauto-backup.service

# Run a backup immediately:
sudo systemctl start homeauto-backup.service

# Remove the timer:
sudo ./scripts/stack/backup-schedule-remove.sh
```

The timer fires daily at 02:00 local time (±10 min jitter).  Archives are
written to `./backups/` by default; pass a different path to the install script.

**Off-site transfer template (rsync):**

```bash
# Example: push today's backup to a remote host after the local backup runs.
# Add to /etc/systemd/system/homeauto-backup.service ExecStartPost, or run
# from a separate script/cron:
rsync -a --remove-source-files \
  /path/to/homeauto/backups/homeauto-backup-*.tar.gz \
  user@backup-host:/backups/homeauto/
```

For encrypted off-site backups, use `rclone` with a remote configured with
client-side encryption:
```bash
rclone copy /path/to/homeauto/backups homeauto-encrypted:backups --min-age 1h
```

**Credential handling:** off-site credentials (SSH keys, rclone config) must
not be stored in the repo.  Store them in `~/.ssh/` or `~/.config/rclone/` and
reference them from the script.  Never commit off-site credentials.

**Retention:** prune old archives to limit disk use:
```bash
find /path/to/homeauto/backups -name 'homeauto-backup-*.tar.gz' -mtime +14 -delete
```

---

## Host firewall (opt-in)

The stack does not configure a host firewall by default.  An opt-in helper
script is provided for operators who want a basic ufw baseline.

**This is optional.  Do not run it unless you understand what it does.**

```bash
# Install ufw if not already present:
sudo apt-get install -y ufw

# Preview the script before running:
cat scripts/security/firewall-setup.sh

# Apply the baseline (LAN_CIDR defaults to 192.168.0.0/16):
sudo ./scripts/security/firewall-setup.sh

# Customise the LAN range:
sudo HOMEAUTO_LAN_CIDR=10.0.0.0/8 ./scripts/security/firewall-setup.sh
```

**What the baseline does:**
- Denies all inbound connections by default.
- Allows SSH on port 22 (protect this — don't remove it before running).
- Allows LAN access to HA (8123), MQTT (1883), Z2M (8080), ESPHome (6052), Node-RED (1880).
- MariaDB (3306) is intentionally NOT opened to the LAN — only localhost access needed.

**Rollback:**
```bash
sudo ufw disable    # disable without removing rules
sudo ufw reset      # reset all rules and disable
```

See `scripts/security/firewall-setup.sh` for the full rule set and comments.
