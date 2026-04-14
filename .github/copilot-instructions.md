# Copilot instructions for this repository

## Mission
Contribute safely to a Home Assistant Container stack for Debian 12 / Raspberry Pi OS Bookworm.

## What this file is for
Use this file for coding guardrails and contribution behavior.

## Where status/roadmap lives
Do **not** treat this file as a status tracker.
Implementation status and roadmap are maintained in `FINALIZATION_CHECKLIST.md`.

## Hard requirements
- Preserve install/update/uninstall reversibility.
- Keep secrets out of git (`.env`, `ha/secrets.yaml`, generated password files).
- Do not add WAN exposure by default.
- Prefer headless-safe automation (flags/env over prompts) where practical.

## Must-read files before changes
- `AGENTS.md`
- `FINALIZATION_CHECKLIST.md`
- `README.md`
- `docker-compose.yml`
- `install.sh`, `update.sh`, `uninstall.sh`

## Validation baseline
```bash
./scripts/qa.sh
```

## Documentation discipline
If behavior/config changes, update:
1. `README.md`
2. related `*.example` template files
3. `FINALIZATION_CHECKLIST.md` (only if status/roadmap/evidence changed)
