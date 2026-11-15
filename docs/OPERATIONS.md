# Operations

Start with [README](../README.md). All commands use the persisted project and
external data directory, independent of the caller's current directory.

```bash
sudo ./scripts/stack/compose.sh status
sudo ./scripts/stack/compose.sh config
sudo ./scripts/stack/compose.sh stop
sudo ./scripts/stack/compose.sh start
```

`logs` prints local service logs; inspect/redact identifiers before sharing.
A successful Compose healthcheck is not complete integration acceptance.

## Docker package selection

Preflight is read-only. Do not run a convenience installer or mix package tracks.
On Debian 13 inspect `dpkg-query`, `apt-cache policy docker.io docker-compose
containerd runc docker-ce containerd.io`, and `apt-get -s install docker.io
docker-compose`. Resolve replacements/outage/recovery before applying any plan.
Docker CE's official instructions require removing conflicts; existing containerd
may have unrelated workloads. This repository never performs that removal.

After the approved installation verify `docker version`, `docker compose version`,
`docker run --rm hello-world`, disposable bridge/overlay operation, boot enablement,
and actual HA/MQTT startup. The Q8B BTF errors make runtime tests essential.

## Stop/uninstall and rollback

`sudo ./uninstall.sh --yes` removes only managed containers/network; data/images
remain. It never deletes `/srv/homeauto`, old Pi data or host services.
Start again with `compose.sh start`. Existing pre-migration deployments must use
their original checkout until the [legacy migration](LEGACY_MIGRATION.md) passes.

Do not downgrade against a migrated database. Keep exact image/configuration/data
versions together. `./update.sh --pull-only` stages only the persisted version
tags, without restarting; see the recovery runbook before changing them.

See [consistent recovery and staged upgrades](RECOVERY.md) and [optional actions](ACTIONS.md).
Backups/restoration and staged upgrades are required before production promotion.
Record backup location and off-device copy, not secrets, in acceptance evidence.
