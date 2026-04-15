# Homeauto Finalization Checklist

Authoritative tracker for implementation status, release readiness, roadmap,
and completion evidence.

_Last updated: 2026-04-15 (v1.0.0 release finalization pass)._

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
| S12 | QA | Shell + compose QA script | ✅ Done | `scripts/qa.sh` | — |
| S13 | CI | GitHub Actions QA workflow | ✅ Done | `.github/workflows/ci.yml` | Locally verified clean 2026-04-15; compose config output now via `tee` for log visibility |
| S14 | Docs | Operator/developer documentation | ✅ Done | `README.md`, `docs/` | Maintain with behavior changes |
| S15 | Agent enablement | AGENTS + GitHub instruction corpus | ✅ Done | `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/` | Keep in sync |
| **S16** | **Action bridge** | **Fix broken shell_command: host-side MQTT action bridge** | ✅ Done | `scripts/ha-action-bridge/`, `install.sh`, `uninstall.sh`, `ha/configuration.yaml` | Runtime smoke evidence |
| S17 | Architecture | Architecture document | ✅ Done | `docs/ARCHITECTURE.md` | Maintain with changes |
| S18 | Operations | Operations and troubleshooting docs | ✅ Done | `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md`, `docs/CONFIG_REFERENCE.md` | Maintain with changes |
| S19 | Release proof | Debian/Pi full install→run→uninstall smoke | ⚠️ Blocked | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md` | Run on real Debian 12/Pi host with Docker + hardware |
| S20 | Release proof | Final DoD sign-off | ⏳ Pending | — | Close after S19 + QA evidence |
| S21 | Verification tooling | Release smoke automation + runbook | ✅ Done | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md` | Use for S19 evidence |
| S22 | Compose | Healthchecks + `depends_on: service_healthy` | ✅ Done | `docker-compose.yml` | Validate on target host |
| S23 | CI | Artifact upload (QA output + compose config) | ✅ Done | `.github/workflows/ci.yml` | Check workflow artifacts in Actions |
| S24 | CI | Dependency review workflow | ✅ Done | `.github/workflows/dependency-review.yml` | Review on next PR |
| S25 | Ops | Backup helper script | ✅ Done | `scripts/stack/backup.sh` (covers ha/, zigbee2mqtt/, mosquitto/, esphome/, nodered/, mariadb/), `docs/OPERATIONS.md` | Validate on target |
| S26 | Docs | Support boundaries + version policy | ✅ Done | `docs/SUPPORT_BOUNDARIES.md` | Maintain |
| S27 | Release | CHANGELOG | ✅ Done | `CHANGELOG.md` | Update on each release |
| S28 | QA | `qa.sh` portability: replace `rg` with `find` | ✅ Done | `scripts/qa.sh` | — |
| S29 | Security | Privilege hardening: capabilities alternative documented | ✅ Done | `docker-compose.yml` (comment), `docs/SUPPORT_BOUNDARIES.md` | Hardware validation needed before switching default |
| S30 | Security | Firewall helper (opt-in) | ✅ Done | `scripts/security/firewall-setup.sh` (covers HA/MQTT/Z2M/ESPHome/Node-RED; MariaDB intentionally localhost-only), `docs/OPERATIONS.md` | Opt-in; no auto-run |
| S31 | Ops | Scheduled backup + off-site template | ✅ Done | `scripts/stack/backup-schedule-install.sh`, `backup-schedule-remove.sh`, `docs/OPERATIONS.md` | Opt-in; disabled by default |
| S32 | CI | GitHub Actions SHA pinning | ✅ Done | `.github/workflows/ci.yml`, `.github/workflows/dependency-review.yml` | All three actions pinned to commit SHAs with version comment |
| S33 | Docs | Service compatibility matrix (HA / Z2M / Mosquitto) | ✅ Done | `docs/SUPPORT_BOUNDARIES.md` | Update when major version bumps occur |
| S34 | Verification tooling | Smoke script bridge-dispatch evidence options | ✅ Done | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md` | Use on target host |
| S35 | Release policy | Image tag policy hardened (`zigbee2mqtt:2`) | ✅ Done | `docker-compose.yml`, `docs/SUPPORT_BOUNDARIES.md` | Revisit if major v3 migration needed |
| S36 | Stack expansion | ESPHome + Node-RED + MariaDB integrated in compose/install/uninstall/docs | ✅ Done | `docker-compose.yml`, `install.sh`, `uninstall.sh`, `docs/` | Runtime smoke evidence on target host |

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
- [x] Compose healthchecks implemented (`docker compose ps` shows health status).
- [x] CI artifact upload for QA output and resolved compose config.
- [x] Dependency review workflow added.
- [x] Backup helper script added (`scripts/stack/backup.sh`).
- [x] Support boundaries and version policy documented.
- [x] CHANGELOG started.
- [x] Capture QA evidence (`./scripts/qa.sh` output + smoke verify report; see Section 5, 2026-04-15 entries).
- [ ] Capture install/update/uninstall evidence (commands + outputs).
- [ ] Capture `ha-action-bridge` end-to-end dispatch evidence.
- [ ] Close S19/S20 with evidence references.

### Phase C — Post-v1 hardening backlog

- [x] Evaluate replacing `privileged: true` with fine-grained capabilities — documented analysis + commented alternative in `docker-compose.yml`; default kept as `privileged: true` pending hardware validation (see `docs/SUPPORT_BOUNDARIES.md §Container privilege`).
- [x] Optional firewall helper tooling — `scripts/security/firewall-setup.sh` added (opt-in, ufw-based, LAN-only baseline); documented in `docs/OPERATIONS.md`.
- [x] Scheduled backup automation — `scripts/stack/backup-schedule-install.sh` + `backup-schedule-remove.sh` added (opt-in systemd timer); off-site transfer template documented in `docs/OPERATIONS.md`.
- [x] Supply-chain hardening — GitHub Actions workflow steps pinned to commit SHAs (`actions/checkout@v4.2.2`, `upload-artifact@v4.6.2`, `dependency-review-action@v4.7.1`); image tag policy documented in `docs/SUPPORT_BOUNDARIES.md`.
- [x] HA/Z2M/Mosquitto compatibility matrix — added to `docs/SUPPORT_BOUNDARIES.md`.
- [x] Evaluate image version pinning to specific release tags or digests — decision applied: move from `zigbee2mqtt:latest` to major-pinned `zigbee2mqtt:2`; keep HA `stable` and Mosquitto `2` with documented operator override guidance.

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
| Z2M healthcheck in absence of coordinator | ⚠️ Expected | Z2M won't reach healthy state without a coordinator — healthcheck shows unhealthy | Expected; not a stack bug |
| Dependency review in CI (private repo) | ⚠️ Conditional | `actions/dependency-review-action` requires GitHub Advanced Security for private repos; free on public repos | Workflow now skips dependency review on private repositories without failing CI; enable GHAS + Dependency Graph to enforce |
| Backup scheduling / off-site transfer | ✅ Done | — | `scripts/stack/backup-schedule-install.sh` (opt-in systemd timer); off-site template in `docs/OPERATIONS.md` |
| Image digest pinning | ⏳ Operator decision | Deferred — explicit version tags supported; digest pinning adds maintenance overhead without proportionate benefit for a homelab | Documented in `docs/SUPPORT_BOUNDARIES.md`; operator can pin to specific tags in `docker-compose.yml` |
| GitHub Actions SHA pinning | ✅ Done | — | All workflow steps pinned to commit SHAs (S32) |

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
| 2026-04-14 | Release-readiness pass: healthchecks, CI artifacts, dependency review, backup helper, support boundaries, CHANGELOG, QA portability fix | `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/dependency-review.yml`, `scripts/stack/backup.sh`, `docs/SUPPORT_BOUNDARIES.md`, `CHANGELOG.md`, `scripts/qa.sh` |
| 2026-04-15 | CI workflow analysis: no actionable failures found; `docker compose config` output changed to `tee` pattern so errors appear in step log | `.github/workflows/ci.yml` |
| 2026-04-15 | QA gate local run: `./scripts/qa.sh` passes — shellcheck clean across all 14 scripts, `docker compose config` validates | local run (ubuntu-latest equivalent, Docker Compose v2.38.2, shellcheck 0.9.0) |
| 2026-04-15 | Smoke verify local run: `run_release_smoke.sh --mode verify` passes — uname, bash, docker, compose version, compose config, `docker compose ps` all pass | `artifacts/smoke-report-20260415T065027Z.md` (gitignored; captured in CI artifact on merge) |
| 2026-04-15 | Phase C hardening pass: privilege analysis + capabilities alternative, firewall helper, backup scheduler, GitHub Actions SHA pinning, compatibility matrix | `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/dependency-review.yml`, `scripts/security/firewall-setup.sh`, `scripts/stack/backup-schedule-install.sh`, `scripts/stack/backup-schedule-remove.sh`, `docs/SUPPORT_BOUNDARIES.md`, `docs/OPERATIONS.md` |
| 2026-04-15 | Dependency-review workflow hardened for private repos: non-failing skip notice when GHAS support is unavailable; manual dispatch and least-privilege permissions added | `.github/workflows/dependency-review.yml` |
| 2026-04-15 | Release tooling improvement pass: smoke script now supports bridge dispatch evidence (`--bridge-test`) and explicit uninstall mode (`--uninstall-mode preserve|purge`); runbook/operations updated | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md`, `docs/OPERATIONS.md` |
| 2026-04-15 | Image policy adjustment: Zigbee2MQTT moved from floating `latest` to major-pinned `:2`; support/version policy and compatibility matrix refreshed for 2026 baseline | `docker-compose.yml`, `docs/SUPPORT_BOUNDARIES.md` |
| 2026-04-15 | Service expansion pass: ESPHome (`:6052`), Node-RED (`:1880`), and MariaDB (`:3306`) added with healthchecks + persistent volumes; HA recorder wired to MariaDB via `recorder_db_url` secret; docs/config references updated | `docker-compose.yml`, `install.sh`, `uninstall.sh`, `ha/configuration.yaml.example`, `ha/secrets.yaml.example`, `README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/CONFIG_REFERENCE.md`, `docs/SUPPORT_BOUNDARIES.md` |
| 2026-04-15 | v1.0.0 finalization pass: `ha/configuration.yaml` updated to match example (recorder stanza added); `backup.sh` extended to cover esphome/, nodered/, mariadb/; `firewall-setup.sh` extended with ESPHome/Node-RED ports and MariaDB exclusion comment; `.env.example` misleading shell_command comment fixed; CHANGELOG cut to [1.0.0]; docs/OPERATIONS.md backup table and firewall section updated | `ha/configuration.yaml`, `scripts/stack/backup.sh`, `scripts/security/firewall-setup.sh`, `.env.example`, `CHANGELOG.md`, `docs/OPERATIONS.md` |

---

## 6) File ownership

| File | Purpose |
|---|---|
| `FINALIZATION_CHECKLIST.md` | Status map + roadmap + decisions + evidence log |
| `CHANGELOG.md` | Version history |
| `AGENTS.md` | Contributor/agent operating rules, invariants, official references |
| `.github/copilot-instructions.md` | Concise Copilot-specific guardrails |
| `.github/instructions/DEVELOPERS.md` | PR hygiene, contribution criteria |
| `.github/instructions/SOURCES.md` | Curated official reference links |
| `docs/ARCHITECTURE.md` | Runtime component diagram and action bridge design |
| `docs/OPERATIONS.md` | Install/update/uninstall/backup and day-to-day ops |
| `docs/CONFIG_REFERENCE.md` | All config files and variables |
| `docs/TROUBLESHOOTING.md` | Common problems and fixes |
| `docs/SMOKE_TEST_RUNBOOK.md` | Release verification procedure |
| `docs/SUPPORT_BOUNDARIES.md` | Platform support, known limits, HA Container vs HA OS |
