# Support Boundaries

This document defines what the homeauto stack supports, what it explicitly does
not support, and what is out of scope for the homelab-stable v1 baseline.

---

## Supported platform

| Requirement | Detail |
|---|---|
| OS | Debian 12 (Bookworm) · Raspberry Pi OS Bookworm 64-bit |
| Architecture | x86-64 · arm64 (Raspberry Pi 4 / 5) |
| Docker | Docker CE / `docker.io` package with Compose plugin |
| Install type | Docker Compose (not HA OS, not Supervisor) |

Other Linux distributions may work but are not tested and not supported.
32-bit ARM (`armhf`) is not tested.

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
| Zigbee2MQTT | `koenkk/zigbee2mqtt:latest` | Tracks latest Z2M release |

**Version pinning policy:**
The stack currently tracks `stable` / `2` / `latest` tags, which are re-pulled
on every `./update.sh --restart` run.  This is appropriate for a homelab where
staying current is preferred over reproducibility.

For a more reproducible setup, pin to specific release tags
(e.g. `koenkk/zigbee2mqtt:1.42.0`) and update them deliberately.
Digest pinning (`image@sha256:…`) is not required for this use case and is
deferred to post-v1 hardening.

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

No automated backup or restore tooling is included in v1 beyond
`scripts/stack/backup.sh`, which creates a local tar archive.
Off-site backup, encryption, and scheduled runs are out of scope.
See `docs/OPERATIONS.md § Backup and restore` for the manual procedure.

### Container privilege

`homeassistant` runs with `privileged: true` to support hardware integrations
(D-Bus, USB, Bluetooth) in this phase.  Reducing to fine-grained capabilities
is a post-v1 hardening task listed in `FINALIZATION_CHECKLIST.md` Phase C.

---

## Out of scope (v1)

The following items are intentionally deferred or excluded:

- HA OS / Supervisor workflows
- WAN exposure (reverse proxy, DDNS, port forwarding)
- VLAN/mDNS routing automation
- Automated Zigbee coordinator firmware flashing
- TLS for MQTT (internal LAN use; out of scope for homelab-stable baseline)
- Firewall automation (host firewall is the operator's responsibility)
- Image digest pinning / reproducible builds
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
