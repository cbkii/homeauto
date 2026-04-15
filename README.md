# homeauto stack

Production-lean Home Assistant Container stack for Debian 12 / Raspberry Pi OS Bookworm.
Managed with Docker Compose.

## Services

| Service | Description | Default port |
|---|---|---|
| Home Assistant | Smart home controller | 8123 |
| Mosquitto | MQTT broker (auth required) | 1883 |
| Zigbee2MQTT | Zigbee coordinator bridge + UI | 8080 |

**Host services (systemd):**
- `ha-action-bridge` — host-side MQTT subscriber that executes ADB and Bluetooth helper scripts on behalf of Home Assistant

## Quick start

```bash
# 1. Configure
cp .env.example .env && nano .env
./system/zigbee-discover.sh   # get ZIGBEE_DEVICE path

# 2. Install
sudo ./install.sh

# 3. Open
http://<host-ip>:8123
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for the full setup and maintenance guide.

## Documentation

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How components fit together, action bridge design |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Install, update, uninstall, backup, day-to-day ops |
| [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) | All configuration files and variables |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [docs/SUPPORT_BOUNDARIES.md](docs/SUPPORT_BOUNDARIES.md) | Supported platforms, known limitations, HA Container vs HA OS |
| [docs/SMOKE_TEST_RUNBOOK.md](docs/SMOKE_TEST_RUNBOOK.md) | Release smoke testing procedure |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [FINALIZATION_CHECKLIST.md](FINALIZATION_CHECKLIST.md) | Implementation status, roadmap, release readiness |

## Key design decisions

- **Home Assistant Container** (not HA OS / Supervisor) — no add-on store.
- **Host networking** (`network_mode: host`) for all containers — required for
  LAN multicast and simplifies MQTT addressing.
- **MQTT-based action bridge** — ADB and Bluetooth helper scripts run on the
  host (not inside the HA container) and are triggered via MQTT publish.
  See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for why this is necessary.
- **Auth required** — Mosquitto requires credentials; no anonymous access.
- **No WAN exposure** — no reverse proxy or port-forwarding automation included.
- **Stable Zigbee path** — coordinator mapped via `/dev/serial/by-id/…` to
  avoid symlink churn.

## Prerequisites

- Debian 12 / Raspberry Pi OS Bookworm (64-bit)
- Internet access for package and image pulls
- User with `sudo` access
- Zigbee coordinator connected (if using Zigbee2MQTT)

## Helper actions (ADB / Bluetooth)

Helper scripts are **not** callable via HA `shell_command` — `shell_command`
runs inside the container, where `adb` and `bluetoothctl` are not available.
Instead, Home Assistant publishes MQTT messages and the host-side
`ha-action-bridge` service executes the scripts.

From an HA automation:

```yaml
action:
  - action: mqtt.publish
    data:
      topic: ha/actions/tv_power
      payload: "{{ states('input_text.android_tv_ip') }}"
```

Full topic/payload schema: [docs/ARCHITECTURE.md § MQTT action topics](docs/ARCHITECTURE.md#mqtt-action-topics-and-payloads)

## Security defaults

- MQTT requires authentication — `allow_anonymous false`.
- ADB scripts enforce RFC1918 LAN-only IP targets.
- Bluetooth scripts disable discoverable/pairable modes after use.
- No internet-facing services or port forwarding configured.

## Quality gates

```bash
./scripts/qa.sh
```

Runs `shellcheck` across all `*.sh` files and validates `docker compose config`.

## Status and roadmap

See [FINALIZATION_CHECKLIST.md](FINALIZATION_CHECKLIST.md).

