#!/usr/bin/env python3
"""Remove only managed containers; always preserve configuration, data and images."""
import argparse
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import compose, run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
parser.add_argument('--yes', action='store_true', help='Required to stop/remove containers')
args = parser.parse_args()
if not args.yes:
    parser.error('Pass --yes to remove managed containers. Data is preserved.')
try:
    result = run(compose(args.data_dir, 'down', '--timeout', '60'), timeout=180)
    print('SUCCESS: containers removed; all state/images preserved' if result.returncode == 0 else 'FAILED: containers may remain')
    sys.exit(result.returncode)
except (OSError, ValueError, subprocess.TimeoutExpired):
    print('STOP: invalid state/runtime/timeout', file=sys.stderr)
    sys.exit(2)
