# Q8B / Debian 13 development target

The Q8B is an application commissioning target, **not runtime qualified**.
See [Q8B commissioning](platforms/Q8B.md) and the dated evidence ledger.
The sections below describe the previous Pi release. They remain in force for
Pi deployments, including the Pi 5 / Trixie compatibility gate; the Q8B runbook
adds Q8B-specific gates and supersedes none of them. No kernel/firmware promotion
is implied.

# Support Boundaries

This document defines what the homeauto stack supports, what it explicitly does
not support, and what is out of scope for the homelab-stable v1 baseline.

---

## Supported platform

| Requirement | Detail |
|---|---|
| OS | Debian 12 (Bookworm) · Raspberry Pi OS Bookworm 64-bit |
| OS (compatibility candidate) | Debian 13 (Trixie) · Raspberry Pi OS Trixie 64-bit |
| Architecture | x86-64 · arm64 (Raspberry Pi 4 / 5) |
| Docker | Docker CE / `docker.io` package with Compose plugin |
| Install type | Docker Compose (not HA OS, not Supervisor) |

Other Linux distributions may work but are not tested and not supported.
32-bit ARM (`armhf`) is not tested.

**Decision note (2026-05-25):** Trixie is now a compatibility candidate for
Raspberry Pi 5. It is supported for pilot/homelab use when full smoke evidence
exists for your target host; production sign-off requires local validation.

## Raspberry Pi 5 + Debian Trixie compatibility gate

Minimum expectations for pilot support:

| Area | Minimum expectation |
|---|---|
| Kernel | Debian/Pi OS Trixie default kernel for arm64 on Pi 5 (reported by `uname -r`) |
| Docker Engine | Docker 24+ (`docker --version`) |
| Compose plugin | Compose v2.20+ (`docker compose version`) |
| Install preflight | `sudo ./install.sh --preflight-only` passes |
| QA gate | `./scripts/qa.sh` passes |
| Smoke gate | `./scripts/smoke/run_release_smoke.sh --mode verify` passes; full mode required before release sign-off |

Rollback policy for Trixie regressions:
- Pin service images using `docker-compose.pinned.yml`.
- If host-level regressions remain, rollback host OS to Bookworm baseline and
  restore from backup.

## Healthcheck command dependencies

Healthchecks rely on utilities present in each upstream image. If image
maintainers remove these binaries, service health can fail even when containers
start.

| Service | Healthcheck command dependency | Typical failure symptom |
|---|---|---|
| mariadb | `mariadb-admin` | DB container loops unhealthy; HA waits on SQL |
| mosquitto | `mosquitto_pub` | MQTT service remains unhealthy; dependent services wait |
| homeassistant | `curl` | HA marked unhealthy despite running UI |
| esphome | `curl` | ESPHome marked unhealthy despite dashboard accessibility |
| nodered | `curl` | Node-RED marked unhealthy despite editor availability |
| zigbee2mqtt | `wget` | Z2M unhealthy; may also indicate missing coordinator |

---

## Home Assistant Container vs HA OS

This repo uses **Home Assistant Container** — the plain Docker image.
This is intentionally different from Home Assistant OS (HA OS / HAOS).

| Feature | HA Container (this repo) | HA OS |
|---|---|---|
| Add-on store | ❌ Not available | ✅ Available |
| Supervisor | ❌ Not available | ✅ Available |
| Managed updates via UI | ❌ Use `./update.sh` | ✅ Built-in |
| Custom integrations (HACS) | ✅ Manual install into `ha/custom_components/` | ✅ Via HACS |
| Full config access | ✅ Direct file access | ✅ With SSH |
| Docker Compose control | ✅ Full control | ❌ Managed by HA OS |
| Bluetooth (host) | ✅ Via D-Bus mount + `privileged: true` | ✅ Native |
| ADB helpers | ✅ Via ha-action-bridge | ⚠️ Possible but different path |

Official HA Container docs:
https://www.home-assistant.io/installation/linux/#install-home-assistant-container

---

## Tested image versions

| Service | Image tag | Policy |
|---|---|---|
| Home Assistant | `ghcr.io/home-assistant/home-assistant:stable` | Tracks current stable release |
| Mosquitto | `eclipse-mosquitto:2` | Tracks latest Mosquitto 2.x |
| Zigbee2MQTT | `koenkk/zigbee2mqtt:2` | Tracks Z2M 2.x series (major-pinned) |
| ESPHome | `ghcr.io/esphome/esphome:stable` | Tracks current stable release |
| Node-RED | `nodered/node-red:4` | Tracks Node-RED v4 major line |
| MariaDB | `mariadb:11` | Tracks MariaDB 11.x major line |

**Version pinning policy:**
The stack currently tracks `stable` / `2` / `2` major tags, which are re-pulled
on every `./update.sh --restart` run. This balances homelab currency with
reduced surprise from unconstrained `latest` pulls.

For a more reproducible setup, pin to specific release tags
(e.g. `koenkk/zigbee2mqtt:2.9.2`) and update them deliberately.
Digest pinning (`image@sha256:…`) is not required for this use case and adds
maintenance overhead (manual digest updates on each release).

**Recommendation:** use explicit version tags (not `:latest`) if you want
controlled, deliberate upgrades without running `./update.sh`.

---

## Service compatibility matrix

Core automation services (HA, Mosquitto, Zigbee2MQTT) communicate via MQTT.
Additional services are independent:
- MariaDB is used by HA recorder (`recorder.db_url`)
- ESPHome exposes a dashboard/API service for firmware management
- Node-RED integrates with HA/MQTT via flows

Compatibility is therefore mostly loose at the message bus level (MQTT), with
MariaDB compatibility governed by HA recorder SQL backend support.

| HA version | Mosquitto 2.x | Zigbee2MQTT | Notes |
|---|---|---|---|
| 2022.6+ | ✅ | 1.26+ | MQTT entity model stabilised |
| 2023.x | ✅ | 1.30+ | Device triggers + event entities added |
| 2024.x | ✅ | 1.36+ | Recommended combination |
| 2025.x (stable) | ✅ | 2.0+ | Supported (legacy stable line) |
| 2026.x (stable) | ✅ | 2.8+ | Current tracked combination |

**Breaking changes to watch for:**
- Z2M 2.x introduced configuration and migration changes from late 1.x lines.
  Always check the [Z2M release notes](https://github.com/Koenkk/zigbee2mqtt/releases)
  before updating.
- HA MQTT integration changes are announced in
  [HA release notes](https://www.home-assistant.io/blog/).
- Mosquitto 2.x uses auth-required config by default — no breaking changes
  expected within the 2.x series.

**Update guidance:** run `./update.sh --restart` to pull and apply all updates.
For major Z2M releases, check migration notes before updating.  Roll back with:
```bash
docker compose pull zigbee2mqtt   # pull specific tag if needed
docker compose up -d zigbee2mqtt
```

---

## Known limitations

### Hardware validation

The following features require real hardware and cannot be validated in CI:

| Feature | Required hardware | Status |
|---|---|---|
| Zigbee coordinator | USB Zigbee adapter (e.g. Sonoff Zigbee 3.0, HUSBZB-1) | ⚠️ Blocked: CI only |
| ADB / Android TV control | LAN-connected Android TV with ADB enabled | ⚠️ Blocked: CI only |
| Bluetooth pair/trust/connect | BT adapter + target device | ⚠️ Blocked: CI only |
| ha-action-bridge end-to-end | Running MQTT broker + ADB/BT hardware | ⚠️ Blocked: CI only |

See `FINALIZATION_CHECKLIST.md` §4 for full blocker details and workarounds.

### No WAN exposure automation

The stack does not configure reverse proxies, dynamic DNS, or port forwarding.
All services are LAN-only by default.  WAN access is explicitly out of scope.

### No HA Supervisor / add-on store

The HA Container image does not include the Supervisor.  Add-ons (e.g. ESPHome,
Node-RED, AppDaemon) cannot be installed via the HA UI.  Equivalent
functionality requires separate Docker containers or host-level installation.

### Backup and restore

Local backup tooling is available via `scripts/stack/backup.sh` (manual, on-demand)
and `scripts/stack/backup-schedule-install.sh` (opt-in systemd timer for daily automated
backups).  Both write timestamped archives to `./backups/` by default.

Off-site backup and encryption are out of scope but the operations guide includes
rsync and rclone templates.  See `docs/OPERATIONS.md § Backup and restore`.

### Container privilege

`homeassistant` runs with `privileged: true` as the default.  This is required
in the general case for HA Container on a homelab because:

- **Bluetooth** — HA needs D-Bus access and certain kernel capabilities (e.g.
  `CAP_NET_ADMIN`) to manage Bluetooth sockets.  Even with `/run/dbus` mounted
  read-only, some HA Bluetooth operations require additional privilege.
- **USB / hardware integrations** — some HA integrations probe hardware devices
  (e.g. USB energy meters, custom hardware).  Privilege is the safest default.
- **Network** — `CAP_NET_ADMIN` and `CAP_NET_RAW` are needed by HA for mDNS /
  multicast discovery and raw socket operations.

#### Phase C least-privilege alternative (opt-in, experimental)

A capabilities-based alternative is provided as a commented block in
`docker-compose.yml`.  To try it, replace `privileged: true` with:

```yaml
privileged: false
cap_add:
  - NET_ADMIN
  - NET_RAW
  - SYS_RAWIO
security_opt:
  - no-new-privileges:true
```

**Caveats:**
- Not all HA integrations are guaranteed to work.  In particular, some USB
  integrations and certain HA core features may silently fail or produce
  misleading errors without full privilege.
- Verify that Bluetooth pairing, your Zigbee integration, and any active HA
  integrations still work after switching.
- If any integration stops working, restore `privileged: true` and investigate
  which capability is needed before filing an issue.
- See `FINALIZATION_CHECKLIST.md` Phase C for validation status.

Rollback: set `privileged: true` and run `docker compose up -d --force-recreate homeassistant`.

---

## Out of scope (v1)

The following items are intentionally deferred or excluded:

- HA OS / Supervisor workflows
- WAN exposure (reverse proxy, DDNS, port forwarding)
- VLAN/mDNS routing automation
- Automated Zigbee coordinator firmware flashing
- TLS for MQTT (internal LAN use; out of scope for homelab-stable baseline)
- Firewall automation (opt-in helper: `scripts/security/firewall-setup.sh`; not applied by default)
- Image digest pinning / reproducible builds (explicit version tags supported; see image policy above)
- Kubernetes or Swarm orchestration
- Multi-host or multi-instance HA setups

---

## Reporting issues

This is a personal homelab baseline, not a supported product.  Issues and
pull requests are welcome.  When reporting, please include:

- Host OS and architecture (`uname -a`)
- Docker version (`docker --version`)
- The relevant log output (`docker compose logs <service>`)
- Whether the issue is hardware-dependent (Zigbee, ADB, BT)
