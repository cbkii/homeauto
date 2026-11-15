#!/usr/bin/env python3
"""Inspect firewall exposure without adding/removing rules or enabling UFW."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dry-run', action='store_true', help='Default: read-only plan')
parser.add_argument('--format', choices=['text', 'json'], default='text')
args = parser.parse_args()
report = {'mode': 'read-only', 'ufw': 'unknown', 'rule_count': None,
          'ssh_access': 'Verify current SSH port, source and console before any firewall change',
          'bindings': {'HA': 'host:8123', 'MQTT': 'loopback:1883', 'Z2M': 'loopback:8080',
                       'MariaDB': 'loopback:3306', 'ESPHome': 'loopback:6052', 'Node-RED': 'loopback:1880'},
          'next_steps': ['Save existing UFW/nft/iptables rules privately before any approved change',
                         'Review SSH allow rule and recovery console',
                         'Review Docker forwarding; published container ports can bypass UFW',
                         'No automatic firewall apply is provided']}
try:
    result = run(['ufw', 'status', 'numbered'], timeout=10)
    if result.returncode == 0:
        report['ufw'] = 'active' if 'Status: active' in result.stdout else 'inactive'
        report['rule_count'] = sum(line.lstrip().startswith('[') for line in result.stdout.splitlines())
except (OSError, subprocess.TimeoutExpired):
    report['ufw'] = 'unavailable-or-permission-denied'
if args.format == 'json':
    print(json.dumps(report, indent=2))
else:
    for key, value in report.items():
        print(key + ':', value)
