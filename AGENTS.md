# AGENTS.md

## Purpose
This repository provides a production-lean Home Assistant stack on **Debian 12 / Raspberry Pi OS Bookworm** using Docker Compose.

Primary services and capabilities:
- Home Assistant (Container)
- Mosquitto (MQTT broker)
- Zigbee2MQTT
- Android TV control helpers (ADB)
- Bluetooth helpers (BlueZ-based)

Agents must optimize for:
- reliability,
- idempotence,
- least surprise operations,
- safe rollback/uninstall,
- no secret leakage.

> **Important separation of concerns:**
> - `FINALIZATION_CHECKLIST.md` is the authoritative file for implementation status, roadmap, and pending work.
> - `AGENTS.md` and `.github/instructions/*` are instruction/reference documents for contributors and coding agents.

---

## Scope and non-goals
### In scope
- Debian 12 / Raspberry Pi OS Bookworm compatibility.
- Docker Compose managed stack.
- MQTT authentication by default.
- Zigbee coordinator using stable device paths (`/dev/serial/by-id/*`).
- Android TV + Bluetooth helper scripts suitable for LAN/home use.

### Not in scope (unless explicitly requested)
- HA OS / Supervisor addon workflows.
- WAN exposure automation (reverse proxy/port forwarding).
- VLAN/mDNS routing automation.
- Automated coordinator firmware flashing.

---

## Repo invariants (must hold)
1. Install is safely re-runnable.
2. Uninstall reverses install with optional data preservation.
3. Secrets are never committed (`.env`, `ha/secrets.yaml`, runtime password files).
4. Zigbee path discovery favors `/dev/serial/by-id/*` over unstable tty paths.
5. Default posture does not expose services to WAN.

---

## Expected operator behavior

### Home Assistant container
- Treat this as Home Assistant **Container**, not HA OS.
- Use standalone containers and HA UI integrations.

### Networking
- Host network mode is expected for local discovery reliability.
- Do not add internet-facing defaults.

### MQTT / Mosquitto
- Keep auth enabled (`allow_anonymous false`, `password_file ...`).
- Avoid committing generated password files.

### Zigbee2MQTT
- Keep coordinator mapping stable and explicit.
- Keep `zigbee2mqtt/configuration.yaml` writable for runtime/frontend updates.

### Android TV (ADB)
- Enforce LAN-only target checks.
- Keep helper scripts non-interactive and fail-fast on missing config.

### Bluetooth
- Assume host BlueZ availability.
- Keep discoverable/pairable modes disabled unless actively pairing.

---

## Quality gates for changes
Required checks for PRs touching shell/config/runtime behavior:
1. `shellcheck` across repository scripts.
2. `docker compose config` validation.
3. Smoke evidence on Debian 12 / Pi OS Bookworm before final release sign-off.

Local entrypoint:
```bash
./scripts/qa.sh
```

Release verification helper:
```bash
./scripts/smoke/run_release_smoke.sh --mode verify
```
(Full lifecycle runbook: `docs/SMOKE_TEST_RUNBOOK.md`)

---

## Official references (primary)
(Last curated: 2026-04-14)

### Home Assistant
- https://www.home-assistant.io/docs/
- https://www.home-assistant.io/installation/linux/
- https://www.home-assistant.io/installation/raspberrypi-other/
- https://www.home-assistant.io/common-tasks/container/
- https://www.home-assistant.io/integrations/mqtt/
- https://www.home-assistant.io/integrations/bluetooth/
- https://www.home-assistant.io/integrations/androidtv/
- https://www.home-assistant.io/integrations/androidtv_remote/
- https://www.home-assistant.io/integrations/tuya/

### Docker / Compose
- https://docs.docker.com/engine/install/debian/
- https://docs.docker.com/compose/
- https://docs.docker.com/reference/compose-file/
- https://docs.docker.com/reference/compose-file/services/

### Zigbee2MQTT
- https://www.zigbee2mqtt.io/
- https://www.zigbee2mqtt.io/guide/installation/02_docker.html
- https://www.zigbee2mqtt.io/guide/installation/docker/docker_stack.html
- https://www.zigbee2mqtt.io/guide/configuration/
- https://www.zigbee2mqtt.io/guide/configuration/adapter-settings.html

### Mosquitto / MQTT
- https://mosquitto.org/documentation/
- https://mosquitto.org/man/mosquitto-conf-5.html
- https://mosquitto.org/documentation/authentication-methods/
- https://hub.docker.com/_/eclipse-mosquitto/

### Android ADB / BlueZ
- https://developer.android.com/tools/adb
- https://developer.android.com/tools/releases/platform-tools
- https://www.bluez.org/
- https://manpages.debian.org/unstable/bluez/bluetoothctl.1.en.html

---

## Secondary references (patterns only)
- https://github.com/home-assistant/core
- https://github.com/docker/compose
- https://github.com/Koenkk/zigbee2mqtt
- https://github.com/zigbee2mqtt/hassio-zigbee2mqtt
- https://github.com/eclipse-mosquitto/mosquitto
- https://github.com/m0wlheld/homeassistant-zigbee2mqtt
- https://github.com/snakuzzo/homeassistant-stack

---

## Agent workflow rules
1. Keep diffs minimal and reversible.
2. Justify behavior/security changes with official references.
3. If behavior/config changes, update `README.md` + relevant `*.example` files.
4. If work changes completion state or roadmap, update `FINALIZATION_CHECKLIST.md`.
5. Never commit secrets or generated credentials.
