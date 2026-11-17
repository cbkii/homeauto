#!/usr/bin/env python3
"""Plan, prepare or start an isolated homeauto deployment; never install packages."""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import PROFILES, REPO, atomic, compose, run, safe_root, state, owned_services  # noqa: E402

LOG = logging.getLogger('homeauto')


def password_hash(password: str) -> str:
    # Mosquitto 2 SHA512-PBKDF2 format, verified by broker integration CI.
    salt = secrets.token_bytes(12)
    iterations = 100_000
    digest = hashlib.pbkdf2_hmac('sha512', password.encode(), salt, iterations, dklen=64)
    return '$7$' + str(iterations) + '$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def write(path: Path, content: str, mode=0o600, gid=None):
    atomic(path, content, mode)
    if gid is not None and os.geteuid() == 0:
        os.chown(path, -1, gid)


Z2M_SETTINGS_VERSION = 5  # zigbee2mqtt 2.14.3 settings.CURRENT_VERSION; avoids v1->v5 migration.
NETWORK_ACK = ('Zigbee needs --zigbee-network new: the first Zigbee2MQTT start forms a network from '
               'generated parameters and replaces any network already on that coordinator. To keep an '
               'existing network, follow docs/ZIGBEE.md instead')


def zigbee_first_start(root: Path) -> bool:
    """Z2M writes these after it has formed/adopted a network; absent means first start."""
    data = root / 'zigbee2mqtt'
    return not ((data / 'coordinator_backup.json').exists() or (data / 'database.db').exists())


def validate_zigbee(device: str, adapter: str, zigbee_network: str, zigbee_rtscts: bool | None):
    # Whole-path allowlist: the value is written into .env, so a newline could inject
    # another Compose variable (e.g. override MQTT_BIND_ADDRESS).
    if not re.fullmatch(r'/dev/serial/by-id/[A-Za-z0-9._:+@-]{1,200}', device) or adapter not in {'ember', 'zstack'}:
        raise ValueError('Zigbee needs a stable by-id path and explicitly verified ember/zstack variant')
    if zigbee_network != 'new':
        raise ValueError(NETWORK_ACK)
    if zigbee_rtscts is None:
        raise ValueError('Zigbee needs --zigbee-rtscts true|false from the adapter vendor documentation '
                         '(SMLIGHT SLZB-07/MGx: true; SLZB-07pX: false; see docs/ZIGBEE.md)')


def z2m_settings(password: str, adapter: str, rtscts: bool) -> str:
    z2m = dict(version=Z2M_SETTINGS_VERSION, homeassistant={'enabled': True}, frontend={'enabled': True, 'port': 8080},
               mqtt={'server': 'mqtt://mosquitto:1883', 'user': 'zigbee', 'password': password},
               serial={'port': '/dev/zigbee', 'adapter': adapter, 'rtscts': rtscts},
               advanced={'network_key': list(secrets.token_bytes(16)),
                         'pan_id': secrets.randbelow(0xFFFE) + 1, 'ext_pan_id': list(secrets.token_bytes(8))},
               availability={'enabled': True})
    # JSON is a YAML subset; no template expansion or Python YAML dependency.
    return json.dumps(z2m, indent=2) + '\n'


@contextlib.contextmanager
def root_lock(root: Path):
    """Same flock file as the lifecycle tools' operation lock, so they exclude each other."""
    fd = os.open(root / '.operation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another homeauto lifecycle operation is active') from exc
        yield
    finally:
        os.close(fd)


def add_zigbee(root: Path, current: dict, device: str, adapter: str, zigbee_network: str,
               zigbee_rtscts: bool | None) -> bool:
    """Additive profile: an existing root already holds the zigbee broker account and ACL.

    Writes Z2M settings, then the .env device line, then the marker (commit point). A crash
    before the marker leaves Zigbee unselected and the step safely repeatable. Refused once
    Z2M has ever run in this root, so a formed network is never overwritten.
    """
    validate_zigbee(device, adapter, zigbee_network, zigbee_rtscts)
    with root_lock(root):
        if not zigbee_first_start(root):
            raise ValueError('Zigbee2MQTT has already run in this root; network settings are never regenerated')
        password = json.loads((root / 'secrets.json').read_text())['zigbee']
        if not re.fullmatch(r'[0-9a-f]{48}', password):
            raise ValueError('Existing zigbee broker credential unreadable')
        acl = (root / 'mosquitto/config/acl').read_text()
        if 'user zigbee\ntopic readwrite zigbee2mqtt/#' not in acl:
            raise ValueError('Existing broker ACL lacks the zigbee account; use a new root')
        env = (root / '.env').read_text().splitlines()
        if sum(line.startswith('ZIGBEE_DEVICE=') for line in env) != 1:
            raise ValueError('Unexpected .env layout; refusing to edit it')
        write(root / 'zigbee2mqtt/configuration.yaml', z2m_settings(password, adapter, zigbee_rtscts))
        write(root / '.env', '\n'.join(f'ZIGBEE_DEVICE={device}' if line.startswith('ZIGBEE_DEVICE=') else line
                                       for line in env) + '\n')
        marker = dict(current, profiles=sorted(set(current['profiles']) | {'zigbee'}), zigbee_device=device,
                      zigbee_adapter=adapter, zigbee_network=zigbee_network, zigbee_rtscts=zigbee_rtscts)
        write(root / '.homeauto.json', json.dumps(marker, indent=2) + '\n')
    LOG.info('Zigbee added to existing root; HA/MQTT state and credentials unchanged. Run --apply to start it')
    return True


def prepare(root: Path, profiles: list[str], device: str, adapter: str, bluetooth: bool,
            project: str, timezone: str, zigbee_network: str = '', zigbee_rtscts: bool | None = None) -> bool:
    safe_root(root)
    if root.exists():
        current = state(root)
        if (set(profiles) - set(current['profiles']) == {'zigbee'} and set(current['profiles']) <= set(profiles)
                and current.get('bluetooth') == bluetooth):
            return add_zigbee(root, current, device, adapter, zigbee_network, zigbee_rtscts)
        if sorted(current['profiles']) != sorted(profiles) or current.get('bluetooth') != bluetooth:
            raise ValueError('Profile changes require a separate backed-up deployment; rerun with original selectors')
        if device and device != current.get('zigbee_device'):
            raise ValueError('Coordinator change requires explicit migration; existing network preserved')
        if adapter and adapter != current.get('zigbee_adapter'):
            raise ValueError('Adapter differs from stored coordinator; existing network preserved')
        if zigbee_rtscts is not None and zigbee_rtscts != current.get('zigbee_rtscts'):
            raise ValueError('Serial flow control is recorded once; existing state preserved')
        if zigbee_network and zigbee_network != current.get('zigbee_network'):
            raise ValueError('Zigbee network decision is recorded once; existing state preserved')
        LOG.info('Prepared state already exists; no credentials/configuration changed')
        return False
    if not root.parent.is_dir():
        raise ValueError('Application parent must already exist')
    if 'zigbee' in profiles:
        validate_zigbee(device, adapter, zigbee_network, zigbee_rtscts)
    elif zigbee_network or zigbee_rtscts is not None:
        raise ValueError('--zigbee-network/--zigbee-rtscts apply only to the zigbee profile')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{2,40}', project):
        raise ValueError('Invalid Compose project name')
    if not re.fullmatch(r'[A-Za-z0-9_+/-]+', timezone) or not (Path('/usr/share/zoneinfo') / timezone).is_file():
        raise ValueError('Invalid timezone')
    staging = Path(tempfile.mkdtemp(prefix='.homeauto-prepare-', dir=root.parent))
    os.chmod(staging, 0o700)
    try:
        dirs = ['ha', 'mosquitto/config', 'mosquitto/data', 'mosquitto/health',
                'zigbee2mqtt', 'private', 'esphome', 'nodered', 'mariadb']
        for name in dirs:
            (staging / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ['mosquitto/config', 'mosquitto/health']:
            (staging / name).chmod(0o750)
            if os.geteuid() == 0:
                os.chown(staging / name, -1, 1883)
        for name, uid in [('mosquitto/data', 1883), ('nodered', 1000), ('mariadb', 999)]:
            if os.geteuid() == 0:
                os.chown(staging / name, uid, uid)
        credentials = {user: secrets.token_hex(24) for user in ['ha', 'zigbee', 'bridge', 'health', 'db_root', 'db_user']}
        write(staging / 'secrets.json', json.dumps(credentials, indent=2) + '\n')
        for name in ['db_root', 'db_user']:
            write(staging / 'private' / name, credentials[name] + '\n')
        passwd = ''.join(user + ':' + password_hash(credentials[user]) + '\n'
                         for user in ['ha', 'zigbee', 'bridge', 'health'])
        write(staging / 'mosquitto/config/passwd', passwd, 0o640, 1883)
        acl = ('user ha\ntopic readwrite homeassistant/#\ntopic readwrite zigbee2mqtt/#\n'
               'topic read homeauto/#\ntopic write ha/actions/#\n\n'
               # Z2M subscribes to homeassistant/# during discovery to clear stale entities.
               'user zigbee\ntopic readwrite zigbee2mqtt/#\ntopic readwrite homeassistant/#\n\n'
               'user bridge\ntopic read ha/actions/#\ntopic write homeauto/bridge/#\n\n'
               'user health\ntopic write homeauto/health\n')
        write(staging / 'mosquitto/config/acl', acl, 0o640, 1883)
        write(staging / 'mosquitto/config/mosquitto.conf', (REPO / 'mosquitto/config/mosquitto.conf').read_text(), 0o640, 1883)
        write(staging / 'mosquitto/health/mosquitto_pub', '-u health\n-P ' + credentials['health'] + '\n', 0o640, 1883)
        write(staging / 'ha/configuration.yaml', (REPO / 'ha/configuration.yaml.example').read_text())
        write(staging / 'ha/automations.yaml', '[]\n')
        write(staging / 'ha/scripts.yaml', '{}\n')
        write(staging / 'ha/scenes.yaml', '[]\n')
        if 'zigbee' in profiles:
            write(staging / 'zigbee2mqtt/configuration.yaml',
                  z2m_settings(credentials['zigbee'], adapter, zigbee_rtscts))
        write(staging / '.env', f'HOMEAUTO_DATA_DIR={root}\nTZ={timezone}\nMQTT_BIND_ADDRESS=127.0.0.1\nZIGBEE_DEVICE={device or "/dev/null"}\n')
        write(staging / 'compose.yaml', (REPO / 'docker-compose.yml').read_text())
        write(staging / 'compose.bluetooth.yaml', (REPO / 'deploy/q8b/compose.bluetooth.yaml').read_text())
        marker = dict(schema=1, data_dir=str(root), profiles=profiles, project=project,
                      bluetooth=bluetooth, zigbee_device=device, zigbee_adapter=adapter,
                      zigbee_network=zigbee_network, zigbee_rtscts=zigbee_rtscts)
        write(staging / '.homeauto.json', json.dumps(marker, indent=2) + '\n')
        # Never replace an occupied root. mkdir/rename race is prevented by exclusive lock.
        lock = root.parent / ('.' + root.name + '.homeauto-prepare.lock')
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            if root.exists():
                raise ValueError('Application root became occupied')
            staging.rename(root)
        finally:
            os.close(fd)
            lock.unlink()
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    LOG.info('Prepared private configuration at %s; no containers/packages/services changed', root)
    return True


def apply(root: Path) -> int:
    current = state(root)
    owned_services(root)  # Refuse project-name collisions before any up/down.
    command = [sys.executable, str(REPO / 'scripts/diagnostics/homeauto-preflight.py'),
               '--data-dir', str(root)]
    result = run(command, timeout=180)
    print(result.stdout, end='')
    if result.returncode not in {0, 1}:
        LOG.error('Core preflight blocked application; no containers started')
        return 2
    for args in [('config', '--quiet'),
                 ('up', '-d', '--wait', '--wait-timeout', '240', '--no-deps', 'homeassistant', 'mosquitto')]:
        result = run(compose(root, *args), timeout=300)
        if result.returncode:
            LOG.error('Core validation/start failed; inspect local logs')
            return 2
    optional_failed = False
    selections = []
    if 'mariadb' in current['profiles']:
        selections.append(['mariadb'])
    if 'extras' in current['profiles']:
        selections.append(['esphome', 'nodered'])
    if 'zigbee' in current['profiles']:
        flow = current.get('zigbee_rtscts')
        result = run(command + ['--profiles', 'zigbee', '--zigbee-device', current['zigbee_device'],
                                '--zigbee-adapter', current.get('zigbee_adapter', '')] +
                     ([] if flow is None else ['--zigbee-rtscts', str(flow).lower()]), timeout=180)
        if zigbee_first_start(root) and current.get('zigbee_network') != 'new':
            # Roots prepared before the acknowledgement existed: never let a first start
            # overwrite an unknown coordinator network.
            LOG.warning('Zigbee first start blocked: network decision not recorded; HA/MQTT core remains running')
            optional_failed = True
        elif result.returncode in {0, 1}:
            selections.append(['zigbee2mqtt'])
        else:
            print(result.stdout, end='')
            LOG.warning('Zigbee blocked; HA/MQTT core remains running')
            optional_failed = True
    for services in selections:
        result = run(compose(root, 'up', '-d', '--wait', '--wait-timeout', '240', *services), timeout=300)
        if result.returncode:
            LOG.warning('Optional service unavailable; HA/MQTT core remains running')
            optional_failed = True
    LOG.info('Core healthy. UI onboarding, events, boot and recovery still require acceptance.')
    return 1 if optional_failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--prepare', '--no-start', action='store_true')
    mode.add_argument('--apply', '--start', action='store_true')
    mode.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--profiles', default='')
    for profile in sorted(PROFILES):
        parser.add_argument('--with-' + profile, action='store_true')
    parser.add_argument('--with-all', action='store_true', help='zigbee + extras; still needs explicit device/adapter')
    parser.add_argument('--with-bluetooth', action='store_true')
    parser.add_argument('--zigbee-device', default='')
    parser.add_argument('--zigbee-adapter', choices=['ember', 'zstack'], default='')
    parser.add_argument('--zigbee-rtscts', choices=['true', 'false'], default=None,
                        help='Serial hardware flow control from the adapter documentation')
    parser.add_argument('--zigbee-network', choices=['new'], default='',
                        help='Acknowledge that first start forms a new network on the coordinator')
    parser.add_argument('--project', default='homeauto')
    parser.add_argument('--timezone', default='Australia/Sydney')
    parser.add_argument('--generate-secrets', action='store_true', help='Compatibility: prepare always generates once')
    args = parser.parse_args()
    profiles = set(filter(None, args.profiles.split(',')))
    profiles |= {p for p in PROFILES if getattr(args, 'with_' + p)}
    if args.with_all:
        profiles |= {'zigbee', 'extras'}
    if profiles - PROFILES:
        parser.error('Unknown profile')
    try:
        root = safe_root(args.data_dir)
        if args.preflight_only:
            return subprocess.call([sys.executable, str(REPO / 'scripts/diagnostics/homeauto-preflight.py'),
                                    '--data-dir', str(root), '--profiles', ','.join(sorted(profiles)),
                                    '--zigbee-device', args.zigbee_device,
                                    '--zigbee-adapter', args.zigbee_adapter] +
                                   ([] if args.zigbee_rtscts is None else ['--zigbee-rtscts', args.zigbee_rtscts]))
        if args.prepare:
            prepare(root, sorted(profiles), args.zigbee_device, args.zigbee_adapter,
                    args.with_bluetooth, args.project, args.timezone, args.zigbee_network,
                    None if args.zigbee_rtscts is None else args.zigbee_rtscts == 'true')
            return 0
        if args.apply:
            return apply(root)
        print('PLAN ONLY: no mutation. Existing Docker Engine >=23 + Compose required.\n'
              'No package, firmware, firewall, network, media or systemd changes.\n'
              f'Application root: {root}; selected profiles: {sorted(profiles)}\n'
              'Next: --prepare, review protected files, then --apply.\n'
              'Docker absent: inspect dpkg and apt-get -s install docker.io docker-compose; '
              'choose Debian or CE track explicitly. Never auto-remove containerd/runc.')
        return 0
    except ValueError as exc:
        # Our own fixed refusal messages; they never contain credentials or command output.
        LOG.error('STOP: %s. No state changed.', exc)
        return 2
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOG.error('STOP: %s; credentials and external output suppressed', type(exc).__name__)
        return 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
