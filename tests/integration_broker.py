#!/usr/bin/env python3
"""Real pinned-image MQTT authentication/ACL/health-client checks, no LAN ports."""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_install import install


def main():
    name = 'homeauto-ci-' + secrets.token_hex(6)
    image = 'eclipse-mosquitto:2.0.22'
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'state'
        install.prepare(root, [], '', '', False, 'mqtt-test', 'Australia/Sydney')
        creds = json.loads((root / 'secrets.json').read_text())
        clients = Path(temp) / 'clients'
        for user, password in {**creds, 'bad': 'invalid-credential'}.items():
            directory = clients / user
            directory.mkdir(parents=True)
            for executable in ['mosquitto_pub', 'mosquitto_sub']:
                (directory / executable).write_text('-u ' + ('ha' if user == 'bad' else user) + '\n-P ' + password + '\n')
        def command(argv, *, timeout=30):
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        def client(user, executable, *args):
            return command(['docker', 'exec', '-e', 'XDG_CONFIG_HOME=/test/' + user,
                            name, executable, '-h', '127.0.0.1', *args], timeout=15)
        try:
            result = command(['docker', 'run', '-d', '--name', name, '--network', 'none',
                              '--user', f'{os.geteuid()}:{os.getegid()}',
                              '-e', 'XDG_CONFIG_HOME=/health',
                              '-v', f'{root}/mosquitto/config:/mosquitto/config:ro',
                              '-v', f'{root}/mosquitto/data:/mosquitto/data',
                              '-v', f'{root}/mosquitto/health:/health:ro',
                              '-v', f'{clients}:/test:ro', image], timeout=120)
            if result.returncode:
                raise RuntimeError('Broker launch failed')
            for attempt in range(30):
                health = command(['docker', 'exec', name, 'mosquitto_pub', '-h', '127.0.0.1',
                                  '-t', 'homeauto/health', '-m', 'ok'], timeout=10)
                if health.returncode == 0:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError('Generated broker password/health config failed')
            marker = secrets.token_hex(8)
            result = client('zigbee', 'mosquitto_pub', '-t', 'zigbee2mqtt/ci', '-m', marker, '-r', '-q', '1')
            if result.returncode:
                raise RuntimeError('Zigbee authentication/ACL publish failed')
            result = client('ha', 'mosquitto_sub', '-t', 'zigbee2mqtt/ci', '-C', '1', '-W', '5')
            if result.returncode or result.stdout.strip() != marker:
                raise RuntimeError('HA authenticated MQTT roundtrip failed')
            result = client('bad', 'mosquitto_pub', '-t', 'homeauto/health', '-m', 'denied')
            if result.returncode == 0:
                raise RuntimeError('Bad credentials accepted')
            result = command(['docker', 'exec', '-e', 'XDG_CONFIG_HOME=/nonexistent', name,
                              'mosquitto_pub', '-h', '127.0.0.1', '-t', 'homeauto/health', '-m', 'denied'])
            if result.returncode == 0:
                raise RuntimeError('Anonymous client accepted')
            client('ha', 'mosquitto_pub', '-t', 'homeassistant/ci', '-m', marker, '-r', '-q', '1')
            result = client('health', 'mosquitto_sub', '-t', 'homeassistant/ci', '-C', '1', '-W', '2')
            if marker in result.stdout:
                raise RuntimeError('Health user escaped topic ACL')
            print('PASS: real broker auth, roundtrip, bad/anonymous credentials, ACL and health configuration')
        finally:
            command(['docker', 'rm', '-f', name])


if __name__ == '__main__':
    main()
