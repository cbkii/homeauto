# AGENTS.md

## Purpose
This repo provides a production-lean Home Assistant stack on **Raspberry Pi OS / Debian Bookworm** using **Docker Compose**:
- Home Assistant (Container)
- Mosquitto (MQTT broker)
- Zigbee2MQTT (Zigbee bridge; Tuya Zigbee-friendly)
- Android TV control via ADB (through HA integration + helper scripts)
- Bluetooth control via host BlueZ + helper scripts

Agents (Copilot, Codex, etc.) must optimise for **reliability**, **idempotence**, **least privilege**, and **easy uninstall/rollback**.

---

## Scope and non-goals
### In scope
- Maintain a Docker Compose stack that works on Debian 12 / Raspberry Pi OS Bookworm (64-bit)
- Zigbee via Zigbee2MQTT
- MQTT via Mosquitto with authentication
- Android TV control via HA integrations + safe host helper scripts
- Bluetooth support for HA Container (host BlueZ + D-Bus mount) and optional host helper scripts

### Not in scope (unless explicitly requested)
- Home Assistant OS / Supervisor / Add-ons
- Cloud dependencies beyond what a chosen integration requires (e.g. Tuya cloud)
- VLAN/mDNS gateway configuration (document it, don’t “solve” it in code)
- Automatically opening firewall ports or exposing services to WAN

---

## Repo invariants (do not break)
1. **Install must be safe to re-run** (idempotent). No partial installs that require manual cleanup.
2. **Uninstall must reverse install** (containers removed; repo data optionally preserved; no lingering host mutations).
3. **Secrets never committed**:
   - `.env` must be user-provided (only `.env.example` shipped)
   - HA secrets belong in `ha/secrets.yaml` (ship `secrets.yaml.example`)
4. **No hard-coded device paths** when discoverable:
   - Zigbee uses `/dev/serial/by-id/...` selection
5. Prefer **least privilege**:
   - Avoid `privileged: true` unless justified and documented.

---

## Stack overview and files
- `docker-compose.yml` — services, host network mode, mounts
- `install.sh` — installs host deps, validates env, bootstraps configs, starts containers
- `update.sh` — pulls images + restarts
- `uninstall.sh` — stops stack and removes installed artefacts safely
- `system/zigbee-discover.sh` — interactive chooser for `/dev/serial/by-id/*`
- `ha/` — Home Assistant config (minimal defaults; integrations via UI where possible)
- `zigbee2mqtt/` — Zigbee2MQTT `configuration.yaml`
- `mosquitto/` — Mosquitto config + password file

---

## Operational guidance for agents

### Home Assistant Container constraints
Home Assistant Container is **not** HA OS. No add-ons. Use:
- separate containers (Mosquitto, Zigbee2MQTT, optional Node-RED if ever added)
- HA UI integrations + YAML where appropriate

Container docs, updates, backups:
- Use HA “Common tasks - Container” guidance for update/backup patterns.

### Networking expectations
- HA typically uses `network_mode: host` so discovery (mDNS/SSDP) and local integrations work reliably.
- Do **not** add port forwards or expose HA/MQTT to the internet in this repo.

### Zigbee requirements
- Zigbee coordinator path must be stable (prefer `/dev/serial/by-id/*`).
- Zigbee2MQTT `configuration.yaml` must be writable (frontend may update it).
- Document recommended coordinator firmware updates; don’t automate firmware flashing in this repo.

### Mosquitto requirements
- Always default to authenticated access:
  - `allow_anonymous false`
  - `password_file ...`
- Note: Mosquitto is tightening password file ownership expectations; ensure generated password files are owned by root when required (or follow upstream guidance).

### Bluetooth in HA Container (must be explicit)
For HA Container to use Bluetooth:
- Host must run **BlueZ**
- Container must have access to D-Bus socket (typically `/run/dbus`)
- HA Bluetooth docs recommend adding `cap_add: NET_ADMIN, NET_RAW` and mounting D-Bus.

Agents must:
- Document why privileges/capabilities are needed
- Prefer `cap_add` over `privileged`, and only use `privileged: true` if required for specific adapters/hosts

### Android TV / ADB
- Use Home Assistant’s official Android TV integration docs for setup and pairing/authorisation behaviour.
- Helper scripts must:
  - refuse non-LAN targets by default (RFC1918 only)
  - avoid interactive prompts
  - never weaken ADB security on the TV (e.g. don’t enable wide-open debugging modes)

---

## Security baseline (lite hardening)
Minimum expectations in this repo:
- MQTT requires credentials by default
- ADB scripts:
  - LAN-only target validation
  - no remote/wide-area assumptions
- Bluetooth scripts:
  - not discoverable/pairable by default after initial pairing
- No service exposed to WAN by default (no reverse proxy, no port forward automation)
- Avoid baking secrets into git history

Optional hardening (document as guidance; don’t force without request):
- Local firewall rules (UFW/nftables) to restrict:
  - MQTT (1883) to LAN only
  - HA (8123) to LAN only
- Replace `privileged: true` with minimal `cap_add` where workable
- Use dedicated Linux users / groups for host helper scripts if running anything with elevated rights

---

## Quality gates (required)
Any PR/change should pass:
1. `shellcheck` on all `*.sh` scripts (no unquoted vars, no unsafe globs, etc.)
2. `docker compose config` validates (no invalid compose keys)
3. Install/uninstall smoke test on Debian 12 / Pi OS Bookworm:
   - install completes without prompts besides Zigbee selection
   - stack starts and health-checks are reasonable (containers running)
   - uninstall removes containers and installed files as documented

---

## Official documentation (primary sources)

### Home Assistant
- Docs index: https://www.home-assistant.io/docs/
- Linux install (Container section includes docker compose + device exposure): https://www.home-assistant.io/installation/linux/
- Raspberry Pi (advanced “Container” path): https://www.home-assistant.io/installation/raspberrypi-other/
- Common tasks (Container): https://www.home-assistant.io/common-tasks/container/
- MQTT integration: https://www.home-assistant.io/integrations/mqtt/
- Bluetooth integration (includes Container requirements: BlueZ, D-Bus mount, capabilities): https://www.home-assistant.io/integrations/bluetooth/
- Android Debug Bridge (Android TV integration): https://www.home-assistant.io/integrations/androidtv/
- Android TV Remote (separate integration): https://www.home-assistant.io/integrations/androidtv_remote/
- Tuya integration: https://www.home-assistant.io/integrations/tuya/

### Docker / Compose
- Install Docker Engine on Debian (Bookworm supported): https://docs.docker.com/engine/install/debian/
- Docker Compose overview: https://docs.docker.com/compose/
- Compose file reference / specification: https://docs.docker.com/reference/compose-file/
- Compose services reference: https://docs.docker.com/reference/compose-file/services/

### Zigbee2MQTT
- Docs home: https://www.zigbee2mqtt.io/
- Docker install guide: https://www.zigbee2mqtt.io/guide/installation/02_docker.html
- Configuration overview: https://www.zigbee2mqtt.io/guide/configuration/
- Adapter settings (incl. adapter discovery notes): https://www.zigbee2mqtt.io/guide/configuration/adapter-settings.html
- Zigbee2MQTT GitHub: https://github.com/Koenkk/zigbee2mqtt
- Official HA add-on repo (useful reference for patterns even if we’re not HA OS): https://github.com/zigbee2mqtt/hassio-zigbee2mqtt

### Mosquitto / MQTT
- Mosquitto project home: https://mosquitto.org/
- Mosquitto documentation index: https://mosquitto.org/documentation/
- `mosquitto.conf` man page: https://mosquitto.org/man/mosquitto-conf-5.html
- Authentication methods: https://mosquitto.org/documentation/authentication-methods/
- Eclipse Mosquitto GitHub: https://github.com/eclipse-mosquitto/mosquitto
- Official Docker image: https://hub.docker.com/_/eclipse-mosquitto

### Android ADB (official Android docs)
- Android Debug Bridge (adb): https://developer.android.com/tools/adb
- Platform-tools release notes (adb lives here): https://developer.android.com/tools/releases/platform-tools
- Developer options (enabling USB debugging): https://developer.android.com/studio/debug/dev-options

### Bluetooth / BlueZ
- BlueZ project (Linux Bluetooth stack): https://www.bluez.org/
- `bluetoothctl` man page (Debian): https://manpages.debian.org/unstable/bluez/bluetoothctl.1.en.html

### Tuya (official)
- Tuya developer guide for HA Tuya integration (limitations and setup details): https://developer.tuya.com/en/docs/iot/Home-assistant-tuya-intergration
- Tuya HA integration repo (official): https://github.com/tuya/tuya-home-assistant

---

## Battle-tested repos / reference implementations (secondary sources)
Use these for patterns and “known good” approaches, not as authoritative replacements for official docs:
- Home Assistant core: https://github.com/home-assistant/core
- Docker Compose (upstream): https://github.com/docker/compose
- Docker Compose sample patterns (dev-focused; don’t copy blindly to prod): https://github.com/docker/awesome-compose
- Zigbee2MQTT core repo: https://github.com/Koenkk/zigbee2mqtt
- Mosquitto core repo: https://github.com/eclipse-mosquitto/mosquitto
- Official Mosquitto Docker image: https://hub.docker.com/_/eclipse-mosquitto
- Community stack examples (use with caution; validate against official docs):
  - https://github.com/m0wlheld/homeassistant-zigbee2mqtt
  - https://github.com/snakuzzo/homeassistant-stack

---

## Agent workflow (how to propose changes)
When modifying the repo:
1. State the goal and the user-facing effect.
2. Link to the official doc section that justifies the change.
3. Keep diffs minimal; no refactors “for style” without a concrete reliability benefit.
4. Update README + `.env.example` if behaviour/config changes.
5. Ensure uninstall reversibility if you modify host state.

---

## Notes / Known sharp edges (document, don’t hide)
- Bluetooth in containers is sensitive to host/kernel/BlueZ versions; follow HA Bluetooth docs and prefer capabilities over privileged mode.
- Zigbee coordinators can appear as `/dev/ttyUSB*` or `/dev/ttyACM*`; always anchor via `/dev/serial/by-id/`.
- Zigbee2MQTT frontend can rewrite `configuration.yaml`; ensure permissions match that behaviour.
- Mosquitto password file ownership expectations may tighten; keep an eye on upstream release notes/issues.


