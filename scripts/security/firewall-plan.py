#!/usr/bin/env python3
"""Inspect firewall exposure without adding/removing rules or enabling UFW."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import env_read, run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dry-run', action='store_true', help='Default: read-only plan')
parser.add_argument('--format', choices=['text', 'json'], default='text')
parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
args = parser.parse_args()
try:
    mqtt_bind = env_read(args.data_dir / '.env').get('MQTT_BIND_ADDRESS', '127.0.0.1')
    mqtt = ('loopback:1883' if mqtt_bind == '127.0.0.1' else
            f'{mqtt_bind}:1883 (OVERRIDE: reachable beyond this host; Docker-published ports can bypass UFW)')
except (OSError, ValueError):
    mqtt = 'loopback:1883 by default; deployment .env unreadable, effective bind NOT verified'
report = {'mode': 'read-only', 'ufw': 'unknown', 'rule_count': None,
          'ssh_access': 'Verify current SSH port, source and console before any firewall change',
          'bindings': {'HA': 'host:8123', 'MQTT': mqtt, 'Z2M': 'loopback:8080',
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
