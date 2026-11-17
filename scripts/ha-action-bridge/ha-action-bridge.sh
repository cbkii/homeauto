#!/usr/bin/env bash
# Legacy broad dispatcher disabled; service uses the bounded Python replacement.
# Exit 0: a leftover Pi-era unit with Restart=on-failure must not restart-loop on this shim.
printf '%s\n' 'NOTICE: legacy dispatcher removed; disable this unit and use bridge.py (docs/ACTIONS.md)' >&2
exit 0
