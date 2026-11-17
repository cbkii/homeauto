#!/usr/bin/env python3
"""Real pinned HA + Mosquitto lifecycle: absent-dongle apply, health, backup, publish, failure, recovery.

Repository-tier evidence on a CI host; it is not Q8B device evidence.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for sub in ['scripts/lib', 'scripts/stack', 'scripts/smoke']:
    sys.path.insert(0, str(ROOT / sub))
from homeauto import compose  # noqa: E402
import commissioning  # noqa: E402


def py(*args, timeout=600):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=timeout)


def health(root, backups, *extra):
    result = py(ROOT / 'scripts/monitor/health.py', '--data-dir', root, '--backup-dir', backups, '--format', 'json', *extra)
    return result.returncode, {c['check']: c['status'] for c in json.loads(result.stdout)['checks']}


def expect(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    expect(os.geteuid() == 0, 'Run as root (production bind ownership)')
    base = Path(tempfile.mkdtemp(prefix='homeauto-life-', dir='/srv' if Path('/srv').is_dir() else None))
    root, backups = base / 'app', base / 'backups'
    try:
        result = py(ROOT / 'scripts/stack/install.py', '--prepare', '--data-dir', root, '--with-zigbee',
                    '--zigbee-device', '/dev/serial/by-id/usb-absent-fixture-if00-port0', '--zigbee-adapter', 'ember',
                    '--zigbee-rtscts', 'true', '--zigbee-network', 'new', '--project', 'life-' + secrets.token_hex(4))
        expect(result.returncode == 0, 'prepare failed: ' + result.stderr[-400:])
        # Gate: optional device loss. Absent coordinator -> exit 1, core healthy, Z2M never started.
        result = py(ROOT / 'scripts/stack/install.py', '--apply', '--data-dir', root)
        expect(result.returncode == 1, f'absent dongle should degrade, got {result.returncode}: {result.stderr[-400:]}')
        code, checks = health(root, backups)
        expect(code == 2 and checks['backup'] == 'FAIL', 'missing backup must fail health')
        expect(checks['service-homeassistant'] == checks['service-mosquitto'] == 'PASS', f'core not healthy: {checks}')
        expect(checks['service-zigbee2mqtt'] == 'WARN' and checks['usb-coordinator'] == 'WARN', f'optional loss: {checks}')
        # Real consistent backup: stop writers, snapshot, resume healthy.
        result = py(ROOT / 'scripts/stack/backup.py', '--data-dir', root, '--backup-dir', backups)
        expect(result.returncode == 0, 'backup failed: ' + result.stderr[-400:])
        code, checks = health(root, backups, '--publish')
        expect(code == 1 and checks['backup'] == 'PASS' and checks['service-homeassistant'] == 'PASS',
               f'post-backup health {code}: {checks}')
        status_code, rows = commissioning.Broker(root).read('-t', 'homeauto/health/status', '--retained-only', wait=3)
        expect(rows and json.loads(rows[0][1])['status'] == 'degraded', 'HA account cannot read published health')
        result = py(ROOT / 'scripts/smoke/commissioning.py', '--data-dir', root)
        expect('PASS  mqtt' in result.stdout, 'commissioning MQTT stage failed:\n' + result.stdout)
        # Failure injection: core service down is a FAIL; apply recovers it.
        subprocess.run(compose(root, 'stop', 'homeassistant'), capture_output=True, timeout=120, check=True)
        code, checks = health(root, backups)
        expect(code == 2 and checks['service-homeassistant'] == 'FAIL', 'stopped HA not detected')
        result = py(ROOT / 'scripts/stack/install.py', '--apply', '--data-dir', root)
        code, checks = health(root, backups)
        expect(result.returncode == 1 and checks['service-homeassistant'] == 'PASS', 'apply did not recover core')
        print('PASS: absent-dongle core start, health, real backup/resume, retained health publish, '
              'MQTT commissioning, core failure detection and recovery')
    finally:
        subprocess.run(compose(root, 'down', '--timeout', '30'), capture_output=True, timeout=180)
        subprocess.run(['rm', '-rf', str(base)], timeout=60)


if __name__ == '__main__':
    main()
