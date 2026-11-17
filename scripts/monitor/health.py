#!/usr/bin/env python3
"""Read-only service, USB, storage and backup health for one homeauto root.

Exit 0 healthy, 1 warnings (optional parts degraded), 2 failure (core service,
storage or backup). Never restarts, pairs or changes anything. With --publish the
summary is sent retained to homeauto/health/status by the broker's write-only
`health` account (its option file already lives inside the Mosquitto container).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import compose, run, state  # noqa: E402

CORE = ('homeassistant', 'mosquitto')
OPTIONAL = {'zigbee': ('zigbee2mqtt',), 'extras': ('esphome', 'nodered'), 'mariadb': ('mariadb',)}
TOPIC = 'homeauto/health/status'


def age_hours(path: Path, now: datetime) -> float | None:
    try:
        created = json.loads(path.read_text())['created_utc']
        return (now - datetime.fromisoformat(created)).total_seconds() / 3600
    except (OSError, ValueError, KeyError, TypeError):
        return None


def evaluate(facts: dict, *, backup_max_hours: float, copy_max_hours: float) -> list[dict]:
    """Pure decision logic over collected facts (unit tested)."""
    rows = []
    def add(check, status, detail):
        rows.append(dict(check=check, status=status, detail=detail))
    services = facts['services']
    if facts.get('stopped_marker'):
        add('backup-interrupted', 'FAIL', 'a killed backup left services stopped: '
            'run backup.py --data-dir <root> --resume')
    for name in CORE:
        row = services.get(name, {})
        ok = row.get('State') == 'running' and row.get('Health') in {'healthy', '', None}
        add('service-' + name, 'PASS' if ok else 'FAIL',
            f"{row.get('State', 'absent')}/{row.get('Health') or 'no healthcheck'}")
    for profile in facts['profiles']:
        for name in OPTIONAL.get(profile, ()):
            row = services.get(name, {})
            ok = row.get('State') == 'running' and row.get('Health') in {'healthy', '', None}
            add('service-' + name, 'PASS' if ok else 'WARN',
                f"{row.get('State', 'absent')}/{row.get('Health') or 'no healthcheck'} (optional; core unaffected)")
    if 'zigbee' in facts['profiles']:
        add('usb-coordinator', 'PASS' if facts['coordinator_present'] else 'WARN',
            'stable serial link present' if facts['coordinator_present'] else
            'stable serial link absent: check USB seating/hub power; do not substitute ttyUSB paths')
    if facts['bluetooth']:
        add('usb-bluetooth', 'PASS' if facts['hci_present'] else 'WARN',
            'controller present' if facts['hci_present'] else 'no hci controller (optional)')
    free, total = facts['free_bytes'], facts['total_bytes']
    # Absolute floors matter on small disks, percentages on large ones (1 TB NVMe: 5 % = 50 GB).
    add('storage', 'FAIL' if free < 5 * 1024**3 or free < total * 0.05 else
        'WARN' if free < 20 * 1024**3 or free < total * 0.15 else 'PASS', f'{free / 1024**3:.1f} GiB free of {total / 1024**3:.1f} GiB')
    backup = facts['backup_age_hours']
    add('backup', 'FAIL' if backup is None or backup > backup_max_hours else 'PASS',
        'no verified backup with recovered services recorded' if backup is None else
        f'last verified backup {backup:.1f} h ago (limit {backup_max_hours:g} h)')
    copy = facts['copy_age_hours']
    add('backup-offdevice', 'WARN' if copy is None or copy > copy_max_hours else 'PASS',
        'no verified off-device copy recorded' if copy is None else
        f'last verified off-device copy {copy:.1f} h ago (limit {copy_max_hours:g} h)')
    return rows


def collect(root: Path, backup_dir: Path) -> dict:
    data = state(root)
    result = run(compose(root, 'ps', '--all', '--format', 'json'), timeout=60)
    if result.returncode:
        raise RuntimeError('Cannot read Compose service state')
    raw = result.stdout.strip()
    items = [] if not raw else json.loads(raw) if raw.startswith('[') else [json.loads(x) for x in raw.splitlines()]
    device = Path(data.get('zigbee_device') or '/nonexistent')
    try:
        present = str(device).startswith('/dev/serial/by-id/') and device.is_symlink() and device.resolve().is_char_device()
    except OSError:
        present = False
    usage = shutil.disk_usage(root)
    now = datetime.now(timezone.utc)
    return dict(services={i['Service']: i for i in items}, profiles=data['profiles'],
                bluetooth=bool(data.get('bluetooth')), coordinator_present=present,
                hci_present=any(Path('/sys/class/bluetooth').glob('hci*')),
                free_bytes=usage.free, total_bytes=usage.total,
                backup_age_hours=age_hours(backup_dir / 'last-success.json', now),
                copy_age_hours=age_hours(backup_dir / 'last-offdevice.json', now),
                stopped_marker=(root / '.backup-stopped.json').exists())


def publish(root: Path, summary: dict) -> bool:
    argv = compose(root, 'exec', '-T', 'mosquitto', 'mosquitto_pub', '-h', '127.0.0.1',
                   '-t', TOPIC, '-r', '-q', '1', '-s')
    return run(argv, timeout=30, input=json.dumps(summary)).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--backup-max-hours', type=float, default=36)
    parser.add_argument('--copy-max-hours', type=float, default=8 * 24)
    parser.add_argument('--format', choices=['text', 'json'], default='text')
    parser.add_argument('--publish', action='store_true', help='Retained summary to ' + TOPIC)
    args = parser.parse_args()
    try:
        rows = evaluate(collect(args.data_dir, args.backup_dir),
                        backup_max_hours=args.backup_max_hours, copy_max_hours=args.copy_max_hours)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        rows = [dict(check='evidence', status='FAIL', detail=type(exc).__name__)]
    code = 2 if any(r['status'] == 'FAIL' for r in rows) else 1 if any(r['status'] == 'WARN' for r in rows) else 0
    summary = dict(schema=1, checked_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                   status=['ok', 'degraded', 'failed'][code], checks=rows)
    if args.publish and not publish(args.data_dir, summary):
        print('WARN: could not publish health summary (broker down or pre-monitoring ACL)', file=sys.stderr)
        code = max(code, 1)
    if args.format == 'json':
        print(json.dumps(summary, indent=2))
    else:
        for row in rows:
            print(f"{row['status']:4} {row['check']}: {row['detail']}")
        print(f"{summary['checked_utc']} {summary['status'].upper()}: read-only; nothing restarted or changed")
    return code


if __name__ == '__main__':
    os.umask(0o077)
    sys.exit(main())
