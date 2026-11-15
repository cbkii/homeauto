# Troubleshooting

- **No Docker:** run read-only preflight, then inspect a coherent Debian or CE
  package plan. Do not remove containerd or update the Q8B kernel speculatively.
- **Application root occupied:** preserve it; identify old state and use the
  legacy migration runbook. Do not delete the marker or regenerate credentials.
- **MQTT rejected:** use protected credentials locally, verify ACL/user and
  broker health. HA broker configuration belongs in the UI, not YAML keys.
- **Zigbee driver mismatch:** stop only Z2M. Confirm physical SKU and firmware;
  CP210x does not distinguish ember/zstack. Preserve existing network material.
- **USB removed/reinserted:** verify by-id resolves to a character device and no
  competing ZHA/process owns it. Recreate only Z2M after controlled testing; do
  not reset/power-cycle the Q8B USB controller. Core should remain available.
- **Bluetooth activating:** leave the overlay off. Investigate BlueZ separately;
  don't disable Qualcomm services or change USB power policy to unblock core.
- **BTF validation errors:** retain boot/module/package evidence and investigate
  the earliest mismatch separately. Container feature tests decide whether it
  blocks Docker. No kernel/firmware repair belongs in app installation.
- **Permission failure:** verify pinned image UID and private bind permissions;
  do not make secrets world-readable. Rootless/userns deployments need a plan.
- **Port occupied:** identify the existing service before start. Managed-service
  warnings do not prove that an unrelated listener is safe; inspect locally.

Use `compose.sh status` and local `compose.sh logs`. Do not publish raw logs,
configuration, `.storage`, network keys, serial identifiers or secrets.
