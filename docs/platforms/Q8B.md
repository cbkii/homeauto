# Radxa Dragon Q8B commissioning

Target: Debian 13 / Armbian ARM64 on the existing NVMe-backed root. Keep the
VX230v providing VDSL/router/Wi-Fi, Q8B as a LAN client, Pi bootable as rollback,
and `/media/mediasmb` unchanged. Do not configure WAN on the second NIC.

The [observed baseline](Q8B_AUDIT_2026-11-15.md) is dated evidence. Recheck it
before commissioning. Docker, coordinator firmware/driver and Bluetooth remain
unqualified. Missing optional peripherals must not prevent HA/MQTT startup.

## Development sequence

1. Evidence and support boundaries.
2. Portable preflight, protected external state, modern HA/MQTT/Zigbee stack.
3. Private consistent backups, staged upgrades, safe bridge and monitoring.
4. Opt-in sensors, ESPHome and native Android TV examples.

## Host acceptance

| Gate | State | Required evidence |
| --- | --- | --- |
| Read-only preflight | BLOCKED: not run on host | Current OS/runtime/storage/ports report |
| Docker ARM64 runtime | BLOCKED | Coherent package plan, disposable container/network test |
| HA and authenticated MQTT | BLOCKED | UI onboarding plus publish/subscribe round trip |
| Coordinator identity | UNKNOWN | Label + preflight `coordinator-variant`; Z2M bridge info (type/firmware) |
| Zigbee network decision | UNKNOWN | Stick holds no needed network (`--zigbee-network new`) or manual adoption |
| Zigbee event | BLOCKED | `commissioning.py --device ... --ha-entity ...` all stages PASS |
| Optional device loss | BLOCKED | Dongle absent; HA and MQTT still running |
| Recovery | BLOCKED | Private backup restored on isolated target, off-NVMe copy |
| Persistence | BLOCKED | Warm/cold boot, unchanged SSH/NVMe/LAN, service health |

Acceptance tiers, each requiring timestamped evidence from the previous one:

1. **Repo validated**: CI green (ShellCheck, unit tests, 16 Compose combinations,
   real broker/ACL, Z2M schema, backup/restore, ARM64 manifests). Not device evidence.
2. **Q8B core running**: preflight report, `install.sh --apply` core healthy, HA
   MQTT integration added, `commissioning.py` `mqtt` PASS.
3. **Zigbee event reaches HA**: `commissioning.py` with `--device` and `--ha-entity`
   all stages PASS on the Q8B.
4. **Resilience**: dongle-absent core start, warm/cold reboot, backup, isolated
   restore and off-device copy all rechecked with the same tools.

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
