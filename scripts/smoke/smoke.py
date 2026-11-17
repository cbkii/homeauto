#!/usr/bin/env python3
"""Write a private read-only preflight report; never install/update/uninstall."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import REPO, atomic, run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode', choices=['verify'], default='verify')
parser.add_argument('--output', type=Path, default=Path('artifacts/preflight.json'))
parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
args = parser.parse_args()
os.umask(0o077)
try:
    result = run([sys.executable, str(REPO / 'scripts/diagnostics/homeauto-preflight.py'),
                  '--format', 'json', '--data-dir', str(args.data_dir)], timeout=180)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic(args.output, result.stdout)
    print('Private preflight report:', args.output)
    sys.exit(result.returncode)
except (OSError, subprocess.TimeoutExpired):
    print('FAILED: report could not be completed', file=sys.stderr)
    sys.exit(3)
