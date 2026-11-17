#!/usr/bin/env python3
"""Optional unprivileged MQTT dispatcher: finite allowlist, short-lived JSON requests."""
from __future__ import annotations
import argparse
import ipaddress
import json
import logging
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

LOG = logging.getLogger('homeauto-actions')
TV_ACTIONS = {'tv_power': '26', 'tv_home': '3', 'tv_back': '4'}
ACTIONS = set(TV_ACTIONS) | {'tv_launch_app', 'bt_connect'}
PRIVATE_NETS = [ipaddress.ip_network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']]


def config_read(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_mode & 0o007:
        raise ValueError('Private config permissions required')
    data = json.loads(path.read_text())
    if not data.get('mqtt', {}).get('username') or not data['mqtt'].get('password'):
        raise ValueError('Dedicated MQTT credentials required')
    for name, target in data.get('tv', {}).items():
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', name):
            raise ValueError('Invalid target name')
        host, port = target.get('host'), target.get('port', 5555)
        # ip_address() also accepts integers; execute() needs a string, so reject before parsing.
        if not isinstance(host, str) or type(port) is not int:
            raise ValueError('TV host must be a string IP and port an integer')
        ip = ipaddress.ip_address(host)
        if not any(ip in network for network in PRIVATE_NETS) or not 1 <= port <= 65535:
            raise ValueError('TV must use an explicitly allowed private IP/port')
        packages = target.get('packages', [])
        if not isinstance(packages, list) or any(not isinstance(p, str) or
                                                 not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{1,199}', p) for p in packages):
            raise ValueError('Invalid package allowlist')
    for name, mac in data.get('bluetooth', {}).items():
        if not isinstance(mac, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', name) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', mac):
            raise ValueError('Invalid Bluetooth allowlist')
    return data


def validate(topic: str, payload: bytes, config: dict, *, now=None) -> tuple[str, dict]:
    if len(payload) > 512 or not topic.startswith('ha/actions/'):
        raise ValueError('Invalid envelope')
    action = topic.removeprefix('ha/actions/')
    if action not in ACTIONS:
        raise ValueError('Unknown action')
    data = json.loads(payload.decode('utf-8', errors='strict'))
    fields = {'target', 'request_id', 'expires'} | ({'package'} if action == 'tv_launch_app' else set())
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('Invalid request schema')
    if not isinstance(data['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', data['request_id']):
        raise ValueError('Invalid request ID')
    timestamp = time.time() if now is None else now
    if type(data['expires']) not in {int, float} or not timestamp < data['expires'] <= timestamp + 60:
        raise ValueError('Expired or excessive request lifetime')
    allowed = config.get('bluetooth', {}) if action == 'bt_connect' else config.get('tv', {})
    if not isinstance(data['target'], str) or data['target'] not in allowed:
        raise ValueError('Target is not allowed')
    if action == 'tv_launch_app' and data['package'] not in allowed[data['target']].get('packages', []):
        raise ValueError('Package is not allowed')
    return action, data


def execute(action: str, request: dict, config: dict):
    if action == 'bt_connect':
        argv = ['/usr/bin/bluetoothctl', 'connect', config['bluetooth'][request['target']]]
        subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        return
    target = config['tv'][request['target']]
    serial = target['host'] + ':' + str(target.get('port', 5555))
    for argv in [
        ['/usr/bin/adb', 'connect', serial],
        ['/usr/bin/adb', '-s', serial, 'shell', 'input', 'keyevent', TV_ACTIONS[action]] if action in TV_ACTIONS else
        ['/usr/bin/adb', '-s', serial, 'shell', 'monkey', '-p', request['package'], '-c', 'android.intent.category.LAUNCHER', '1']
    ]:
        subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


class Dispatcher:
    def __init__(self, config: dict, executor=execute, cache: Path | None = None):
        self.config = config
        self.executor = executor
        self.cache = cache  # persisted so a restart cannot re-run a captured, unexpired request
        self.seen: dict[str, float] = self._load()
        self.pending = queue.Queue(maxsize=16)

    def _load(self) -> dict[str, float]:
        if not self.cache or not self.cache.is_file() or self.cache.is_symlink():
            return {}
        try:
            data = json.loads(self.cache.read_text())
            now = time.time()
            return {k: float(v) for k, v in data.items()
                    if isinstance(k, str) and isinstance(v, (int, float)) and v > now}
        except (OSError, ValueError, AttributeError):
            return {}

    def _persist(self):
        if not self.cache:
            return
        temporary = self.cache.with_name('.' + self.cache.name + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.seen, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.cache)

    def receive(self, topic: str, payload: bytes, retained=False):
        if retained:
            raise ValueError('Retained commands refused')
        action, request = validate(topic, payload, self.config)
        now = time.time()
        self.seen = {key: expiry for key, expiry in self.seen.items() if expiry > now}
        if request['request_id'] in self.seen:
            raise ValueError('Duplicate request')
        if len(self.seen) >= 1024:
            raise ValueError('Rate limit')
        self.seen[request['request_id']] = request['expires']
        self._persist()  # record before queueing: a crash after enqueue still blocks replay
        try:
            self.pending.put_nowait((action, request))
        except queue.Full:
            del self.seen[request['request_id']]  # rejected, not executed: do not consume the ID
            self._persist()
            raise

    def worker(self):
        while True:  # One systemd-owned worker; every external command has a timeout.
            action, request = self.pending.get()
            try:
                validate('ha/actions/' + action, json.dumps(request).encode(), self.config)
                self.executor(action, request, self.config)
                LOG.info('Action completed: %s', action)
            except Exception:  # noqa: BLE001 - the single worker must survive any request
                LOG.warning('Action failed or expired; details suppressed')
            finally:
                self.pending.task_done()


def make_client(config, dispatcher, mqtt):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set(config['mqtt']['username'], config['mqtt']['password'])
    client.will_set('homeauto/bridge/availability', 'offline', qos=1, retain=True)
    def connected(connection, userdata, flags, reason, properties):
        if reason == 0:
            connection.subscribe('ha/actions/#', options=mqtt.SubscribeOptions(qos=1, retainAsPublished=True))
            connection.publish('homeauto/bridge/availability', 'online', qos=1, retain=True)
    def message(connection, userdata, item):
        try:
            dispatcher.receive(item.topic, item.payload, item.retain)
        except (ValueError, UnicodeError, TypeError, queue.Full):
            LOG.warning('Action rejected; topic/payload/credentials suppressed')
    client.on_connect = connected
    client.on_message = message
    client.reconnect_delay_set(min_delay=2, max_delay=30)
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/homeauto/actions.json'))
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args()
    try:
        config = config_read(args.config)
        if args.check_config:
            print('SUCCESS: private action configuration valid; no connection or command issued')
            return 0
        import paho.mqtt.client as mqtt
        state = os.environ.get('STATE_DIRECTORY', '').split(':')[0]
        dispatcher = Dispatcher(config, cache=Path(state) / 'seen-requests.json' if state else None)
        client = make_client(config, dispatcher, mqtt)
        threading.Thread(target=dispatcher.worker, daemon=True).start()
        client.connect_async(config['mqtt'].get('host', '127.0.0.1'), config['mqtt'].get('port', 1883), keepalive=30)
        client.loop_forever(retry_first_connection=True)
        return 0
    except (OSError, ValueError, ImportError):
        LOG.error('Bridge unavailable; private configuration/dependencies require review')
        return 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
