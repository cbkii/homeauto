#!/usr/bin/env python3
"""Explicit image staging. No moving tags or unattended restart."""
import argparse
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import compose, run, owned_services

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
parser.add_argument('--pull-only', action='store_true')
args = parser.parse_args()
if not args.pull_only:
    parser.error('Use --pull-only to stage persisted tags. See staged-upgrade runbook before restart.')
try:
    owned_services(args.data_dir)
    result = run(compose(args.data_dir, 'pull'), timeout=600)
    if result.returncode == 0:
        print('SUCCESS: images staged; no containers restarted')
    else:
        # Registry/tag/auth diagnostics from Docker; no credentials are passed on argv.
        print('FAILED: image pull; Docker reported:', file=sys.stderr)
        print('\n'.join((result.stderr or result.stdout).strip().splitlines()[-20:]), file=sys.stderr)
    sys.exit(result.returncode)
except (OSError, ValueError, subprocess.TimeoutExpired):
    print('STOP: invalid state/runtime/timeout', file=sys.stderr)
    sys.exit(2)
