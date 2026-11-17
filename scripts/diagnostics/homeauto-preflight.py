#!/usr/bin/env python3
"""Read-only host discrimination. Output never includes raw command logs/IDs."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import run, safe_root, state, owned_services  # noqa: E402

PORTS = {'homeassistant': 8123, 'mosquitto': 1883, 'zigbee': 8080,
         'mariadb': 3306, 'esphome': 6052, 'nodered': 1880}


# SMLIGHT SLZB-07 family: every variant uses the same CP2102N bridge, so VID:PID cannot
# identify the radio. Variant naming per smlight.tech product pages (checked 2026-11-17).
SLZB07_VARIANTS = {'': ('EFR32MG21', 'ember'), 'mg24': ('EFR32MG24', 'ember'),
                   'mg26': ('EFR32MG26', 'ember'), 'p7': ('CC2652P7', 'zstack'),
                   'p10': ('CC2674P10', 'zstack')}


def variant_hint(product: str | None):
    """Map a USB product descriptor to (variant, radio, adapter); None when unrecognised."""
    match = re.search(r'SLZB-07(Mg24|Mg26|p7|p10)?(?![A-Za-z0-9])', product or '', re.IGNORECASE)
    if not match:
        return None
    suffix = (match.group(1) or '').lower()
    return ('SLZB-07' + (match.group(1) or ''),) + SLZB07_VARIANTS[suffix]


def usb_descriptor(serial: Path) -> dict | None:
    """Read-only sysfs walk from the tty to its USB device; serial number never read."""
    try:
        node = (Path('/sys/class/tty') / serial.resolve().name / 'device').resolve()
    except OSError:
        return None
    while node != node.parent and not (node / 'idVendor').is_file():
        node = node.parent
    if not (node / 'idVendor').is_file():
        return None
    def attr(name):
        path = node / name
        value = path.read_text(errors='replace').strip() if path.is_file() else ''
        return re.sub(r'[^A-Za-z0-9 ._-]', '', value)[:64]
    return dict(vid=attr('idVendor'), pid=attr('idProduct'), manufacturer=attr('manufacturer'),
                product=attr('product'))


def checks(facts: dict, profiles: set[str], adapter: str = '') -> list[dict]:
    rows = []
    def add(name, status, detail):
        rows.append(dict(check=name, status=status, detail=detail))
    add('platform', 'PASS' if facts['os'] in {'debian', 'raspbian'} else 'WARN',
        f"{facts['os']} {facts['version']}; {facts['arch']}; {facts['kernel']}")
    add('architecture', 'PASS' if facts['arch'] in {'aarch64', 'x86_64'} else 'BLOCK',
        'ARM64 and AMD64 image lanes; other architectures require qualification')
    add('pages', 'PASS' if facts['pages'] == 4096 else 'WARN',
        f"{facts['pages']} bytes; large pages require HA jemalloc qualification")
    add('cgroup', 'PASS' if facts['cgroup2'] else 'WARN', 'cgroup v2 ' + str(facts['cgroup2']))
    add('docker', 'PASS' if facts['docker_ready'] else 'BLOCK',
        'Engine >=23 and Compose available' if facts['docker_ready'] else
        'Engine/daemon/permissions/Compose missing or unsupported; inspect package plan')
    add('package-track', 'BLOCK' if facts['mixed_packages'] else 'PASS',
        'Conflicting Debian/CE packages' if facts['mixed_packages'] else
        'Installed package names: ' + ', '.join(facts['packages']))
    for feature, available in facts['features'].items():
        add('kernel-' + feature, 'PASS' if available == 'y' else 'BLOCK' if available == 'n' else 'WARN',
            'Built-in' if available == 'y' else 'Required feature disabled' if available == 'n' else
            'Module or unknown; actual Docker network test required')
    add('storage', 'PASS' if facts['free_bytes'] >= 5 * 1024**3 else 'BLOCK',
        f"Available bytes on application filesystem: {facts['free_bytes']}")
    add('ownership', 'PASS' if facts['writable'] else 'WARN',
        'Application parent writable' if facts['writable'] else 'Preparation requires appropriate owner/root')
    add('time', 'PASS' if facts['ntp'] else 'WARN', 'NTP synchronisation ' + str(facts['ntp']))
    needed = {'homeassistant', 'mosquitto'}
    if 'zigbee' in profiles:
        needed.add('zigbee')
        add('coordinator', 'PASS' if facts['serial_present'] else 'BLOCK',
            'Stable serial character device present; radio/firmware still unverified'
            if facts['serial_present'] else 'Select existing /dev/serial/by-id path and confirm variant')
        add('serial-owner', 'BLOCK' if facts['serial_busy'] else 'WARN',
            'Another process holds serial device' if facts['serial_busy'] else
            'No holder found or insufficient permissions; verify exclusive ownership before initialisation')
        descriptor = facts.get('serial_descriptor')
        hint = variant_hint(descriptor and descriptor['product'])
        if facts['serial_present'] and hint and adapter and hint[2] != adapter:
            add('coordinator-variant', 'BLOCK', f'USB descriptor reports {hint[0]} ({hint[1]}, adapter {hint[2]}); '
                f'declared adapter {adapter} does not match. Confirm label/firmware; no radio was contacted')
        elif facts['serial_present'] and hint:
            add('coordinator-variant', 'PASS' if adapter else 'WARN',
                f'USB descriptor reports {hint[0]} ({hint[1]}, adapter {hint[2]})' +
                ('' if adapter else '; declare --zigbee-adapter') +
                '; firmware type/version and network state verified only by Zigbee2MQTT start')
        elif facts['serial_present']:
            add('coordinator-variant', 'WARN', 'USB descriptor ' +
                (f"{descriptor['vid']}:{descriptor['pid']} '{descriptor['product']}'" if descriptor else 'unreadable') +
                ' does not identify the radio; confirm SKU label and firmware before declaring an adapter')
    if 'extras' in profiles:
        needed |= {'esphome', 'nodered'}
    if 'mariadb' in profiles:
        needed.add('mariadb')
    for name in sorted(needed):
        owned = ('zigbee2mqtt' if name == 'zigbee' else name) in facts.get('managed_services', [])
        occupied = PORTS[name] in facts['ports']
        add('port-' + name, 'WARN' if occupied and owned else 'BLOCK' if occupied else 'PASS',
            f'TCP {PORTS[name]} active (managed service)' if occupied and owned else
            f'TCP {PORTS[name]} occupied by other service' if occupied else f'TCP {PORTS[name]} free')
    add('network', 'WARN', 'Interfaces: ' + ', '.join(facts['interfaces']) +
        '; network configuration unchanged; household LAN and firewall require review')
    add('usb', 'WARN', 'USB vendor/product topology: ' + ', '.join(facts['usb']) +
        '; enumeration is not a radio/hotplug test')
    add('optional-bluetooth', 'WARN', 'Controller readiness is independent of core; qualify separately')
    return rows


def collect(root: Path, serial: str) -> dict:
    os_data = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        key, _, value = line.partition('=')
        os_data[key] = value.strip('"')
    def probe(argv):
        try:
            return run(argv, timeout=8)
        except (FileNotFoundError, PermissionError):
            return None
    version = probe(['docker', 'version', '--format', '{{.Server.Version}}'])
    plugin = probe(['docker', 'compose', 'version'])
    ready = bool(version and version.returncode == 0 and plugin and plugin.returncode == 0)
    if ready:
        try:
            ready = int(version.stdout.split('.')[0]) >= 23
        except ValueError:
            ready = False
    package_names = ['docker.io', 'docker-compose', 'docker-ce', 'docker-ce-cli',
                     'docker-compose-plugin', 'containerd', 'containerd.io', 'runc', 'podman-docker']
    installed = []
    for pkg in package_names:
        result = probe(['dpkg-query', '-W', '-f=${Status}', pkg])
        if result and result.returncode == 0 and result.stdout.strip() == 'install ok installed':
            installed.append(pkg)
    mixed = ('containerd.io' in installed and bool({'containerd', 'runc'} & set(installed))) or (
        'docker-ce' in installed and bool({'docker.io', 'podman-docker'} & set(installed)))
    existing = root
    while not existing.exists():
        existing = existing.parent
    config_file = Path('/boot') / ('config-' + platform.release())
    config = config_file.read_text() if config_file.is_file() else ''
    features = {key: next((line.partition('=')[2] for line in config.splitlines()
                          if line.startswith('CONFIG_' + symbol + '=')),
                         'n' if '# CONFIG_' + symbol + ' is not set' in config else '?')
                for key, symbol in {'overlay': 'OVERLAY_FS', 'bridge': 'BRIDGE',
                                    'netfilter': 'NETFILTER', 'veth': 'VETH'}.items()}
    ntp = probe(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'])
    sockets = probe(['ss', '-H', '-lnt'])
    if not sockets or sockets.returncode != 0:
        raise RuntimeError('Cannot enumerate listening TCP ports (ss required)')
    ports = set()
    for line in sockets.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4:
            try:
                ports.add(int(fields[3].rsplit(':', 1)[-1]))
            except ValueError:
                continue
    serial_path = Path(serial) if serial else None
    present = bool(serial_path and serial.startswith('/dev/serial/by-id/') and serial_path.is_symlink()
                   and serial_path.resolve().is_char_device())
    holder = probe(['fuser', str(serial_path)]) if present else None
    usb = []
    for device in Path('/sys/bus/usb/devices').glob('*'):
        if (device / 'idVendor').is_file() and (device / 'idProduct').is_file():
            usb.append(device.name + ':' + (device / 'idVendor').read_text().strip() + ':' +
                       (device / 'idProduct').read_text().strip())
    managed = []
    if (root / '.homeauto.json').exists() and ready:
        managed = sorted(owned_services(root))
        # fuser includes the container's host PID. Permit only an exact process
        # listed by Docker for this project's Z2M container, never every holder.
        if holder and holder.returncode == 0 and 'zigbee2mqtt' in managed:
            marker = state(root)
            cid = probe(['docker', 'ps', '--filter', 'label=com.docker.compose.project=' + marker['project'],
                         '--filter', 'label=com.docker.compose.service=zigbee2mqtt', '--format', '{{.ID}}'])
            if cid and cid.returncode == 0 and len(cid.stdout.splitlines()) == 1:
                top = probe(['docker', 'top', cid.stdout.strip(), '-eo', 'pid'])
                if top and top.returncode == 0:
                    owners = set(holder.stdout.split())
                    processes = set(top.stdout.split())
                    if owners and owners <= processes:
                        holder = None
    return dict(managed_services=managed, os=os_data.get('ID', 'unknown'), version=os_data.get('VERSION_ID', 'unknown'),
                arch=platform.machine(), kernel=platform.release(), pages=os.sysconf('SC_PAGE_SIZE'),
                cgroup2=Path('/sys/fs/cgroup/cgroup.controllers').exists(), docker_ready=ready,
                packages=installed, mixed_packages=bool(mixed), features=features,
                free_bytes=shutil.disk_usage(existing).free, writable=os.access(existing, os.W_OK),
                ntp=bool(ntp and ntp.returncode == 0 and ntp.stdout.strip() == 'yes'), ports=ports,
                serial_present=present, serial_busy=bool(holder and holder.returncode == 0),
                serial_descriptor=usb_descriptor(serial_path) if present else None,
                interfaces=sorted(p.name for p in Path('/sys/class/net').glob('*')), usb=sorted(usb))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=['text', 'json'], default='text')
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--profiles', default='')
    parser.add_argument('--zigbee-device', default='')
    parser.add_argument('--zigbee-adapter', choices=['', 'ember', 'zstack'], default='')
    args = parser.parse_args()
    profiles = set(filter(None, args.profiles.split(',')))
    if profiles - {'zigbee', 'extras', 'mariadb', 'actions'}:
        parser.error('Unknown profile')
    try:
        safe_root(args.data_dir)
        rows = checks(collect(args.data_dir, args.zigbee_device), profiles, args.zigbee_adapter)
        code = 2 if any(r['status'] == 'BLOCK' for r in rows) else 1 if any(r['status'] == 'WARN' for r in rows) else 0
        report = dict(schema=1, exit_code=code, checks=rows)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        # Do not include external command output or private input in errors.
        # ValueError/RuntimeError text is our own fixed wording; external output stays suppressed.
        detail = str(exc) if type(exc) in {ValueError, RuntimeError} else type(exc).__name__
        report = dict(schema=1, exit_code=3, checks=[dict(check='evidence', status='ERROR', detail=detail)])
        code = 3
    if args.format == 'json':
        print(json.dumps(report, indent=2))
    else:
        for row in report['checks']:
            print(f"{row['status']:5} {row['check']}: {row['detail']}")
        print(f'Exit {code}: 0 ready, 1 warnings, 2 blocked, 3 evidence error. No host changes made.')
    return code


if __name__ == '__main__':
    sys.exit(main())
