#!/usr/bin/env python3
"""Real pinned-image MQTT authentication/ACL/health-client checks, no LAN ports."""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import threading
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
            result = command(['docker', 'run', '-d', '--name', name, '-p', '127.0.0.1::1883',
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
            # Z2M subscribes to homeassistant/# to clear stale discovery; it must receive retained config.
            result = client('zigbee', 'mosquitto_sub', '-t', 'homeassistant/#', '-C', '1', '-W', '5')
            if result.returncode or result.stdout.strip() != marker:
                raise RuntimeError('Zigbee user cannot read Home Assistant discovery topics')
            client('ha', 'mosquitto_pub', '-t', 'ha/actions/ci', '-m', marker, '-r', '-q', '1')
            result = client('zigbee', 'mosquitto_sub', '-t', 'ha/actions/#', '-C', '1', '-W', '2')
            if marker in result.stdout:
                raise RuntimeError('Zigbee user escaped action topic ACL')
            client('ha', 'mosquitto_pub', '-t', 'ha/actions/ci', '-r', '-n', '-q', '1')  # clear retained marker
            # Exercise exact production MQTTv5 subscription flags: a retained
            # publish to an already established subscription must stay rejected.
            import importlib.util
            import paho.mqtt.client as mqtt
            spec = importlib.util.spec_from_file_location('bridge', Path(__file__).resolve().parents[1] / 'scripts/ha-action-bridge/bridge.py')
            bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
            port_text = command(['docker', 'port', name, '1883/tcp']).stdout.strip()
            port = int(port_text.rsplit(':', 1)[1])
            config = dict(mqtt=dict(host='127.0.0.1', port=port, username='bridge', password=creds['bridge']),
                          tv={'fixture': {'host': '192.168.1.2', 'packages': []}}, bluetooth={})
            dispatcher = bridge.Dispatcher(config)
            connection = bridge.make_client(config, dispatcher, mqtt)
            subscribed = threading.Event(); received = threading.Event()
            connection.on_subscribe = lambda *a: subscribed.set()
            original = connection.on_message
            def observe(*args):
                original(*args); received.set()
            connection.on_message = observe
            connection.connect('127.0.0.1', port, keepalive=30)
            connection.loop_start()
            try:
                if not subscribed.wait(5):
                    raise RuntimeError('Bridge never subscribed')
                request = json.dumps(dict(target='fixture', request_id='retained_test_123', expires=time.time() + 30))
                result = client('ha', 'mosquitto_pub', '-t', 'ha/actions/tv_home', '-m', request, '-r', '-q', '1')
                if result.returncode or not received.wait(5) or not dispatcher.pending.empty():
                    raise RuntimeError('Live retained action was accepted')
                received.clear()
                request = json.dumps(dict(target='fixture', request_id='ordinary_test_123', expires=time.time() + 30))
                result = client('ha', 'mosquitto_pub', '-t', 'ha/actions/tv_home', '-m', request, '-q', '1')
                if result.returncode or not received.wait(5) or dispatcher.pending.qsize() != 1:
                    raise RuntimeError('Normal allowed action was not queued')
            finally:
                connection.disconnect(); connection.loop_stop()
            print('PASS: real broker auth/ACL/health and live retained-action rejection')
        finally:
            command(['docker', 'rm', '-f', name])


if __name__ == '__main__':
    main()
