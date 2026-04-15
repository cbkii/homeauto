# Smoke Test Runbook

Reproducible release verification procedure for Debian 12 / Raspberry Pi OS Bookworm.

## Purpose
Validate the install → run → update → uninstall lifecycle and capture evidence to close
finalization checklist items S19/S20.

## Prerequisites
- Target host: Debian 12 or Raspberry Pi OS Bookworm (64-bit).
- `.env` configured with a real Zigbee adapter path and MQTT credentials.
- Network access for package and image pulls.
- Optional: Android TV and Bluetooth target devices for helper validation.

---

## Step 1 — Non-destructive verify (recommended first)

Run on any host with Docker installed:

```bash
./scripts/smoke/run_release_smoke.sh --mode verify
```

Expected results:
- Markdown report generated under `artifacts/smoke-report-<timestamp>.md`.
- Report includes: system info, Docker version, Compose config validation, stack status.
- If `.env` is absent, verify mode automatically uses `.env.example` and records
  a warning in the report.

---

## Step 2 — Full lifecycle smoke (target host, destructive)

Requires sudo and a configured `.env` with valid device paths:

```bash
sudo ./scripts/smoke/run_release_smoke.sh --mode full
```

Optional stricter cleanup:
```bash
sudo ./scripts/smoke/run_release_smoke.sh --mode full --uninstall-mode purge
```

Optional bridge dispatch evidence capture:
```bash
sudo ./scripts/smoke/run_release_smoke.sh \
  --mode full \
  --bridge-test \
  --bridge-payload "192.168.1.60"
```

Expected results:
- `install.sh` succeeds with container stack running.
- `update.sh --restart` succeeds.
- `uninstall.sh --yes` removes containers and host-side services.
- Markdown report generated under `artifacts/`.
- With `--bridge-test`, report includes `ha-action-bridge` journal output.

---

## Step 3 — Manual device checks

After install:

### Containers
```bash
docker compose ps
# Core services should show "Up":
# homeassistant, mosquitto, zigbee2mqtt, esphome, nodered, mariadb
```

### ha-action-bridge service
```bash
systemctl status ha-action-bridge
journalctl -fu ha-action-bridge
```

Test dispatch (substitute real MQTT credentials and TV IP):
```bash
mosquitto_pub -h 127.0.0.1 -u <user> -P <pass> \
  -t ha/actions/tv_power -m "192.168.1.60"
```
Expected: bridge log shows `action=tv_power`, `adb` output visible in journal.

### Zigbee coordinator
```bash
docker compose logs zigbee2mqtt
# Look for: "Connected to MQTT server" and serial port open
```

### ADB helper
```bash
ANDROID_TV_IP=192.168.1.60 /usr/local/bin/ha-actions/tv_power.sh
# Expected: keyevent sent, no LAN-check error
```

### Bluetooth helper
```bash
BT_DEVICE_MAC=AA:BB:CC:DD:EE:FF /usr/local/bin/ha-actions/bt_connect.sh
# Expected: bluetoothctl connects or reports connection state
```

---

## Step 4 — Evidence capture and checklist closure

1. Save the smoke report from `artifacts/smoke-report-<timestamp>.md`.
2. Copy relevant output snippets to `FINALIZATION_CHECKLIST.md` evidence log.
3. Mark S19 done once full lifecycle + hardware checks pass.
4. Mark S20 done after QA, CI, and S19 evidence are all consolidated.

Suggested evidence checklist:
- smoke report path and timestamp
- install/update/uninstall command blocks showing `[PASS]`
- `docker compose ps` output while stack is running
- `ha-action-bridge` dispatch log lines (if `--bridge-test` was used)
- notes on any expected warnings (for example: no coordinator connected)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker compose` fails with socket errors | Docker daemon not running or not accessible | Run on a host with a running Docker daemon |
| `install.sh` fails on `ZIGBEE_DEVICE` check | Adapter not connected or wrong path | Connect adapter; run `./system/zigbee-discover.sh` |
| `ha-action-bridge` not dispatching | MQTT credentials mismatch | Check `/etc/ha-action-bridge.env`; re-run `install.sh --no-start` |
| ADB helper refuses connection | Non-LAN IP or ADB debugging not enabled | Check TV settings; verify IP is RFC1918 |
| Bluetooth helper fails | BlueZ not running or wrong MAC | `systemctl status bluetooth`; verify MAC address |
