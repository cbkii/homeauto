#!/usr/bin/env python3
"""Read-only, redacted Q8B commissioning report for homeauto (stdlib only).

Default mode changes nothing: no packages, services, network, firewall, mounts, fan/GPIO,
UART or radio contact. Serial numbers are replaced by a short one-way tag (to compare runs, e.g. after replugging);
MAC, IPv4 and IPv6 addresses are reduced to a class; the hostname is never read.
Each section is labelled with its evidence class:
  ENUMERATION  read from /proc, /sys, os-release or a tool's status output
  RUNTIME      state reported by a running daemon (Docker, systemd)
  TRANSACTION  only with --docker-smoke: disposable containers/network, then removed
  UNAVAILABLE  tool or path missing / permission denied
Run as root for complete Docker/serial-holder evidence:
  sudo python3 scripts/diagnostics/q8b-report.py --data-dir /srv/homeauto > q8b-report.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
PORTS = {'homeassistant': 8123, 'mosquitto': 1883, 'zigbee2mqtt': 8080, 'mariadb': 3306,
         'esphome': 6052, 'nodered': 1880}
# module -> Kconfig symbol, so built-in support is distinguishable from missing support.
MODULES = {'overlay': 'OVERLAY_FS', 'bridge': 'BRIDGE', 'br_netfilter': 'BRIDGE_NETFILTER', 'veth': 'VETH',
           'nf_tables': 'NF_TABLES', 'nft_nat': 'NFT_NAT', 'nf_nat': 'NF_NAT', 'nf_conntrack': 'NF_CONNTRACK',
           'ip_tables': 'IP_NF_IPTABLES', 'iptable_nat': 'IP_NF_NAT',
           'xt_MASQUERADE': 'NETFILTER_XT_TARGET_MASQUERADE', 'xt_conntrack': 'NETFILTER_XT_MATCH_CONNTRACK',
           'cp210x': 'USB_SERIAL_CP210X', 'btusb': 'BT_HCIBTUSB', 'btrtl': 'BT_RTL'}
SERIAL_GRABBERS = ['ModemManager.service', 'brltty.service', 'brltty-udev.service']


def tag(value: str) -> str:
    return 'h' + hashlib.sha256(value.encode()).hexdigest()[:8]


IPV6 = re.compile(r'(?i)(?<![0-9a-f:])(?:(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}'
                  r'|(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4})*)?)(?![0-9a-f:])')


def redact(text: str) -> str:
    text = re.sub(r'(?i)\b([0-9a-f]{2}:){5}[0-9a-f]{2}\b', 'MAC-REDACTED', text)
    text = re.sub(r'\b(\d{1,3}\.){3}\d{1,3}\b', lambda m: address_class(m.group(0)), text)
    return IPV6.sub(lambda m: address_class(m.group(0).lower()) if len(m.group(0)) > 2 else m.group(0), text)


def address_class(address: str) -> str:
    if address in {'0.0.0.0', '::', '*', ''}:
        return 'ANY'
    if address.startswith('127.') or address == '::1':
        return 'LOOPBACK'
    if re.match(r'^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|fe80:|fd)', address):
        return 'PRIVATE'
    return 'OTHER'


def run(argv: list[str], timeout: int = 20) -> tuple[int, str]:
    if not shutil.which(argv[0]):
        return 127, ''
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 124, ''


def read(path: Path, limit: int = 4096) -> str | None:
    try:
        return path.read_text(errors='replace')[:limit].strip()
    except OSError:
        return None


def section(cls: str, **data) -> dict:
    return dict(evidence=cls, **data)


def identity() -> dict:
    osr = dict(line.split('=', 1) for line in (read(Path('/etc/os-release')) or '').splitlines() if '=' in line)
    mem = re.search(r'MemTotal:\s+(\d+)', read(Path('/proc/meminfo')) or '')
    return section('ENUMERATION', os=osr.get('ID', '?').strip('"'), version=osr.get('VERSION_ID', '?').strip('"'),
                   pretty=osr.get('PRETTY_NAME', '?').strip('"'), kernel=platform.release(), arch=platform.machine(),
                   page_size=os.sysconf('SC_PAGE_SIZE'), mem_gib=round(int(mem.group(1)) / 1024**2, 1) if mem else None,
                   model=read(Path('/proc/device-tree/model')) or read(Path('/sys/class/dmi/id/product_name')),
                   uptime_h=round(float((read(Path('/proc/uptime')) or '0').split()[0]) / 3600, 1))


def docker() -> dict:
    code, out = run(['docker', 'info', '--format', '{{json .}}'], 30)
    if code:
        return section('UNAVAILABLE', detail='docker info failed (daemon down, CLI missing or not root)', code=code)
    info = json.loads(out)
    compose = run(['docker', 'compose', 'version', '--short'])[1].strip()
    packages = {}
    for pkg in ['docker.io', 'docker-ce', 'docker-ce-cli', 'docker-compose', 'docker-compose-plugin',
                'containerd', 'containerd.io', 'runc', 'podman-docker']:
        c, o = run(['dpkg-query', '-W', '-f=${Status} ${Version}', pkg])
        if c == 0 and o.startswith('install ok installed'):
            packages[pkg] = o.split()[-1]
    return section('RUNTIME', server=info.get('ServerVersion'), compose=compose or None,
                   storage_driver=info.get('Driver'), cgroup_driver=info.get('CgroupDriver'),
                   cgroup_version=info.get('CgroupVersion'), security=info.get('SecurityOptions'),
                   default_runtime=info.get('DefaultRuntime'), arch=info.get('Architecture'),
                   containers=dict(running=info.get('ContainersRunning'), total=info.get('Containers')),
                   warnings=[redact(w) for w in info.get('Warnings') or []], packages=packages,
                   daemon_json_present=Path('/etc/docker/daemon.json').exists(),
                   enabled=run(['systemctl', 'is-enabled', 'docker.service'])[1].strip() or None,
                   active=run(['systemctl', 'is-active', 'docker.service'])[1].strip() or None)


def kernel_net() -> dict:
    loaded = {line.split()[0] for line in (read(Path('/proc/modules'), 200000) or '').splitlines() if line}
    config = read(Path(f'/boot/config-{platform.release()}'), 2_000_000)
    if config is None and Path('/proc/config.gz').exists():
        import gzip
        try:
            config = gzip.decompress(Path('/proc/config.gz').read_bytes()).decode(errors='replace')
        except OSError:
            config = None
    def state(mod, symbol):
        if mod in loaded:
            return 'loaded'
        if config is None:
            return 'unknown (no kernel config readable)'
        value = re.search(rf'^CONFIG_{symbol}=(\w)', config, re.M)
        return {'y': 'builtin', 'm': 'module-not-loaded'}.get(value.group(1) if value else '', 'disabled')
    iptables = run(['iptables', '--version'])[1].strip()
    return section('ENUMERATION', modules={m: state(m, k) for m, k in MODULES.items()},
                   kernel_config='readable' if config is not None else 'unavailable',
                   cgroup2=Path('/sys/fs/cgroup/cgroup.controllers').exists(),
                   cgroup_controllers=(read(Path('/sys/fs/cgroup/cgroup.controllers')) or '').split(),
                   ip_forward=read(Path('/proc/sys/net/ipv4/ip_forward')),
                   bridge_nf_call_iptables=read(Path('/proc/sys/net/bridge/bridge-nf-call-iptables')),
                   nft=bool(shutil.which('nft')), iptables=iptables or None,
                   iptables_backend='nf_tables' if 'nf_tables' in iptables else 'legacy' if 'legacy' in iptables else None)


def storage(paths: list[str]) -> dict:
    out = {}
    for path in paths:
        code, text = run(['findmnt', '-J', '-T', path, '-o', 'TARGET,SOURCE,FSTYPE,OPTIONS'])
        fs = json.loads(text)['filesystems'][0] if code == 0 and text.strip() else {}
        exists = Path(path).exists()
        free = shutil.disk_usage(path) if exists else None
        source = fs.get('source') or ''
        out[path] = dict(exists=exists, mount_target=fs.get('target'), fstype=fs.get('fstype'),
                         source=re.sub(r'^/dev/', '', source) if source.startswith('/dev/') else ('other' if source else None),
                         read_only='ro' in (fs.get('options') or '').split(','),
                         free_gib=round(free.free / 1024**3, 1) if free else None,
                         is_mountpoint=os.path.ismount(path) if exists else False)
    return section('ENUMERATION', paths=out)


def ports() -> dict:
    code, text = run(['ss', '-H', '-lnt'])
    if code:
        return section('UNAVAILABLE', detail='ss (iproute2) missing')
    found = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        address, _, port = fields[3].rpartition(':')
        if port.isdigit() and int(port) in PORTS.values():
            found.setdefault(int(port), set()).add(address_class(address.strip('[]').split('%')[0]))
    return section('ENUMERATION', listeners={name: sorted(found.get(port, [])) or 'free' for name, port in PORTS.items()})


def shown_by_id(name: str) -> str:
    """usb-<manufacturer>_<product>_<serial>-if00-port0: replace only the serial with a tag."""
    match = re.match(r'^(usb-.+?)_([A-Za-z0-9]{6,})(-if\d+.*)$', name)
    return f'{match.group(1)}_{tag(match.group(2))}{match.group(3)}' if match else tag(name)


def usb_node(tty: str) -> Path | None:
    try:
        node = (Path('/sys/class/tty') / tty / 'device').resolve()
    except OSError:
        return None
    while node != node.parent and not (node / 'idVendor').is_file():
        node = node.parent
    return node if (node / 'idVendor').is_file() else None


def serial(adapter: str) -> dict:
    sys.path.insert(0, str(REPO / 'scripts/diagnostics'))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('preflight', REPO / 'scripts/diagnostics/homeauto-preflight.py')
        preflight = importlib.util.module_from_spec(spec); spec.loader.exec_module(preflight)
        hint = preflight.variant_hint
        flow = preflight.SLZB07_RTSCTS
    except Exception:  # noqa: BLE001 - report must not depend on the rest of the checkout
        hint, flow = (lambda product: None), {}  # noqa: E731
    by_id = Path('/dev/serial/by-id')
    devices = []
    for link in sorted(by_id.iterdir()) if by_id.is_dir() else []:
        shown = shown_by_id(link.name)
        tty = link.resolve().name
        node = usb_node(tty)
        attr = (lambda a: (read(node / a) or '') if node else '')
        driver_link = Path('/sys/class/tty') / tty / 'device/driver'
        holders = run(['fuser', str(link)])[1].split()
        variant = hint(attr('product'))
        devices.append(dict(by_id=shown, tty=tty, vid_pid=f"{attr('idVendor')}:{attr('idProduct')}",
                            manufacturer=attr('manufacturer'), product=attr('product'),
                            driver=driver_link.resolve().name if driver_link.exists() else None,
                            usb_path=node.name if node else None, speed_mbps=attr('speed') or None,
                            holder_pids=len(holders),
                            variant_hint=dict(variant=variant[0], radio=variant[1], adapter=variant[2],
                                              documented_rtscts=flow.get(variant[2])) if variant else None,
                            adapter_matches=(variant[2] == adapter) if variant and adapter else None))
    grabbers = {unit: run(['systemctl', 'is-active', unit])[1].strip() or 'unknown' for unit in SERIAL_GRABBERS}
    return section('ENUMERATION', devices=devices, serial_grabbers=grabbers,
                   note='USB descriptors only; radio firmware and network state need a separately approved probe')


def bluetooth() -> dict:
    controllers = []
    for hci in sorted(Path('/sys/class/bluetooth').glob('hci*')):
        node = usb_node_from(hci / 'device')
        controllers.append(dict(name=hci.name, vid_pid=f"{read(node / 'idVendor')}:{read(node / 'idProduct')}" if node else None))
    rfkill = [dict(type=read(r / 'type'), soft=read(r / 'soft'), hard=read(r / 'hard'))
              for r in sorted(Path('/sys/class/rfkill').glob('rfkill*'))]
    return section('ENUMERATION', controllers=controllers, rfkill=rfkill,
                   bluetooth_service=run(['systemctl', 'is-active', 'bluetooth.service'])[1].strip() or None,
                   note='Optional: must not gate core boot')


def usb_node_from(path: Path) -> Path | None:
    try:
        node = path.resolve()
    except OSError:
        return None
    while node != node.parent and not (node / 'idVendor').is_file():
        node = node.parent
    return node if (node / 'idVendor').is_file() else None


def thermal() -> dict:
    zones = []
    for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
        temp = read(zone / 'temp')
        zones.append(dict(zone=zone.name, type=read(zone / 'type'),
                          celsius=round(int(temp) / 1000, 1) if temp and temp.lstrip('-').isdigit() else None))
    fans = []
    for fan in sorted(Path('/sys/class/hwmon').glob('hwmon*/fan*_input')):
        value = read(fan)
        fans.append(dict(sensor=f'{fan.parent.name}/{fan.name}', rpm=int(value) if value and value.isdigit() else None))
    hottest = max((z['celsius'] for z in zones if z['celsius'] is not None), default=None)
    return section('ENUMERATION', zones=zones, fans=fans, hottest_celsius=hottest,
                   load=read(Path('/proc/loadavg')), note='Instantaneous reading; not a sustained-load qualification')


def images() -> dict:
    """Pinned images from the checkout: present locally? Architecture as Docker reports it."""
    compose_file = REPO / 'docker-compose.yml'
    pinned = sorted(set(re.findall(r'^\s*image:\s*(\S+)', compose_file.read_text(), re.M))) if compose_file.is_file() else []
    out = {}
    for image in pinned:
        code, text = run(['docker', 'image', 'inspect', '--format', '{{.Os}}/{{.Architecture}}{{if .Variant}}/{{.Variant}}{{end}}', image])
        out[image] = text.strip() if code == 0 else 'not pulled'
    return section('RUNTIME', host_arch=platform.machine(), images=out,
                   note='Pulled at --apply; registry manifests for linux/arm64 are checked in CI')


def system_units() -> dict:
    code, out = run(['systemctl', '--failed', '--plain', '--no-legend', '--no-pager'])
    ntp = run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'])[1].strip() or None
    return section('RUNTIME' if code == 0 else 'UNAVAILABLE', ntp_synchronized=ntp,
                   failed_units=[line.split()[0] for line in out.splitlines() if line.strip()],
                   pd_mapper=run(['systemctl', 'is-active', 'pd-mapper.service'])[1].strip() or None)


def homeauto(root: Path) -> dict:
    marker = root / '.homeauto.json'
    if not marker.is_file():
        return section('ENUMERATION', prepared=False, root=str(root))
    data = json.loads(marker.read_text())
    out = dict(prepared=True, root=str(root), profiles=data.get('profiles'), project=data.get('project'),
               bluetooth=data.get('bluetooth'), zigbee_adapter=data.get('zigbee_adapter') or None,
               zigbee_rtscts=data.get('zigbee_rtscts'), zigbee_network=data.get('zigbee_network'),
               zigbee_device_set=bool(data.get('zigbee_device')),
               z2m_network_formed=(root / 'zigbee2mqtt/coordinator_backup.json').exists(),
               backup_interrupted_marker=(root / '.backup-stopped.json').exists())
    code, text = run(['docker', 'compose', '-p', data.get('project', 'homeauto'), 'ps', '--all', '--format', 'json'], 30)
    if code == 0:
        rows = json.loads(text) if text.strip().startswith('[') else [json.loads(l) for l in text.splitlines() if l.strip()]
        out['services'] = {r['Service']: f"{r['State']}/{r.get('Health') or '-'}" for r in rows}
    return section('RUNTIME' if code == 0 else 'ENUMERATION', **out)


def docker_smoke(image: str) -> dict:
    """TRANSACTION: disposable bridge network + broker + client by DNS name, then removed."""
    suffix = secrets.token_hex(4)
    net, broker = f'homeauto-smoke-{suffix}', f'homeauto-smoke-broker-{suffix}'
    import socket
    with socket.socket() as probe:  # a currently free loopback port for the publish test
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    steps, ok = [], False
    def step(name, argv, timeout=120):
        code, _ = run(argv, timeout)
        steps.append(dict(step=name, ok=code == 0))
        return code == 0
    retry = 'for i in 1 2 3 4 5 6 7 8 9 10; do mosquitto_pub -h {h} -p {p} -t smoke -m ok && exit 0; sleep 1; done; exit 1'
    try:
        ok = (step('create bridge network', ['docker', 'network', 'create', '--driver', 'bridge', net]) and
              step('start broker on bridge, published on 127.0.0.1 only',
                   ['docker', 'run', '-d', '--name', broker, '--network', net, '-p', f'127.0.0.1:{port}:1883',
                    image, 'mosquitto', '-c', '/mosquitto-no-auth.conf']) and
              step('container -> container by DNS name (bridge, veth, embedded DNS)',
                   ['docker', 'run', '--rm', '--network', net, image, 'sh', '-c', retry.format(h=broker, p=1883)],
                   timeout=180) and
              step('host netns -> loopback-published port (Docker NAT/proxy, nftables/iptables)',
                   ['docker', 'run', '--rm', '--network', 'host', image, 'sh', '-c', retry.format(h='127.0.0.1', p=port)],
                   timeout=180))
    finally:
        run(['docker', 'rm', '-f', broker], 60)
        run(['docker', 'network', 'rm', net], 60)
    leftovers = run(['docker', 'ps', '-a', '--filter', f'name={suffix}', '--format', '{{.ID}}'])[1].strip()
    return section('TRANSACTION', image=image, steps=steps, passed=bool(ok) and not leftovers,
                   cleaned_up=not leftovers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--zigbee-adapter', choices=['', 'ember', 'zstack'], default='')
    parser.add_argument('--docker-smoke', action='store_true',
                        help='TRANSACTION: disposable network/containers using the pinned Mosquitto image, then removed')
    args = parser.parse_args()
    image = 'eclipse-mosquitto:2.0.22'
    compose_file = REPO / 'docker-compose.yml'
    if compose_file.is_file():
        found = re.search(r'image:\s*(eclipse-mosquitto:\S+)', compose_file.read_text())
        image = found.group(1) if found else image
    report = dict(schema=1, generated_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                  euid=os.geteuid(), repo_commit=run(['git', '-C', str(REPO), 'rev-parse', '--short', 'HEAD'])[1].strip() or None)
    for name, func in [('identity', identity), ('docker', docker), ('kernel_network', kernel_net),
                       ('storage', lambda: storage(['/', '/srv', '/var/lib/docker', '/media/mediasmb', str(args.data_dir)])),
                       ('ports', ports), ('serial', lambda: serial(args.zigbee_adapter)), ('bluetooth', bluetooth),
                       ('thermal', thermal), ('systemd', system_units), ('images', images), ('homeauto', lambda: homeauto(args.data_dir))]:
        try:
            report[name] = func()
        except Exception as exc:  # noqa: BLE001 - one failed section must not hide the rest
            report[name] = section('UNAVAILABLE', detail=type(exc).__name__)
    if args.docker_smoke:
        report['docker_smoke'] = docker_smoke(image)
    text = json.dumps(report, indent=2, default=list)
    print(redact(text))
    return 0


if __name__ == '__main__':
    sys.exit(main())
