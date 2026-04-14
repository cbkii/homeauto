# Developer & Agent Playbook

This file defines workflow expectations for contributors using GitHub tooling.

## Separation of concerns
- `FINALIZATION_CHECKLIST.md` = implementation status map + roadmap + completion evidence.
- `AGENTS.md` + `.github/instructions/*` = operating instructions + references.

## Contribution acceptance criteria
- Install remains idempotent/re-runnable.
- Uninstall remains reversible with preserve-by-default behavior.
- Secrets are never committed.
- No default WAN exposure is introduced.
- QA checks pass (`shellcheck`, `docker compose config`).

## Reference hierarchy
1. Official docs (authoritative).
2. Upstream project repos.
3. Community examples (patterns only, verify before adopting).

## PR hygiene expectations
- Keep diffs small, reversible, and explicitly scoped.
- Explain user-visible behavior changes.
- Cite official docs for security/runtime-sensitive changes.
- Update runbook/examples when config behavior changes.
- Update checklist rows if completion status or roadmap changes.

## Primary docs to cite in PRs
- Home Assistant install (Linux/Container): https://www.home-assistant.io/installation/linux/
- Home Assistant common tasks (Container): https://www.home-assistant.io/common-tasks/container/
- Home Assistant Bluetooth integration: https://www.home-assistant.io/integrations/bluetooth/
- Home Assistant Android TV (ADB): https://www.home-assistant.io/integrations/androidtv/
- Docker Engine install (Debian): https://docs.docker.com/engine/install/debian/
- Compose reference: https://docs.docker.com/reference/compose-file/
- Zigbee2MQTT Docker guide: https://www.zigbee2mqtt.io/guide/installation/02_docker.html
- Zigbee2MQTT adapter settings: https://www.zigbee2mqtt.io/guide/configuration/adapter-settings.html
- Mosquitto authentication methods: https://mosquitto.org/documentation/authentication-methods/

## Verification runbook
- Non-destructive smoke: `./scripts/smoke/run_release_smoke.sh --mode verify`
- Full lifecycle smoke (target host): `sudo ./scripts/smoke/run_release_smoke.sh --mode full`
- Procedure details: `docs/SMOKE_TEST_RUNBOOK.md`
