#!/usr/bin/env python3
"""Install or remove optional backup units; default dry-run. Never enable implicitly."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import REPO, atomic, run, state


def units(root, destination):
    return {
        'homeauto-backup.service': f'''[Unit]
Description=homeauto consistent private backup
After=docker.service
Requires=docker.service
RequiresMountsFor={root} {destination}

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory={REPO}
EnvironmentFile=-/etc/homeauto/backup.env
ExecStart=/usr/bin/python3 {REPO}/scripts/stack/backup.py --data-dir {root} --backup-dir {destination}
TimeoutStartSec=30min
UMask=0077
Nice=10
IOSchedulingClass=idle
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={root} {destination}
StandardOutput=journal
StandardError=journal
''',
        'homeauto-backup.timer': '''[Unit]
Description=homeauto daily consistent backup (brief service outage)

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
'''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if not args.apply:
            print('PLAN: remove units (data retained)' if args.remove else 'PLAN: install disabled daily backup timer; brief writer downtime at 03:00 host time')
            return 0
        if os.geteuid() != 0:
            raise ValueError('Root required for unit files')
        if args.remove:
            result = run(['systemctl', 'disable', '--now', 'homeauto-backup.timer'])
            if result.returncode:
                raise RuntimeError('Could not stop timer; units preserved')
            for name in units(args.data_dir, args.backup_dir):
                (Path('/etc/systemd/system') / name).unlink(missing_ok=True)
        else:
            state(args.data_dir)
            if not re.fullmatch(r'/[A-Za-z0-9_/-]+', str(args.backup_dir)) or not re.fullmatch(r'/[A-Za-z0-9_/-]+', str(REPO)):
                raise ValueError('Unit paths require simple absolute characters')
            if args.backup_dir == args.data_dir or args.data_dir in args.backup_dir.parents:
                raise ValueError('Backup target must be outside state root')
            args.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            values = units(args.data_dir, args.backup_dir)
            with tempfile.TemporaryDirectory() as tmp:
                paths = []
                for name, content in values.items():
                    path = Path(tmp) / name
                    path.write_text(content); paths.append(str(path))
                result = run(['systemd-analyze', 'verify', *paths], timeout=30)
                if result.returncode:
                    raise RuntimeError('Unit validation failed')
            for name, content in values.items():
                target = Path('/etc/systemd/system') / name
                if target.exists():
                    raise ValueError('Existing units preserved; inspect before replacing')
                atomic(target, content, 0o644)
        result = run(['systemctl', 'daemon-reload'])
        if result.returncode:
            raise RuntimeError('Unit reload failed')
        print('SUCCESS: units removed; backups retained' if args.remove else 'SUCCESS: units installed disabled. Enable explicitly: systemctl enable --now homeauto-backup.timer')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        print('STOP: scheduling change incomplete; inspect existing units; timer never enabled automatically', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
