# Qualification runbook

Source QA is not physical acceptance. Keep a private report with timestamp,
repository commit, DMI/revision, OS/image/kernel/DT/BIOS, state root, exact images
and backup location. Publish only redacted results.

1. Establish current SSH/console/recovery and off-device backup. Run read-only
   preflight. Review BTF/USB/platform faults; do not modify boot/network/thermal.
2. Apply an explicitly reviewed Docker package plan; verify ARM64 disposable
   container, bridge, mounts and boot persistence before application start.
3. Prepare an unoccupied state root. Confirm private permissions, no secrets in
   source, current chosen image manifests. Validate persisted Compose config.
4. Start core. Complete HA UI and MQTT integration. Verify a real authenticated
   publish/subscribe event and refusal of bad credentials/unauthorised topics.
5. Confirm coordinator SKU/firmware and by-id mapping, exclusive serial ownership,
   selected driver, then start Zigbee in a separately prepared deployment.
   Pair one test end device and observe its event in HA. Preserve network backup.
6. Stop/restart each core service; remove/reinsert optional Zigbee USB; verify
   HA/MQTT continue and Z2M reconnects/recreates without broad USB reset.
7. Create a consistent private backup; copy off-NVMe, restore to an isolated
   target, verify HA settings/history plus MQTT/Zigbee state. Never share a
   coordinator/network between live and restored test instances.
8. Warm reboot and cold power-on. Verify SSH, intended NVMe/EFI, LAN, mounts,
   service health, actual automation event and no new system/USB errors.
9. Promote only after required checks pass; update canonical current state and
   version pins from actual observations. Keep Pi/router untouched until then.

`scripts/smoke/run_release_smoke.sh --mode verify --output "artifacts/preflight-$(date -u +%Y%m%dT%H%M%SZ).json"`
writes a private, timestamped JSON preflight report containing host checks only;
record the qualification metadata above separately. It never installs, upgrades
or uninstalls a live stack.
Missing evidence is BLOCKED, never converted to a pass by CI.
