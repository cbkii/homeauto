# AGENTS.md

## Purpose
This repository manages a Home Assistant stack running via Docker on Raspberry Pi 5.
Agents (Copilot, Codex, Claude, etc.) MUST prioritise:

- Stability over novelty
- Idempotent shell scripts
- Debian Bookworm / Raspberry Pi OS compatibility
- Docker Compose (v2) correctness
- Home Assistant Container constraints (not HA OS)

## Non‑Goals
- No Home Assistant OS assumptions
- No systemd unit replacement unless explicitly requested
- No cloud dependencies unless unavoidable (e.g. Tuya cloud)

## Mandatory Practices
- All shell scripts must use:
  - `#!/usr/bin/env bash`
  - `set -euo pipefail`
- Never hardcode device paths where discovery is possible
- Never assume interactive terminals
- Prefer explicit logging over silent failure

## Security Expectations
- ADB access must be LAN‑only and non‑interactive
- Bluetooth commands must be non‑discoverable after pairing
- Avoid running long‑lived privileged processes

## Validation
- Scripts must be safe to re‑run
- Uninstall must fully reverse install actions
