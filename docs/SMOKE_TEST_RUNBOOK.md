# Smoke Test Runbook (Debian 12 / Raspberry Pi OS Bookworm)

This runbook provides a reproducible process for closing finalization checklist verification items.

## Goals
- Validate install/update/uninstall lifecycle on target runtime.
- Capture evidence to close `FINALIZATION_CHECKLIST.md` pending rows (S16/S17).

## Prerequisites
- Target host: Debian 12 or Raspberry Pi OS Bookworm (64-bit).
- `.env` configured with a real Zigbee adapter path and credentials.
- Network access for package/image pulls.
- Optional: Android TV and Bluetooth target devices for helper validation.

## 1) Non-destructive verification (recommended first)
```bash
./scripts/smoke/run_release_smoke.sh --mode verify
```

Expected result:
- markdown report generated under `artifacts/`.
- report includes docker/compose versions, compose validation output, and stack status.

## 2) Full lifecycle validation (destructive to running stack state)
```bash
sudo ./scripts/smoke/run_release_smoke.sh --mode full
```

Expected result:
- install/update/uninstall sequence executed.
- markdown report generated under `artifacts/`.

## 3) Device checks (manual)
After install/start:
- Confirm Zigbee2MQTT can access coordinator and no serial-path mismatch.
- Confirm ADB helper scripts can execute against a LAN Android TV.
- Confirm Bluetooth pair/trust/connect scripts work for at least one target device.

## 4) Checklist closure
- Attach report path/output snippets to `FINALIZATION_CHECKLIST.md` evidence log.
- Mark S16 as implemented only once lifecycle + runtime checks are complete.
- Mark S17 done after QA and release evidence are consolidated.


## Troubleshooting quick notes
- If `docker compose ps` fails with daemon socket errors, run on a host with a running Docker daemon (nested CI containers often cannot run Docker networking/iptables).
- If Zigbee checks fail, verify `.env` points to a valid `/dev/serial/by-id/*` path on the target host.
- If ADB checks fail, confirm the TV allows debugging and the target IP is RFC1918 LAN.
