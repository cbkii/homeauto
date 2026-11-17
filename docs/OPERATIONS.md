# Operations

Start with [README](../README.md). Commands use the persisted project and
external data directory; run them from the project checkout.

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
tags, without restarting. Do not restart onto new images until a verified backup
exists and its isolated restore has been rehearsed (recovery runbook:
`docs/RECOVERY.md`, delivered with the recovery change).

See [consistent recovery and staged upgrades](RECOVERY.md) and [optional actions](ACTIONS.md).
Backups/restoration and staged upgrades are required before production promotion.
Record backup location and off-device copy, not secrets, in acceptance evidence.

## Monitoring

`scripts/monitor/health.py` is read-only: it never restarts or changes anything.

```bash
sudo python3 scripts/monitor/health.py --data-dir /srv/homeauto --backup-dir /srv/homeauto-backups
```

| Check | FAIL (exit 2) | WARN (exit 1) |
| --- | --- | --- |
| `service-homeassistant`, `service-mosquitto` | not running/healthy | |
| optional services (Z2M, MariaDB, extras) | | not running/healthy; core unaffected |
| `usb-coordinator`, `usb-bluetooth` | | stable link / hci controller absent |
| `storage` (data filesystem) | < 5 GiB or < 5 % free | < 20 GiB or < 15 % free |
| `backup` | no verified backup with recovered services, or > 36 h old | |
| `backup-offdevice` | | none recorded, or > 8 days old |

`--publish` sends the summary retained to `homeauto/health/status` through the
broker's write-only `health` account (the `ha` account can read `homeauto/#`).
Roots prepared before this change keep their original ACL; publishing then
reports a warning. A Home Assistant sensor that becomes unavailable if the checks
stop arriving (YAML MQTT entities remain supported alongside the UI broker setup):

```yaml
mqtt:
  sensor:
    - name: homeauto health
      unique_id: homeauto_health_status
      state_topic: homeauto/health/status
      value_template: "{{ value_json.status }}"
      json_attributes_topic: homeauto/health/status
      json_attributes_template: "{{ {'checked_utc': value_json.checked_utc, 'checks': value_json.checks} | tojson }}"
      expire_after: 1500
```

Install units (both **disabled**; enable explicitly after reviewing outage timing):

```bash
sudo python3 scripts/stack/schedule.py --apply --data-dir /srv/homeauto \
  --backup-dir /srv/homeauto-backups [--copy-to /mnt/<other-disk>]
sudo systemctl enable --now homeauto-health.timer      # every 10 min, read-only
sudo systemctl enable --now homeauto-backup.timer      # 03:00, brief writer outage
```
