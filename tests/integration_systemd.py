#!/usr/bin/env python3
"""Generated backup units under real systemd (Debian 13 userland, host Docker daemon via socket).

Proves on a CI host (not the Q8B): install idempotence, disabled timer, a manual start under
ProtectSystem=strict/ProtectHome=read-only, a forced start timeout (SIGTERM) and a SIGKILL all
leave HA and Mosquitto running with no partial archive published.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'homeauto-systemd-ci:trixie'
STANDIN = ('[Unit]\nDescription=stand-in: host dockerd reached via bind-mounted socket\n'
           '[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/true\n')


def sh(*argv, timeout=900, check=True):
    result = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{" ".join(argv[:4])} ... failed ({result.returncode}):\n{result.stdout[-800:]}{result.stderr[-800:]}')
    return result


def build():
    if sh('docker', 'image', 'inspect', IMAGE, check=False).returncode == 0:
        return
    name = 'homeauto-sd-build-' + secrets.token_hex(3)
    sh('docker', 'run', '-d', '--name', name, 'debian:trixie', 'sleep', 'infinity')
    try:
        sh('docker', 'exec', name, 'sh', '-c', 'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install '
           '-y -qq --no-install-recommends systemd systemd-sysv python3 docker-cli docker-compose iproute2 psmisc '
           'tzdata ca-certificates >/dev/null')
        sh('docker', 'commit', name, IMAGE)
    finally:
        sh('docker', 'rm', '-f', name, check=False)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root (creates /srv test roots with production ownership)')
    build()
    base = Path('/srv/homeauto-sdci-' + secrets.token_hex(4))
    base.mkdir(mode=0o755)
    app, backups, name = base / 'app', base / 'backups', 'homeauto-sd-' + secrets.token_hex(3)
    sh('docker', 'run', '-d', '--name', name, '--privileged', '--cgroupns=host',
       '-v', '/sys/fs/cgroup:/sys/fs/cgroup:rw', '--tmpfs', '/run', '--tmpfs', '/run/lock',
       '-v', '/var/run/docker.sock:/var/run/docker.sock', '-v', f'{ROOT}:/opt/homeauto:ro',
       '-v', f'{base}:{base}', IMAGE, '/lib/systemd/systemd')

    def x(script, timeout=900, check=True):
        return sh('docker', 'exec', name, 'sh', '-c', script, timeout=timeout, check=check)

    def status():
        raw = x(f'cd /opt/homeauto && docker compose -p sdci{base.name[-8:]} ps --all --format json').stdout.strip()
        rows = json.loads(raw) if raw.startswith('[') else [json.loads(l) for l in raw.splitlines() if l]
        return {r['Service']: (r['State'], r.get('Health')) for r in rows}

    def healthy():
        return status() == {'homeassistant': ('running', 'healthy'), 'mosquitto': ('running', 'healthy')}

    def archives():
        return sorted(p.name for p in backups.glob('homeauto-*.tar.gz'))

    try:
        for _ in range(60):
            if x('systemctl is-system-running', check=False).stdout.strip() in {'running', 'degraded'}:
                break
            time.sleep(1)
        x(f"printf '{STANDIN}' > /etc/systemd/system/docker.service && systemctl daemon-reload && "
          'systemctl start docker.service')
        x(f'cd /opt/homeauto && python3 scripts/stack/install.py --prepare --data-dir {app} '
          f'--project sdci{base.name[-8:]} --timezone UTC && python3 scripts/stack/install.py --apply --data-dir {app}')
        install = f'cd /opt/homeauto && python3 scripts/stack/schedule.py --apply --data-dir {app} --backup-dir {backups}'
        if 'installed' not in x(install).stdout or 'already current' not in x(install).stdout:
            raise RuntimeError('Unit install not idempotent')
        if x('systemctl is-enabled homeauto-backup.timer', check=False).stdout.strip() != 'disabled':
            raise RuntimeError('Timer must stay disabled after install')

        x('systemctl start homeauto-backup.service')
        if len(archives()) != 1 or not healthy():
            raise RuntimeError(f'Manual sandboxed backup failed: {archives()} {status()}')
        print('ok: manual start under ProtectSystem=strict/ProtectHome=read-only published a private archive')

        x('systemctl start homeauto-health.service')  # SuccessExitStatus=1: degraded (no off-device copy) is success
        health = x('journalctl -u homeauto-health.service --no-pager -o cat -n 12').stdout
        if 'PASS service-homeassistant' not in health or 'PASS backup' not in health or 'could not publish' in health:
            raise RuntimeError('Health unit failed under sandbox:\n' + health)
        if x('systemctl is-enabled homeauto-health.timer', check=False).stdout.strip() != 'disabled':
            raise RuntimeError('Health timer must stay disabled after install')
        print('ok: health unit ran under the sandbox, saw the new backup and published')

        x("mkdir -p /etc/systemd/system/homeauto-backup.service.d && printf '[Service]\\nTimeoutStartSec=4s\\n' > "
          '/etc/systemd/system/homeauto-backup.service.d/ci.conf && systemctl daemon-reload')
        if x('systemctl start homeauto-backup.service', check=False).returncode == 0:
            raise RuntimeError('Forced timeout did not trigger')
        log = x('journalctl -u homeauto-backup.service --no-pager -o cat -n 8').stdout
        if 'INTERRUPTED (SIGTERM)' not in log or len(archives()) != 1 or not healthy() or (app / '.backup-stopped.json').exists():
            raise RuntimeError(f'Timeout left bad state: {archives()} {status()}\n{log}')
        print('ok: systemd start timeout -> SIGTERM -> services resumed, nothing published')

        x('rm -r /etc/systemd/system/homeauto-backup.service.d && systemctl daemon-reload && '
          'systemctl start --no-block homeauto-backup.service')
        for _ in range(100):
            if (app / '.backup-stopped.json').exists():
                break
            time.sleep(0.1)
        time.sleep(1)
        x('systemctl kill -s KILL --kill-whom=main homeauto-backup.service')
        for _ in range(600):
            if x('systemctl show -p ActiveState --value homeauto-backup.service').stdout.strip() in {'failed', 'inactive'}:
                break
            time.sleep(1)
        log = x('journalctl -u homeauto-backup.service --no-pager -o cat -n 8').stdout
        if 'RESUMED: homeassistant' not in log or not healthy() or (app / '.backup-stopped.json').exists():
            raise RuntimeError(f'SIGKILL not recovered by ExecStopPost: {status()}\n{log}')
        print('ok: SIGKILL mid-backup -> ExecStopPost --resume restarted services')

        if 'removed' not in x(f'cd /opt/homeauto && python3 scripts/stack/schedule.py --apply --remove').stdout:
            raise RuntimeError('Unit removal failed')
        if 'nothing' not in x(f'cd /opt/homeauto && python3 scripts/stack/schedule.py --apply --remove').stdout:
            raise RuntimeError('Second removal not idempotent')
        print('PASS: systemd install/idempotence/disabled timer, sandboxed start, timeout and SIGKILL recovery, removal')
    finally:
        x(f'cd /opt/homeauto && docker compose -p sdci{base.name[-8:]} down --timeout 30', check=False)
        sh('docker', 'rm', '-f', name, check=False)
        sh('rm', '-rf', str(base), check=False)


if __name__ == '__main__':
    main()
