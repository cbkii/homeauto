# homeauto

A portable Home Assistant **Container** stack for Debian 12 and Debian 13 ARM64 or AMD64,
including the Radxa Dragon Q8B. Core: Home Assistant + authenticated Mosquitto.
Zigbee2MQTT, MariaDB, ESPHome, Node-RED, Bluetooth and host actions are opt-in.
New installations use SQLite. No HA OS/Supervisor or router replacement.

**Q8B hardware acceptance is pending.** See [baseline](docs/platforms/Q8B_AUDIT_2026-11-15.md),
[commissioning](docs/platforms/Q8B.md) and [acceptance](docs/SMOKE_TEST_RUNBOOK.md).

## First installation

Run from this checkout; the scripts also work when invoked from another directory.
No package installation, firewall reset or network change is performed.

```bash
./install.sh --plan
python3 scripts/diagnostics/homeauto-preflight.py --format json
```

Exit codes: 0 ready, 1 warnings, 2 blocked, 3 evidence/tool error. Docker absent
is a blocker for application start, not an invitation to replace containerd.
Review [Docker package selection](docs/platforms/Q8B.md) first.

After backups and host prerequisites are established:

```bash
sudo ./install.sh --prepare --data-dir /srv/homeauto
sudo ./scripts/stack/compose.sh --data-dir /srv/homeauto config
sudo ./install.sh --apply --data-dir /srv/homeauto
sudo ./scripts/stack/compose.sh --data-dir /srv/homeauto status
```

The default invocation only prints a plan. `--prepare` creates protected files
once in an **unoccupied** `/srv/homeauto`. Existing unrecognised directories are
refused. `--apply` validates ownership and starts core first; unavailable optional services return 1 while core remains running. Neither installs
or enables host packages/services. Docker must already start at boot.

Open `http://<Q8B-LAN-IP>:8123`, create an owner account, then add MQTT under
**Settings → Devices & services → Add integration → MQTT**. Broker `127.0.0.1`,
port 1883, user `ha`. Read its password locally from the protected
`/srv/homeauto/secrets.json`; do not paste it into logs or issues. ADB/TV and BLE
can usually use native HA integrations after separate qualification.

## Optional profiles

Select profiles during preparation. Flags accumulate; `--profiles zigbee,extras`
is equivalent to `--with-zigbee --with-extras`. `--with-mariadb` provides an
optional SQL server; it does not change HA's recorder. An existing deployment
requires a backed-up migration before changing its selections.

For Zigbee follow [docs/ZIGBEE.md](docs/ZIGBEE.md): confirm the exact radio
variant (all SLZB-07 variants share one CP2102N USB bridge; MG21/MG24/MG26 use
`--zigbee-adapter ember --zigbee-rtscts true`, p7/p10 use `zstack` with
`--zigbee-rtscts false`), pass the stable
`/dev/serial/by-id/` link as `--zigbee-device`, and add `--zigbee-network new`
only if the stick holds no network you need: the first start forms a new network
and replaces any existing one. No firmware is flashed. Verify MQTT -> Z2M -> HA
with the read-only `scripts/smoke/commissioning.py`.

MQTT is published only on loopback by default. Zigbee2MQTT uses the private
Compose network. Z2M, Node-RED and ESPHome dashboards are loopback only; use SSH
forwarding (`ssh -L 8080:127.0.0.1:8080 USER@Q8B`). HA uses host networking for
discovery. Existing host/LAN firewall rules remain the operator's responsibility.

## Operations and recovery

- [Backups and restoration](docs/RECOVERY.md), [optional host actions](docs/ACTIONS.md).
- [Operations](docs/OPERATIONS.md), [configuration](docs/CONFIG_REFERENCE.md).
- [Legacy MariaDB migration](docs/LEGACY_MIGRATION.md): preserve history/config.
- [Support and privilege boundaries](docs/SUPPORT_BOUNDARIES.md).
- [Troubleshooting](docs/TROUBLESHOOTING.md).
- `./scripts/qa.sh`: ShellCheck, syntax, Python tests, all Compose profiles.

Uninstall stops/removes only this Compose project and always preserves state:
`sudo ./uninstall.sh --yes --data-dir /srv/homeauto`. Roll back the matching
configuration **and data** before using an earlier image after schema migration.
