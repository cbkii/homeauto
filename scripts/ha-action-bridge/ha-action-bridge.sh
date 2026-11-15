#!/usr/bin/env bash
# Legacy broad dispatcher disabled; service uses the bounded Python replacement.
printf '%s\n' 'STOP: use bridge.py with a private allowlist; see docs/ACTIONS.md' >&2
exit 2
