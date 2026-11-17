#!/usr/bin/env python3
"""Read-only MQTT -> Zigbee2MQTT -> Home Assistant commissioning evidence.

Publishes nothing, pairs nothing and never changes Zigbee/HA state. Output is a
timestamped stage table; IEEE addresses, credentials and payloads are not printed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import compose, run, state  # noqa: E402

# Option file via stdin keeps the broker password out of host/container argv.
SUB = ('umask 077; d=$(mktemp -d) || exit 3; cat > "$d/mosquitto_sub"; '
       'XDG_CONFIG_HOME="$d" mosquitto_sub -h 127.0.0.1 -F "%t\t%p" "$@"; rc=$?; rm -rf "$d"; exit $rc')
SUB_TIMEOUT, SUB_AUTH = 27, 5  # Measured with eclipse-mosquitto 2.0.22.
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 _./-]{0,63}')
ENTITY = re.compile(r'[a-z_]+\.[a-z0-9_]{1,128}')


def utc() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Broker:
    def __init__(self, root: Path, runner=run):
        self.root, self.runner = root, runner
        self.password = json.loads((root / 'secrets.json').read_text())['ha']

    def read(self, *args: str, wait: int = 3) -> tuple[int, list[tuple[str, str]]]:
        argv = compose(self.root, 'exec', '-T', 'mosquitto', 'sh', '-c', SUB, 'sh', '-W', str(wait), *args)
        result = self.runner(argv, timeout=wait + 30, input=f'-u ha\n-P {self.password}\n')
        rows = [tuple(line.split('\t', 1)) for line in result.stdout.splitlines() if '\t' in line]
        return result.returncode, rows


def payload(rows, topic):
    for name, body in rows:
        if name == topic:
            try:
                return json.loads(body)
            except ValueError:
                return None
    return None


def stage_mqtt(broker) -> tuple[str, str]:
    code, _ = broker.read('-t', 'homeassistant/status', '--retained-only', wait=2)
    if code in {0, SUB_TIMEOUT}:
        return 'PASS', 'ha user authenticated to broker'
    return 'FAIL', 'ha credentials rejected' if code == SUB_AUTH else f'broker unreachable (exit {code})'


def stage_bridge(broker) -> tuple[str, str]:
    _, rows = broker.read('-t', 'zigbee2mqtt/bridge/state', '-t', 'zigbee2mqtt/bridge/info',
                          '--retained-only', wait=3)
    bridge = payload(rows, 'zigbee2mqtt/bridge/state') or {}
    if bridge.get('state') != 'online':
        return 'FAIL', 'Zigbee2MQTT bridge not online (inspect Z2M log locally)'
    info = payload(rows, 'zigbee2mqtt/bridge/info') or {}
    coordinator = info.get('coordinator') or {}
    meta = coordinator.get('meta') or {}
    firmware = meta.get('revision') or meta.get('version') or 'unknown'
    channel = (info.get('network') or {}).get('channel', 'unknown')
    return 'PASS', (f"bridge online; coordinator type {coordinator.get('type', 'unknown')}, "
                    f"firmware {firmware}, channel {channel}; Z2M {info.get('version', 'unknown')}")


def stage_discovery(broker) -> tuple[str, str]:
    _, rows = broker.read('-t', 'homeassistant/+/+/+/config', '--retained-only', wait=3)
    ours = [t for t, body in rows if 'Zigbee2MQTT' in body]
    if not ours:
        return 'FAIL', 'no retained Zigbee2MQTT discovery configs (homeassistant.enabled / ACL)'
    return 'PASS', f'{len(ours)} retained Zigbee2MQTT discovery configs'


def ha_state(entity: str, token: str, opener=urllib.request.urlopen) -> dict:
    request = urllib.request.Request(f'http://127.0.0.1:8123/api/states/{entity}',
                                     headers={'Authorization': 'Bearer ' + token})
    with opener(request, timeout=10) as response:
        return json.load(response)


def stage_event(broker, device: str, wait: int, entity: str | None, token: str | None,
                opener=urllib.request.urlopen) -> tuple[str, str]:
    before = ha_state(entity, token, opener)['last_updated'] if entity else None
    started = time.monotonic()
    code, rows = broker.read('-t', 'zigbee2mqtt/' + device, '-R', '-C', '1', wait=wait)
    if code != 0 or not rows:
        return 'FAIL', f'no live event from {device!r} within {wait}s (operate the device during the wait)'
    detail = f'live event from {device!r} after {time.monotonic() - started:.0f}s'
    if not entity:
        return 'PASS', detail + '; HA entity not checked'
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ha_state(entity, token, opener)['last_updated'] != before:
            return 'PASS', detail + f'; HA {entity} updated'
        time.sleep(1)
    return 'FAIL', detail + f'; HA {entity} did not update within 15s'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--device', help='Z2M friendly name to wait for (operate it during the wait)')
    parser.add_argument('--wait', type=int, default=120)
    parser.add_argument('--ha-entity', help='HA entity_id expected to update from that device')
    parser.add_argument('--ha-token-file', type=Path, help='0600 file holding an HA long-lived token')
    args = parser.parse_args()
    rows = []
    try:
        if args.device and not NAME.fullmatch(args.device) or not 5 <= args.wait <= 900:
            raise ValueError('Invalid device name or wait')
        if bool(args.ha_entity) != bool(args.ha_token_file) or (args.ha_entity and not args.device):
            raise ValueError('--ha-entity needs --ha-token-file and --device')
        token = None
        if args.ha_entity:
            if not ENTITY.fullmatch(args.ha_entity):
                raise ValueError('Invalid entity_id')
            if args.ha_token_file.is_symlink() or args.ha_token_file.stat().st_mode & 0o077:
                raise ValueError('Token file must be a private (0600) regular file')
            token = args.ha_token_file.read_text().strip()
        data = state(args.data_dir)
        broker = Broker(args.data_dir)
        rows.append(('mqtt',) + stage_mqtt(broker))
        if 'zigbee' in data['profiles'] and rows[-1][1] == 'PASS':
            rows.append(('zigbee-bridge',) + stage_bridge(broker))
            rows.append(('ha-discovery',) + stage_discovery(broker))
            if args.device and rows[-2][1] == 'PASS':
                rows.append(('device-event',) + stage_event(broker, args.device, args.wait,
                                                            args.ha_entity, token))
        elif 'zigbee' not in data['profiles']:
            rows.append(('zigbee-bridge', 'SKIP', 'zigbee profile not selected'))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired, urllib.error.URLError) as exc:
        rows.append(('evidence', 'ERROR', str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
    stamp = utc()
    for stage, status, detail in rows:
        print(f'{stamp} {status:5} {stage}: {detail}')
    failed = any(status in {'FAIL', 'ERROR'} for _, status, _ in rows)
    print(f"{stamp} {'FAILED' if failed else 'PASSED'}: read-only; nothing published, paired or changed")
    return 2 if failed else 0


if __name__ == '__main__':
    os.umask(0o077)
    sys.exit(main())
