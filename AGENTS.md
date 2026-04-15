# AGENTS.md

## Purpose
This repository provides a production-lean Home Assistant Container stack on
**Debian 12 / Raspberry Pi OS Bookworm** using Docker Compose.

Primary services and capabilities:
- Home Assistant (Container edition — not HA OS)
- Mosquitto (MQTT broker, auth required)
- Zigbee2MQTT (serial Zigbee coordinator bridge)
- Android TV helper scripts over ADB (LAN-only)
- Bluetooth helper scripts (BlueZ host tooling)
- `ha-action-bridge` — host-side systemd service that executes helper scripts on behalf of HA

Agents must optimize for:
- reliability and idempotence,
- least-surprise operations,
- safe rollback/uninstall,
- no secret leakage.

> **Separation of concerns:**
> - `FINALIZATION_CHECKLIST.md` — implementation status, roadmap, decisions, evidence.
> - `AGENTS.md` — contributor/agent operating rules and references.
> - `.github/instructions/` — GitHub-native developer guidance.

---

## Scope

### In scope
- Debian 12 / Raspberry Pi OS Bookworm (64-bit) compatibility.
- Docker Compose managed stack.
- MQTT authentication by default.
- Zigbee coordinator using stable `/dev/serial/by-id/` paths.
- Android TV + Bluetooth helper scripts for LAN/home use.
- `ha-action-bridge` systemd service for host-side script execution.

### Not in scope (unless explicitly requested)
- HA OS / Supervisor addon workflows.
- WAN exposure automation (reverse proxy, port forwarding).
- VLAN/mDNS routing automation.
- Automated coordinator firmware flashing.

---

## Repo invariants (must hold)

1. Install is safely re-runnable (idempotent).
2. Uninstall reverses install with optional data preservation.
3. Secrets are never committed (`.env`, `ha/secrets.yaml`, `mosquitto/config/passwd`, `/etc/ha-action-bridge.env`).
4. Zigbee path discovery favors `/dev/serial/by-id/` over unstable tty paths.
5. Default posture does not expose services to WAN.
6. `shell_command` is NOT used for ADB/Bluetooth actions — use MQTT publish to `ha/actions/#` (see `docs/ARCHITECTURE.md`).

---

## Architecture summary

- All containers use `network_mode: host`.
- HA publishes MQTT messages to trigger ADB and Bluetooth actions.
- `ha-action-bridge` (host systemd service) subscribes to `ha/actions/#` and calls helper scripts.
- Helper scripts live in `scripts/adb/` and `scripts/bt/`, installed to `/usr/local/bin/ha-actions/` by `install.sh`.

See `docs/ARCHITECTURE.md` for the full diagram and action bridge design.

---

## Quality gates

Required for any PR touching shell/config/runtime behavior:
1. `shellcheck` across all `*.sh` files.
2. `docker compose config` validation.
3. Smoke evidence on Debian 12 / Pi OS Bookworm before release sign-off.

Local entrypoint:
```bash
./scripts/qa.sh
```

Release verification:
```bash
./scripts/smoke/run_release_smoke.sh --mode verify   # non-destructive
sudo ./scripts/smoke/run_release_smoke.sh --mode full  # full lifecycle (target host)
```
(Full runbook: `docs/SMOKE_TEST_RUNBOOK.md`)

---

## Official references (primary)

### Home Assistant
- https://www.home-assistant.io/installation/linux/
- https://www.home-assistant.io/common-tasks/container/
- https://www.home-assistant.io/integrations/mqtt/
- https://www.home-assistant.io/integrations/shell_command/
- https://www.home-assistant.io/integrations/bluetooth/
- https://www.home-assistant.io/integrations/androidtv/

### Docker / Compose
- https://docs.docker.com/engine/install/debian/
- https://docs.docker.com/compose/
- https://docs.docker.com/reference/compose-file/services/

### Zigbee2MQTT
- https://www.zigbee2mqtt.io/guide/installation/02_docker.html
- https://www.zigbee2mqtt.io/guide/configuration/
- https://www.zigbee2mqtt.io/guide/configuration/adapter-settings.html

### Mosquitto
- https://mosquitto.org/man/mosquitto-conf-5.html
- https://mosquitto.org/documentation/authentication-methods/

### ADB / BlueZ
- https://developer.android.com/tools/adb
- https://manpages.debian.org/unstable/bluez/bluetoothctl.1.en.html

---

## Agent workflow rules

1. Read `FINALIZATION_CHECKLIST.md` and `docs/ARCHITECTURE.md` before making changes.
2. Keep diffs minimal and reversible.
3. Justify behavior/security changes with official references.
4. If behavior/config changes, update `README.md` + relevant `*.example` files + `docs/`.
5. If completion status or roadmap changes, update `FINALIZATION_CHECKLIST.md`.
6. Never commit secrets or generated credentials.
7. Do not use `shell_command` for ADB/Bluetooth — use the MQTT bridge pattern.
