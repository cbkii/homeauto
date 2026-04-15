# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- Compose healthchecks for all three services (`homeassistant`, `mosquitto`,
  `zigbee2mqtt`) so `docker compose ps` reports health at a glance.
- `depends_on: condition: service_healthy` for `homeassistant` and `zigbee2mqtt`
  on `mosquitto` — services wait for the broker to be healthy before starting.
- `scripts/stack/backup.sh` — lightweight tar-based backup helper.
- `docs/SUPPORT_BOUNDARIES.md` — platform support matrix, known limitations,
  HA Container vs HA OS comparison, version pinning policy.
- CI: copy `.env.example` to `.env` before QA so `docker compose config`
  succeeds without real secrets.
- CI: upload QA output and resolved Compose config as workflow artifacts.
- `.github/workflows/dependency-review.yml` — dependency review on PRs (requires
  GHAS on private repos; free on public).

### Changed
- `scripts/qa.sh`: replaced `rg --files` with `find` — removes ripgrep
  dependency, improves portability.
- `docker-compose.yml`: `koenkk/zigbee2mqtt` now uses the explicit `:latest`
  tag instead of an implicit latest; MQTT credentials passed as env vars to
  the `mosquitto` service for the healthcheck.
- `FINALIZATION_CHECKLIST.md`: added new items S22–S27, updated Phase C/B
  roadmap rows, extended evidence log.
- CI: `docker compose config` output now routed through `tee` so errors are
  visible directly in the GitHub Actions step log in addition to the artifact.
- `FINALIZATION_CHECKLIST.md` Phase B: "Capture QA evidence" marked done
  (QA gate and smoke verify confirmed locally 2026-04-15).

---

## [0.1.0] — 2026-04-14

Initial homelab-stable baseline release.

### Added
- Home Assistant Container (`ghcr.io/home-assistant/home-assistant:stable`)
- Mosquitto MQTT broker with mandatory authentication
- Zigbee2MQTT with stable `/dev/serial/by-id/` adapter path
- `install.sh` — idempotent install with env validation
- `update.sh` — pull-and-restart with `--pull-only` option
- `uninstall.sh` — preserve-by-default with explicit `--purge-data`
- `scripts/stack/upgrade.sh` — host dependency reconcile + stack restart
- `scripts/adb/` — Android TV ADB helper scripts (tv_power, tv_home, tv_back,
  tv_launch_app)
- `scripts/bt/` — Bluetooth helper scripts (bt_connect, bt_pair_trust)
- `scripts/ha-action-bridge/` — host-side MQTT action bridge (systemd service)
  fixing the shell_command host/container boundary problem
- `scripts/qa.sh` — shellcheck + compose config QA script
- `scripts/smoke/run_release_smoke.sh` — release verification automation
- `system/zigbee-discover.sh` — stable adapter path discovery
- `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/CONFIG_REFERENCE.md`,
  `docs/TROUBLESHOOTING.md`, `docs/SMOKE_TEST_RUNBOOK.md`
- `.github/workflows/ci.yml` — CI QA workflow
- `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/` —
  agent and contributor guidance corpus
