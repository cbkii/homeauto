# Copilot instructions for this repository

## Mission
Contribute safely to a Home Assistant Container stack for Debian 12 / Raspberry Pi OS Bookworm.

## Where things live
- **Status / roadmap / evidence**: `FINALIZATION_CHECKLIST.md` (authoritative).
- **Operating rules + references**: `AGENTS.md`.
- **Architecture**: `docs/ARCHITECTURE.md`.
- **Config reference**: `docs/CONFIG_REFERENCE.md`.

## Hard requirements
- Preserve install/update/uninstall reversibility and idempotency.
- Keep secrets out of git (`.env`, `ha/secrets.yaml`, `mosquitto/config/passwd`, `/etc/ha-action-bridge.env`).
- Do not add WAN exposure by default.
- Do NOT use `shell_command` for ADB/Bluetooth — use MQTT publish to `ha/actions/#` (see `docs/ARCHITECTURE.md`).
- Prefer headless-safe automation (flags/env over interactive prompts).

## Must-read before changes
- `AGENTS.md`
- `FINALIZATION_CHECKLIST.md`
- `docs/ARCHITECTURE.md`
- `docker-compose.yml`
- `install.sh`, `update.sh`, `uninstall.sh`

## Validation baseline
```bash
./scripts/qa.sh
```

## Documentation discipline
If behavior or config changes, update:
1. `README.md`
2. Relevant `*.example` template files
3. `docs/` (ARCHITECTURE, OPERATIONS, CONFIG_REFERENCE, TROUBLESHOOTING as appropriate)
4. `FINALIZATION_CHECKLIST.md` (only if status or roadmap changed)
