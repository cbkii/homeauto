# Configuration

Default state root: `/srv/homeauto` (0700). Must be separate from source and
`/media/mediasmb`; no symlinked or occupied unrecognised root is accepted.

| Path | Purpose |
| --- | --- |
| `.homeauto.json` | Managed root, Compose project, profiles, verified adapter choice |
| `.env` | Public Compose settings: data path, TZ, loopback MQTT, serial link |
| `secrets.json` | 0600 generated service credentials; never print in diagnostics |
| `private/db_*` | MariaDB password files (only consumed by optional DB) |
| `compose.yaml` | Versioned deployment snapshot |
| `ha/` | HA config, SQLite and UI-managed integrations |
| `zigbee2mqtt/` | Protected radio/network configuration, keys and coordinator state |
| `mosquitto/config/` | PBKDF2 password hashes, topic ACLs and broker configuration |
| `mosquitto/data/` | Retained MQTT persistence |
| `mosquitto/health/` | Private client configuration; no password in argv/healthcheck |

Prepared Mosquitto files use group 1883 for the pinned image. Its data uses UID
1883; Node-RED data UID 1000, MariaDB data UID 999. Root preparation sets these
owners; a non-root developer preparation is suitable for unit tests, not proof
of container access permissions. Docker rootless/userns remapping needs separate
qualification; do not broadly chmod secret directories to fix it.

No user `.env` is sourced or executed. Preparation never rewrites existing
credentials, network keys or application configuration. Use the original profile
selectors on rerun. Changing profiles, coordinator or data root is an explicit
backed-up migration, not a regeneration command.

Base Compose tags are pinned. `docker-compose.pinned.yml` remains an empty
compatibility overlay. Manifest validation checks ARM64/AMD64 availability;
actual runtime health remains a host gate. 4 KiB Q8B pages need no jemalloc flag.

`deploy/legacy/docker-compose.yml` archives the prior network/data contract for
inspection. Do not execute this archived Compose file from any directory: its
relative binds resolve under `deploy/legacy`, not the original repository root.
Follow the legacy migration runbook instead.
