# Homeauto Finalization Checklist

This file is the authoritative tracker for:
- implemented vs pending scope,
- release-readiness status,
- roadmap sequencing,
- completion evidence.

_Last updated: 2026-04-14._

---

## 1) Implementation status map (authoritative)

| ID | Area | Requirement / Feature | Status | Evidence (files) | Next step |
|---|---|---|---|---|---|
| S1 | Scope | Homelab-stable baseline target | ✅ Implemented | README + AGENTS alignment | Keep stable |
| S2 | Security | Keep HA `privileged: true` (current phase) | ✅ Implemented | `docker-compose.yml` | Revisit post-v1 |
| S3 | MQTT | Auth required by default | ✅ Implemented | `mosquitto/config/mosquitto.conf` | Add runtime smoke evidence |
| S4 | Zigbee | Stable adapter flow via `/dev/serial/by-id/*` discovery | ✅ Implemented | `system/zigbee-discover.sh`, `.env.example` | Capture hardware smoke logs |
| S5 | Zigbee | In-container device mapping consistency (`/dev/zigbee`) | ✅ Implemented | `docker-compose.yml`, `zigbee2mqtt/configuration.yaml` | Validate on target coordinator |
| S6 | Install | Idempotent install + required env validation | ✅ Implemented | `install.sh` | Runtime smoke evidence |
| S7 | Update | Pull/restart controls + upgrade helper | ✅ Implemented | `update.sh`, `scripts/stack/upgrade.sh` | Validate upgrade path on Bookworm |
| S8 | Uninstall | Preserve by default + explicit purge | ✅ Implemented | `uninstall.sh` | Smoke-test preserve/purge paths |
| S9 | Secrets | Example-based secret handling (`.env`, HA secrets) | ✅ Implemented | `.env.example`, `ha/secrets.yaml.example`, `.gitignore` | Audit docs clarity |
| S10 | ADB | LAN-only helper controls (power/home/back/launch) | ✅ Implemented | `scripts/adb/*` | Add on-device behavioral smoke evidence |
| S11 | Bluetooth | Connect + pair/trust helper workflow | ✅ Implemented | `scripts/bt/*` | Validate against target adapter/device combos |
| S12 | QA | Shell + compose QA script | ✅ Implemented | `scripts/qa.sh` | Ensure tools installed in runner images |
| S13 | QA | CI workflow for QA gate | ✅ Implemented | `.github/workflows/ci.yml` | Observe green run on next push |
| S14 | Docs | Operator runbook coverage | ✅ Implemented | `README.md` | Maintain with behavior changes |
| S15 | Agent enablement | AGENTS + GitHub instruction corpus | ✅ Implemented | `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*` | Keep in sync with status map |
| S16 | Release proof | Debian/Pi full install→run→uninstall smoke evidence | ⚠️ Blocked (current env) | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md`, `artifacts/smoke-report-*.md` | Run on real Debian/Pi host with Docker daemon + hardware access |
| S17 | Release proof | Final DoD closure sign-off | ⏳ Pending | N/A | Close after S16 + QA evidence |
| S18 | Verification tooling | Release smoke automation + runbook available | ✅ Implemented | `scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md` | Use for S16 evidence capture |

Legend: ✅ Implemented, ⏳ Pending, ⚠️ Blocked, ❌ Not started.

---

## 2) Roadmap (sequenced)

### Phase A — Verification on target runtime
- [x] Add scripted smoke harness + runbook (`scripts/smoke/run_release_smoke.sh`, `docs/SMOKE_TEST_RUNBOOK.md`).
- [x] Run non-destructive smoke harness in current environment (`--mode verify`) and capture report artifact.
- [ ] Run Debian 12/Pi OS Bookworm install smoke test on target host.
- [ ] Confirm containers healthy (`homeassistant`, `mosquitto`, `zigbee2mqtt`).
- [ ] Validate Zigbee adapter operation with real coordinator.
- [ ] Validate ADB and Bluetooth helper scripts against real devices.

### Phase B — Evidence and release readiness
- [ ] Capture QA evidence (`./scripts/qa.sh` + CI run links/logs).
- [ ] Capture install/update/uninstall evidence (commands + outputs).
- [ ] Close S16/S17 status rows with evidence references.

### Phase C — Post-v1 hardening backlog (deferred)
- [ ] Evaluate replacing `privileged: true` with fine-grained capabilities.
- [ ] Optional firewall helper tooling (still opt-in by policy).
- [ ] Optional backup/restore helper scripts.

---

## 3) Decision lock-in (from scope finalization)
- Target maturity: homelab-stable baseline.
- Uninstall default: preserve data.
- HA privilege mode: keep `privileged: true` for this phase.
- MQTT password rotation: explicit/opt-in only.
- ADB scope: richer helper scripts included.
- Bluetooth scope: pair + trust workflow included.
- QA baseline: shellcheck + compose config.
- Headless-first operation wherever practical.

---

## 4) Completion evidence log

| Date | Change | Evidence |
|---|---|---|
| 2026-04-14 | Finalization baseline implemented | repo commits + config/scripts/docs updates |
| 2026-04-14 | Agent/developer instruction corpus established | `AGENTS.md` + `.github/instructions/*` |
| 2026-04-14 | Smoke verification tooling added | `scripts/smoke/run_release_smoke.sh` + `docs/SMOKE_TEST_RUNBOOK.md` |
| 2026-04-14 | Environment smoke attempt captured; daemon/hardware limitations identified | `artifacts/smoke-report-*.md` |

---

## 5) File ownership/cross-reference
- `FINALIZATION_CHECKLIST.md`: status map + roadmap + release evidence.
- `AGENTS.md`: contributor/agent operating rules and references.
- `.github/copilot-instructions.md`: concise Copilot-specific guardrails.
- `.github/instructions/*.md`: GitHub-native developer guidance and source index.
