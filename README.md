# homeauto stack

Production-lean Home Assistant Container stack for Raspberry Pi OS / Debian 12 (Bookworm) with Docker Compose.

## Included services
- Home Assistant (Container)
- Mosquitto (MQTT broker with auth)
- Zigbee2MQTT (serial adapter via `/dev/serial/by-id/*`)
- Android TV helper scripts over ADB (LAN-only)
- Bluetooth helper scripts (BlueZ host tooling)

## Security defaults
- MQTT anonymous access is disabled.
- Helper scripts reject non-LAN Android TV targets.
- Bluetooth scripts disable discoverable/pairable modes after actions.
- No WAN exposure or reverse proxy automation is included.

## Prerequisites
- Debian 12 / Raspberry Pi OS Bookworm (64-bit)
- Internet access for package/image pulls
- User with sudo access
- Zigbee coordinator connected (if using Zigbee2MQTT)

## Configuration
1. Copy and edit environment file:
   ```bash
   cp .env.example .env
   nano .env
   ```
2. Set `ZIGBEE_DEVICE` to a stable path under `/dev/serial/by-id/*`.
   - Use discovery helper:
     ```bash
     ./system/zigbee-discover.sh
     ```

## Install
```bash
sudo ./install.sh
```

Install behavior:
- Installs required packages (`docker.io`, `docker-compose-plugin`, `bluez`, `adb`, `mosquitto-clients`)
- Creates missing config/data directories
- Creates MQTT password file only if missing (or when explicitly rotating)
- Starts stack by default

Useful flags:
```bash
sudo ./install.sh --no-start
sudo ./install.sh --rotate-mqtt-password
```

## Update / upgrade
Pull and restart stack:
```bash
./update.sh --restart
```

Pull only:
```bash
./update.sh --pull-only
```

Combined helper (reconcile host deps + restart stack):
```bash
./scripts/stack/upgrade.sh
```

## Uninstall / rollback
Remove containers and installed helper scripts, preserve data by default:
```bash
sudo ./uninstall.sh --yes
```

Purge all local stack data too:
```bash
sudo ./uninstall.sh --yes --purge-data
```

## Home Assistant notes
- This repo targets **Home Assistant Container**, not HA OS or Supervisor add-ons.
- `ha/configuration.yaml` ships shell commands for BT/ADB helpers.
- Put sensitive values in `ha/secrets.yaml` (copy from `ha/secrets.yaml.example`).

## Bluetooth notes
- Host BlueZ service is required.
- HA container mounts `/run/dbus`.
- `homeassistant` remains `privileged: true` for compatibility in this phase.

## Android TV notes
Available helper scripts:
- `tv_power.sh`
- `tv_home.sh`
- `tv_back.sh`
- `tv_launch_app.sh <android.package.id>`

All require `ANDROID_TV_IP` and enforce RFC1918 LAN-only addresses.

## Zigbee2MQTT notes
- Config file: `zigbee2mqtt/configuration.yaml`
- Default serial path in-container: `/dev/zigbee`
- Update Zigbee2MQTT MQTT credentials to match Mosquitto values.

## Quality gates
Run local validations:
```bash
./scripts/qa.sh
```

This checks:
- `shellcheck` on all `*.sh`
- `docker compose config`

## Operations checklist
See `FINALIZATION_CHECKLIST.md` for the full implementation and completion-tracking plan.

## Access
Home Assistant web UI:
- `http://<host-ip>:8123`
