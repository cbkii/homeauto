#!/usr/bin/env python3
"""Real broker + ACL path for commissioning.py, with Z2M-shaped retained state (no radio)."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/stack'))
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from install import prepare  # noqa: E402
from homeauto import compose  # noqa: E402

PUB = ('umask 077; d=$(mktemp -d); cat > "$d/mosquitto_pub"; '
       'XDG_CONFIG_HOME="$d" mosquitto_pub -h 127.0.0.1 -r -q 1 "$@"; rc=$?; rm -rf "$d"; exit $rc')


def publish(root, password, topic, message):
    result = subprocess.run(compose(root, 'exec', '-T', 'mosquitto', 'sh', '-c', PUB, 'sh', '-t', topic, '-m', message),
                            input=f'-u zigbee\n-P {password}\n', capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('zigbee user could not publish ' + topic)


def check(root) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke/commissioning.py'), '--data-dir', str(root)],
                            capture_output=True, text=True, timeout=120)
    return result.returncode, result.stdout


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root (production bind ownership)')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'app'
        prepare(root, ['zigbee'], '/dev/serial/by-id/usb-fixture-if00-port0', 'ember', False,
                'commission-ci-' + secrets.token_hex(4), 'Australia/Sydney', 'new')
        password = json.loads((root / 'secrets.json').read_text())['zigbee']
        try:
            up = subprocess.run(compose(root, 'up', '-d', '--wait', '--wait-timeout', '120', 'mosquitto'),
                                capture_output=True, text=True, timeout=180)
            if up.returncode:
                raise RuntimeError('Broker start failed')
            code, out = check(root)
            if code != 2 or 'PASS  mqtt' not in out or 'FAIL  zigbee-bridge' not in out:
                raise RuntimeError('Missing bridge must fail after authenticated MQTT:\n' + out)
            publish(root, password, 'zigbee2mqtt/bridge/state', '{"state":"online"}')
            publish(root, password, 'zigbee2mqtt/bridge/info', json.dumps(dict(
                version='2.14.3', network=dict(channel=15),
                coordinator=dict(type='EmberZNet', ieee_address='0x0000000000000000', meta=dict(revision='8.0.2')))))
            publish(root, password, 'homeassistant/sensor/z2m_ci/linkquality/config',
                    '{"origin":{"name":"Zigbee2MQTT"}}')
            code, out = check(root)
            if code != 0 or out.count('PASS') < 3 or '0x0000000000000000' in out:
                raise RuntimeError('Online bridge/discovery not recognised:\n' + out)
            publish(root, password, 'zigbee2mqtt/bridge/state', '{"state":"offline"}')
            code, out = check(root)
            if code != 2:
                raise RuntimeError('Offline bridge was not reported as failure:\n' + out)
            print('PASS: commissioning check over real broker/ACL: missing, online and offline bridge')
        finally:
            subprocess.run(compose(root, 'down', '--timeout', '30'), capture_output=True, timeout=120)


if __name__ == '__main__':
    main()
