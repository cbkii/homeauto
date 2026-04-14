# Homeauto Finalization Checklist

Authoritative tracker for implementation status, release readiness, roadmap,
and completion evidence.

_Last updated: 2026-04-14._

---

## 1) Implementation status map

| ID | Area | Requirement / Feature | Status | Evidence (files) | Next step |
|---|---|---|---|---|---|
| S1 | Scope | Homelab-stable baseline target | ✅ Done | README + AGENTS alignment | Maintain |
| S2 | Security | HA `privileged: true` (current phase) | ✅ Done | `docker-compose.yml` | Revisit post-v1 |
| S3 | MQTT | Auth required (`allow_anonymous false`) | ✅ Done | `mosquitto/config/mosquitto.conf` | Add runtime smoke evidence |
| S4 | Zigbee | Stable adapter path via `/dev/serial/by-id/` | ✅ Done | `system/zigbee-discover.sh`, `.env.example` | Capture hardware smoke logs |
| S5 | Zigbee | In-container device mapping (`/dev/zigbee`) | ✅ Done | `docker-compose.yml`, `zigbee2mqtt/configuration.yaml` | Validate on target coordinator |
| S6 | Install | Idempotent install + env validation | ✅ Done | `install.sh` | Runtime smoke evidence |
| S7 | Update | Pull/restart controls + upgrade helper | ✅ Done | `update.sh`, `scripts/stack/upgrade.sh` | Validate upgrade path on target |
| S8 | Uninstall | Preserve-by-default + explicit purge | ✅ Done | `uninstall.sh` | Smoke-test preserve/purge paths |
| S9 | Secrets | Example-based secret handling | ✅ Done | `.env.example`, `ha/secrets.yaml.example`, `.gitignore` | — |
| S10 | ADB | LAN-only helper controls (power/home/back/launch) | ✅ Done | `scripts/adb/` | On-device behavioral smoke |
| S11 | Bluetooth | Connect + pair/trust helper workflow | ✅ Done | `scripts/bt/` | Validate against real adapter |
| S12 | QA | Shell + compose QA script | ✅ Done | `scripts/qa.sh` | Ensure tools in CI runner image |
| S13 | CI | GitHub Actions QA workflow | ✅ Done | `.github/workflows/ci.yml` | Confirm green run |
| S14 | Docs | Operator/developer documentation | ✅ Done | `README.md`, `docs/` | Maintain with behavior changes |
| S15 | Agent enablement | AGENTS + GitHub instruction corpus | ✅ Done | `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/` | Keep in sync |
| **S16** | **Action bridge** | **Fix broken shell_command: host-side MQTT action bridge** | ✅ Done | `scripts/ha-action-bridge/`, `install.sh`, `uninstall.sh`, `ha/configuration.yaml` | Runtime smoke evidence |
| S17 | Architecture | Architecture document | ✅ Done | `docs/ARCHITECTURE.md` | Maintain with changes |
| S18 | Operations | Operations and troubleshooting docs | ✅ Done | `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md`, `docs/CONFIG_REFERENCE.md` | Maintain with changes |
| S19 | Release proof | Debian/Pi full install→run→uninstall smoke | ⚠️ Blocked | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md` | Run on real Debian 12/Pi host with Docker + hardware |
| S20 | Release proof | Final DoD sign-off | ⏳ Pending | — | Close after S19 + QA evidence |
| S21 | Verification tooling | Release smoke automation + runbook | ✅ Done | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md` | Use for S19 evidence |

Legend: ✅ Done, ⏳ Pending, ⚠️ Blocked (reason stated in next-step), ❌ Not started.

---

## 2) Roadmap

### Phase A — Verification on target runtime
- [x] Scripted smoke harness + runbook.
- [x] Non-destructive verify mode run in CI; daemon/hardware limitations documented.
- [ ] Run full lifecycle smoke on Debian 12 / Pi OS Bookworm target host.
- [ ] Confirm containers healthy (`homeassistant`, `mosquitto`, `zigbee2mqtt`).
- [ ] Validate Zigbee adapter operation with a real coordinator.
- [ ] Validate ADB helper scripts against a real LAN Android TV.
- [ ] Validate Bluetooth pair/trust/connect scripts against a real device.
- [ ] Validate `ha-action-bridge` service start, MQTT dispatch, and script execution.

### Phase B — Evidence and release readiness
- [ ] Capture QA evidence (`./scripts/qa.sh` output + CI run link).
- [ ] Capture install/update/uninstall evidence (commands + outputs).
- [ ] Capture `ha-action-bridge` end-to-end dispatch evidence.
- [ ] Close S19/S20 with evidence references.

### Phase C — Post-v1 hardening backlog (deferred)
- [ ] Evaluate replacing `privileged: true` with fine-grained capabilities.
- [ ] Optional firewall helper tooling (opt-in by policy).
- [ ] Optional backup/restore helper scripts.
- [ ] Consider image version pinning policy vs `stable`/`latest` tags.
- [ ] Evaluate support boundaries and document HA/Z2M version compatibility matrix.

---

## 3) Decision log

| Decision | Rationale | Locked in |
|---|---|---|
| Home Assistant Container (not HA OS) | No Supervisor dependency; simpler Docker Compose model | Yes |
| Host network mode for all containers | Required for mDNS/multicast LAN discovery | Yes |
| MQTT auth required | Security baseline; no anonymous access | Yes |
| MQTT-based action bridge for ADB/BT | `shell_command` runs in container; `adb`/`bluetoothctl` not in HA image | Yes |
| Uninstall preserves data by default | Safe default; explicit `--purge-data` for removal | Yes |
| `privileged: true` for HA | Required for some integrations in this phase | Current phase only |
| MQTT password rotation: explicit/opt-in | Avoid accidental service disruption | Yes |
| No WAN exposure automation | Out of scope for homelab-stable baseline | Yes |
| Stable Zigbee path (`/dev/serial/by-id/`) | Avoids tty symlink instability across reboots | Yes |

---

## 4) Known gaps and blockers

| Item | Status | Blocker | Workaround / plan |
|---|---|---|---|
| Hardware smoke evidence | ⚠️ Blocked | Requires real Debian 12/Pi host with Docker daemon and physical devices | Run `scripts/smoke/run_release_smoke.sh --mode full` on target |
| `ha-action-bridge` MQTT end-to-end test | ⚠️ Blocked | Requires running MQTT broker + ADB/BT hardware | Test manually after install |
| HA integration validation (MQTT/BT/Z2M) | ⚠️ Blocked | Requires running HA instance | Validate on target after install |
| Backup/restore automation | ❌ Not started | Deferred to Phase C | Document manually in OPERATIONS.md |
| Image version pinning | ❌ Not started | Deferred to Phase C | Currently using `stable`/`:2`/`:latest` tags |

---

## 5) Completion evidence log

| Date | Change | Evidence |
|---|---|---|
| 2026-04-14 | Initial finalization baseline | repo commits |
| 2026-04-14 | Agent/developer instruction corpus | `AGENTS.md` + `.github/instructions/` |
| 2026-04-14 | Smoke verification tooling added | `scripts/smoke/run_release_smoke.sh` + `docs/SMOKE_TEST_RUNBOOK.md` |
| 2026-04-14 | Environment smoke attempt; daemon/hardware blockers identified | `artifacts/smoke-report-*.md` |
| 2026-04-14 | **Fix broken shell_command**: MQTT action bridge implemented | `scripts/ha-action-bridge/`, updated `install.sh`/`uninstall.sh`/`ha/configuration.yaml` |
| 2026-04-14 | Architecture + operations + troubleshooting + config reference docs added | `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md`, `docs/CONFIG_REFERENCE.md` |

---

## 6) File ownership

| File | Purpose |
|---|---|
| `FINALIZATION_CHECKLIST.md` | Status map + roadmap + decisions + evidence log |
| `AGENTS.md` | Contributor/agent operating rules, invariants, official references |
| `.github/copilot-instructions.md` | Concise Copilot-specific guardrails |
| `.github/instructions/DEVELOPERS.md` | PR hygiene, contribution criteria |
| `.github/instructions/SOURCES.md` | Curated official reference links |
| `docs/ARCHITECTURE.md` | Runtime component diagram and action bridge design |
| `docs/OPERATIONS.md` | Install/update/uninstall and day-to-day ops |
| `docs/CONFIG_REFERENCE.md` | All config files and variables |
| `docs/TROUBLESHOOTING.md` | Common problems and fixes |
| `docs/SMOKE_TEST_RUNBOOK.md` | Release verification procedure |
