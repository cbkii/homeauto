# Homeauto execution status

Updated 15 November 2026. Source implementation and physical acceptance are separate.

| ID | Deliverable | Source status | Runtime status |
| --- | --- | --- | --- |
| Q0 | Redacted audit and Q8B support/runbook | Implemented | Dated observations only |
| Q1 | Read-only preflight and separated plan/prepare/apply | Implemented; tests in PR | Q8B preflight BLOCKED |
| Q2 | HA/MQTT/SQLite plus secure opt-in Zigbee and optional SQL/extras | Implemented; tests in PR | Docker/radio/event BLOCKED |
| Q3 | Private consistent recovery, staged upgrades, scoped bridge/monitoring | Pending | BLOCKED |
| Q4 | Useful opt-in sensor/ESPHome/TV samples | Pending | BLOCKED |
| S37 | Debian 13/Trixie and Pi compatibility | Source validation target | Physical smoke required |

Base main: `64c612e0aae4f9fbfa404be4e90f342e76b5db5c`. No existing open PRs
at start. Baseline PR #12. No authorised Q8B connection is available in this
workspace. No firmware/kernel/network/storage/router/Pi change has occurred.

Decision changes supersede the previous Pi release: independent core; SQLite
fresh installs; separate bridge network; loopback management bindings; no default
privileged/D-Bus/USB access; external protected state; no automatic packages.
Existing MariaDB history/configuration is preserved by an explicit migration.
