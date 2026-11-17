#!/usr/bin/env python3
"""Install or remove optional homeauto systemd units; default plan only. Never enables timers.

Install is all-or-nothing and idempotent: identical managed units are left alone, differing
or foreign units are refused before anything is written. Removal tolerates missing units and
deletes only files carrying the managed header.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import REPO, atomic, run, state

UNIT_DIR = Path('/etc/systemd/system')
HEADER = '# Managed by homeauto scripts/stack/schedule.py; edits are overwritten only by explicit reinstall.\n'
SIMPLE = re.compile(r'/[A-Za-z0-9_./-]+')
# ProtectHome=read-only below: application state must not live where the sandbox forbids writes.
HIDDEN = ('/home', '/root', '/run/user')


def units(root: Path, destination: Path) -> dict[str, str]:
    return {
        'homeauto-backup.service': HEADER + f'''[Unit]
Description=homeauto consistent private backup (brief HA/MQTT outage)
After=docker.service
Requires=docker.service
RequiresMountsFor={root} {destination}
ConditionPathExists={root}/.homeauto.json

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {REPO}/scripts/stack/backup.py --data-dir {root} --backup-dir {destination}
# Runs after success, failure, timeout or SIGKILL: restarts anything a backup left stopped.
ExecStopPost=/usr/bin/python3 {REPO}/scripts/stack/backup.py --data-dir {root} --resume
TimeoutStartSec=45min
# SIGTERM goes to backup.py only; it unwinds and resumes services before SIGKILL.
KillMode=mixed
TimeoutStopSec=10min
UMask=0077
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={root} {destination}
StandardOutput=journal
StandardError=journal
''',
        'homeauto-backup.timer': HEADER + '''[Unit]
Description=homeauto daily consistent backup (brief service outage)

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
'''}


def check_paths(root: Path, destination: Path):
    for path in (root, destination, REPO):
        if not path.is_absolute() or '..' in path.parts or not SIMPLE.fullmatch(str(path)):
            raise ValueError(f'Unit paths must be simple absolute paths without ..: {path}')
    for path in (root, destination):
        if any(str(path) == h or str(path).startswith(h + '/') for h in HIDDEN):
            raise ValueError(f'{path} is read-only under the unit sandbox (ProtectHome); use e.g. /srv')
    real_root, real_dest = root.resolve(), destination.resolve()
    if real_dest == real_root or real_root in real_dest.parents or real_dest in real_root.parents:
        raise ValueError('Backup directory must be independent of the application root')


def prepare_destination(destination: Path):
    if destination.is_symlink():
        raise ValueError('Symlinked backup directory refused')
    if destination.exists():
        info = destination.stat()
        # main() requires root, so this means root-owned in production.
        if not destination.is_dir() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Existing backup directory must be root-owned and private (0700); fix it explicitly')
    else:
        destination.mkdir(parents=True, mode=0o700)


def install(root: Path, destination: Path, unit_dir: Path = UNIT_DIR, runner=run) -> list[str]:
    state(root)
    check_paths(root, destination)
    values = units(root, destination)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for name, content in values.items():
            (Path(tmp) / name).write_text(content)
            paths.append(str(Path(tmp) / name))
        if runner(['systemd-analyze', 'verify', '--man=no', *paths], timeout=60).returncode:
            raise RuntimeError('Generated units failed systemd-analyze verify')
    pending = {}
    for name, content in values.items():  # decide for every unit before writing any
        target = unit_dir / name
        if target.is_symlink():
            raise ValueError(f'{target} is a symlink; refusing')
        if target.exists():
            current = target.read_text()
            if current == content:
                continue
            raise ValueError(f'{target} exists and differs; inspect, remove with --remove, then reinstall')
        pending[target] = content
    prepare_destination(destination)
    written = []
    try:
        for target, content in pending.items():
            atomic(target, content, 0o644)
            written.append(target)
    except OSError:
        for target in written:
            target.unlink(missing_ok=True)
        raise
    return [t.name for t in written]


def remove(unit_dir: Path = UNIT_DIR, runner=run) -> list[str]:
    names = list(units(Path('/srv/x'), Path('/srv/y')))
    present = [unit_dir / n for n in names if (unit_dir / n).exists()]
    foreign = [p for p in present if not p.read_text().startswith(HEADER)]
    if foreign:
        raise ValueError('Not homeauto-managed, left untouched: ' + ', '.join(p.name for p in foreign))
    timers = [p.name for p in present if p.name.endswith('.timer')]
    if timers and runner(['systemctl', 'disable', '--now', *timers]).returncode:
        raise RuntimeError('Could not disable timer; units preserved')
    services = [p.name for p in present if p.name.endswith('.service')]
    if services and runner(['systemctl', 'stop', *services], timeout=900).returncode:
        raise RuntimeError('Could not stop service; units preserved')
    for path in present:
        path.unlink()
    return [p.name for p in present]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if not args.apply:
            print('PLAN: remove managed units (backups retained)' if args.remove else
                  'PLAN: install DISABLED daily backup timer (brief writer outage at 03:00 host time). '
                  'Test first: systemctl start homeauto-backup.service; journalctl -u homeauto-backup')
            return 0
        if os.geteuid() != 0:
            raise ValueError('Root required for unit files')
        changed = remove() if args.remove else install(args.data_dir, args.backup_dir)
        if run(['systemctl', 'daemon-reload']).returncode:
            raise RuntimeError('Unit reload failed')
        if args.remove:
            print('SUCCESS: removed ' + (', '.join(changed) or 'nothing (already absent)') + '; backups retained')
        else:
            print('SUCCESS: ' + ('installed ' + ', '.join(changed) if changed else 'units already current') +
                  ' (disabled). Test: systemctl start homeauto-backup.service; then enable explicitly: '
                  'systemctl enable --now homeauto-backup.timer')
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('STOP: ' + (str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__) +
              '. Timer never enabled automatically.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
