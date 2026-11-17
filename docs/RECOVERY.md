# Backup, restoration and staged upgrades

Backups contain credentials and Zigbee network material. Keep them private and
copy them off-device over SSH or to a verified mounted external filesystem.
A local NVMe archive is not off-device protection.

## Consistent backup

```bash
sudo ./scripts/stack/backup.sh --dry-run
sudo ./scripts/stack/backup.sh --backup-dir /srv/homeauto-backups --keep 7
```

This deliberately causes a **brief application outage**: records running services
and immutable image IDs/registry digests, stops application writers, requires a
nonempty logical SQL dump if MariaDB is selected, stops the DB, snapshots all
state, verifies hashes and resumes only originally running services. HA's SQLite
is copied only after HA stops. MQTT retained state flushes on clean stop.
Use HA's supported UI backups as an additional convenient application backup;
this host backup also preserves MQTT/Zigbee and deployment state.

`--offline` requires all project containers stopped and honestly labels SQL as
`cold-snapshot-only`; it does not claim a logical dump. A stopped/missing required
DB in online mode is a failure. Failed dumps/stops/restore checks publish no
successful new archive. Exit codes: `0` archive verified and original services
healthy; `2` no archive published; `3` archive verified and kept, but original
services did not return healthy within 6 minutes; `4` (with `--copy-to`) local
archive good, off-device copy failed; `5` interrupted by SIGTERM/SIGINT/SIGHUP,
nothing published, services resumed. On `3`, `last-success.json` is not updated
and retention is not pruned.

Before stopping anything the backup records the services it will stop in
`<data-dir>/.backup-stopped.json` (never archived). Normal completion and
in-process interruption remove it after restarting them. If the process is
killed (SIGKILL, OOM, power loss) the marker remains and
`backup.py --data-dir <root> --resume` restarts exactly those services; the
systemd unit runs this as `ExecStopPost`, so a timeout or kill under systemd
recovers automatically. Stale private staging from a killed run is removed by
the next backup after 6 hours. MariaDB is dumped with credentials fed on stdin
from the existing `private/db_root`; no extra secret is required, so roots
prepared by earlier releases back up unchanged.
The archive and staging are private (0600/0700); successful archives have per-file
SHA256, modes, ownership, configuration and image evidence. These hashes detect
corruption; they are not a signature against an attacker replacing the archive.

Default retention is seven verified completed archives, pruned only after a new
success. Take a separate upgrade checkpoint/off-device copy before retention can
remove it. There is no remote destination invented by the installer.

## Verify and rehearse

Substitute the exact archive filename reported by backup:

```bash
sudo python3 scripts/stack/restore.py /srv/homeauto-backups/ARCHIVE.tar.gz
sudo python3 scripts/stack/restore.py /srv/homeauto-backups/ARCHIVE.tar.gz --destination /srv/homeauto-restore-test
```

Destination must be unoccupied. The script rejects links, devices, duplicate or
escaping paths, mismatched hashes and unsafe permissions. No service is started.
A rehearsal at another path retains the original root marker, preventing an
accidental start against live services. Validate SQLite `PRAGMA quick_check`, HA
settings/history, SQL fixture/history and MQTT/Zigbee state on an **isolated host**.
Never attach the same coordinator or Zigbee network to two instances.

To recover in place: stop this project and optional bridge, preserve the failed
root by renaming it, restore to its original now-unoccupied path, verify private
permissions and exact old images/digests, then start core before optional Zigbee.
Use a local console/recovery session when needed. Never overwrite live state or
perform an image-only downgrade after schema migration. Keep the Pi rollback.
Images are not embedded in archives: retain old local images; for offline/off-host
recovery save them separately with `docker image save`, or confirm the recorded
registry digests can still be pulled. Do not prune until restore acceptance.

## Staged upgrade

```bash
sudo ./scripts/stack/upgrade.sh --candidate /opt/homeauto/docker-compose.yml
sudo ./scripts/stack/upgrade.sh --candidate /opt/homeauto/docker-compose.yml --apply
```

The first prints a plan. Review the candidate and exact version/ARM64 manifests.
Apply validates the candidate, creates a consistent checkpoint, stages images,
starts core first and checks health. Pull failure before restart restores only
the previous Compose config. Any failure after restart requires operator review
and a matching data/config/image restoration; no automatic database downgrade.
Finish real event/reboot acceptance before promotion.

## Optional schedule

The repo checkout must be at a stable location accessible to the unit (for example
`/opt/homeauto`). Keep it there while the timer is installed.

```bash
sudo python3 scripts/stack/schedule.py --apply --data-dir /srv/homeauto --backup-dir /srv/homeauto-backups
sudo systemctl start homeauto-backup.service        # manual test under the real sandbox FIRST
journalctl -u homeauto-backup.service --no-pager -n 20
sudo python3 scripts/stack/restore.py /srv/homeauto-backups/<archive> --destination /srv/homeauto-rehearsal
sudo systemctl enable --now homeauto-backup.timer   # only after the above pass
```

The installer validates complete units (`systemd-analyze verify`) and installs the
timer **disabled**. It is all-or-nothing and idempotent: identical managed units
are a no-op; a differing or foreign unit is refused before anything is written.
Data and backup paths must be outside `/home`, `/root` and `/run/user`
(`ProtectHome=read-only`); an existing backup directory must be root-owned 0700.
The unit allows 45 minutes, then SIGTERM with a 10-minute window for the backup to
resume services before SIGKILL (`KillMode=mixed`), and `ExecStopPost` covers a kill.
CI exercises a manual start, a forced timeout and a SIGKILL under real systemd 257
on Debian 13 (x86); repeat the manual start on the Q8B before enabling the timer.
Default 03:00 is the host's timezone, with up to ten minutes' jitter and catch-up
for missed runs; account for brief HA outage. Root is explicit because Docker
socket access and preserving ownership are root-equivalent operations. The unit
restricts writes to state/backups and logs to journald. Removal
(idempotent; only files with the homeauto header are touched; backups retained):
`sudo python3 scripts/stack/schedule.py --apply --remove`.
