#!/usr/bin/env python3
"""Invoke the persisted Compose project without exposing resolved secrets."""
import argparse
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import compose, run, owned_services

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
parser.add_argument('command', choices=['status', 'start', 'stop', 'config', 'logs'])
args = parser.parse_args()
commands = {'status': ['ps', '--all'], 'start': ['up', '-d', '--wait', '--wait-timeout', '240'],
            'stop': ['stop', '--timeout', '60'], 'config': ['config', '--quiet'], 'logs': ['logs', '--tail', '100']}
try:
    owned_services(args.data_dir)
    if args.command == 'start':
        from install import apply
        sys.exit(apply(args.data_dir))
    if args.command == 'logs':
        # Logs are local-only; review for sensitive device identities before sharing.
        sys.exit(subprocess.call(compose(args.data_dir, *commands[args.command])))
    result = run(compose(args.data_dir, *commands[args.command]), timeout=300)
    if args.command == 'status':
        print(result.stdout, end='')
    print('SUCCESS' if result.returncode == 0 else 'FAILED; inspect local Compose logs')
    sys.exit(result.returncode)
except (OSError, ValueError, subprocess.TimeoutExpired):
    print('STOP: invalid state, unavailable runtime or timeout', file=sys.stderr)
    sys.exit(2)
