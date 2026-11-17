# Radxa Dragon Q8B commissioning

Target: Debian 13 / Armbian ARM64 on the existing NVMe-backed root. Keep the
VX230v providing VDSL/router/Wi-Fi, Q8B as a LAN client, Pi bootable as rollback,
and `/media/mediasmb` unchanged. Do not configure WAN on the second NIC.

The [observed baseline](Q8B_AUDIT_2026-11-15.md) is dated evidence. Recheck it
before commissioning. Docker, coordinator firmware/driver and Bluetooth remain
unqualified. Missing optional peripherals must not prevent HA/MQTT startup.

## Exit gates

| Gate | State | Evidence that moves it to PASS |
| --- | --- | --- |
| 1. Review + CI qualified | Repo only | Review threads dispositioned; CI green on both lanes (x86 containers, not the Q8B) |
| 2. Q8B HA/MQTT healthy | BLOCKED | Stage 0-2 outputs below, timestamped on the Q8B |
| 3. Real Zigbee event reaches HA | BLOCKED | Stage 3 `commissioning.py` all PASS with `--device` and `--ha-entity` |
| 4. Reboot, failure recovery, isolated restore | BLOCKED | Stage 4 outputs |

Evidence classes in reports: ENUMERATION (read from /proc, /sys, tools), RUNTIME
(daemon state), TRANSACTION (something actually executed), UNAVAILABLE. CI results
are simulated: they never move a Q8B gate.

## Runbook

Run from the reviewed checkout (`git -C ~/homeauto log -1 --format=%H` recorded
with each output). Nothing below touches boot, firmware, network/firewall, mounts,
the Pi, fan/GPIO, UART/IR or `/media/mediasmb`. Stop at the first unexpected result
and send the output instead of improvising.

**Stage 0 - read-only report (no change).**

```bash
sudo python3 scripts/diagnostics/q8b-report.py > ~/q8b-report-$(date -u +%Y%m%dT%H%M%SZ).json
sudo python3 scripts/diagnostics/q8b-report.py --docker-smoke > ~/q8b-smoke-$(date -u +%Y%m%dT%H%M%SZ).json
```

The second run creates a throwaway bridge network and two containers from the
pinned Mosquitto image, proves container DNS, veth and loopback-published NAT, and
removes them (`cleaned_up: true`). Serials become a stable one-way tag; addresses
become a class. Check the JSON before sharing it anyway.

**Stage 1 - preflight (no change).**

```bash
./install.sh --preflight-only --data-dir /srv/homeauto
```

BLOCK stops here. A port collision lists the conflicting address class.

**Stage 2 - core HA + MQTT (new private state under /srv/homeauto; no Zigbee).**
Outage boundary: none for existing services (new containers, ports 8123 and
127.0.0.1:1883). Rollback: `sudo ./uninstall.sh --data-dir /srv/homeauto --yes`
removes the containers only. State stays in `/srv/homeauto`; delete it by hand only
after you've decided to abandon it.

```bash
sudo ./install.sh --prepare --data-dir /srv/homeauto --timezone Australia/Sydney
sudo ./install.sh --apply --data-dir /srv/homeauto
sudo python3 scripts/stack/manage.py --data-dir /srv/homeauto status
sudo python3 scripts/smoke/commissioning.py --data-dir /srv/homeauto
```

Complete HA onboarding at `http://<q8b>:8123`, then add the MQTT integration in
the UI (host `127.0.0.1`, port 1883, user `ha`, password from
`sudo python3 -c "import json;print(json.load(open('/srv/homeauto/secrets.json'))['ha'])"`).
Gate 2 needs `PASS mqtt` plus HA showing MQTT as connected.

**Stage 3 - Zigbee (only after the decisions in [ZIGBEE.md](../ZIGBEE.md)).**
Prerequisites from you: the printed SKU on the stick; whether it holds a network you
need; approval to let Z2M form a new network (or the manual adoption path). No
firmware flashing. Replug test first (no radio contact):

```bash
sudo python3 scripts/diagnostics/q8b-report.py | python3 -c "import json,sys;print(json.load(sys.stdin)['serial']['devices'])"
# unplug the stick, wait 10 s, replug into the same port, repeat: the by_id tag must match
```

Then add Zigbee to the same root (HA onboarding, MQTT state and credentials are
kept; running containers are not recreated), apply, and run the event check while
operating the device:

```bash
sudo ./install.sh --prepare --data-dir /srv/homeauto --with-zigbee \
  --zigbee-device /dev/serial/by-id/<link> --zigbee-adapter <ember|zstack> \
  --zigbee-rtscts <true|false> --zigbee-network new
sudo ./install.sh --apply --data-dir /srv/homeauto
sudo python3 scripts/stack/manage.py --data-dir /srv/homeauto logs | grep -i zigbee2mqtt | tail -40   # adapter/firmware lines
sudo python3 scripts/smoke/commissioning.py --data-dir /srv/homeauto \
  --device '<friendly name>' --wait 120 --ha-entity <entity_id> --ha-token-file /root/.homeauto-ha-token
```

The first `--apply` after adding Zigbee is the irreversible point: Z2M forms the
network on the stick. Until then, not applying is the rollback. Afterwards,
`sudo python3 scripts/stack/manage.py --data-dir /srv/homeauto stop` stops
everything; the formed network and `coordinator_backup.json` stay in the root and
are included in backups. Enable permit-join only while pairing. Before sharing
logs, remove IEEE addresses (`0x` followed by 16 hex digits).

**Stage 4 - resilience (planned outage of a few minutes each).**

1. Dongle loss: unplug while running; `health.py` shows `usb-coordinator WARN`
   and core PASS; replug; `install.sh --apply` restores Z2M.
2. Units, disabled: `sudo python3 scripts/stack/schedule.py --apply --data-dir <root> --backup-dir /srv/homeauto-backups`.
3. Manual sandboxed runs: `sudo systemctl start homeauto-backup.service` then
   `homeauto-health.service`; read `journalctl -u homeauto-backup.service -n 20`.
   A new private archive and healthy HA/MQTT afterwards are required.
4. Isolated restore: `sudo python3 scripts/stack/restore.py /srv/homeauto-backups/<archive> --destination /srv/homeauto-restore-test`
   (never the live root), then delete the test directory.
5. Off-device copy to a mounted *other* disk: `sudo python3 scripts/stack/offdevice.py --data-dir <root> --backup-dir /srv/homeauto-backups --target /mnt/<disk>`.
6. Controlled reboot: `sudo systemctl reboot`; afterwards, re-run `manage.py status`,
   `commissioning.py` and `health.py`.

Enable timers only after steps 3-6 pass:
`sudo systemctl enable --now homeauto-backup.timer homeauto-health.timer`.

Do not flash coordinator firmware or guess a serial driver. SMLIGHT uses the
same USB bridge across different radio variants. Never repair module BTF errors
by blindly upgrading the kernel. Do not disable pd-mapper/QRTR, reset USB buses,
write fan PWM, alter EFI, or install Pi boot configuration.

For Docker installation inspect Debian `docker.io`/`docker-compose` versus Docker
CE first. Existing containerd/runc may serve other workloads. Application setup
must never remove them or replace APT sources automatically.

## References checked 15 November 2026

- https://docs.docker.com/engine/install/debian/
- https://www.home-assistant.io/installation/linux/
- https://www.home-assistant.io/integrations/mqtt/
- https://www.home-assistant.io/integrations/recorder/
- https://www.zigbee2mqtt.io/guide/installation/02_docker.html
- https://www.zigbee2mqtt.io/guide/configuration/homeassistant.html
- https://smlight.tech/products/slzb-07
