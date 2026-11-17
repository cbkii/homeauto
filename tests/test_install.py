import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from homeauto import env_read, safe_root


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    item = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(item)
    return item


install = module('install', 'scripts/stack/install.py')
preflight = module('preflight', 'scripts/diagnostics/homeauto-preflight.py')


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'app'

    def prepare(self, **kwargs):
        zigbee = 'zigbee' in kwargs.get('profiles', [])
        network = kwargs.get('network', 'new' if zigbee else '')
        rtscts = kwargs.get('rtscts', (kwargs.get('adapter') == 'ember') if zigbee else None)
        return install.prepare(self.root, kwargs.get('profiles', []), kwargs.get('device', ''),
                               kwargs.get('adapter', ''), False, 'homeauto-test', 'Australia/Sydney', network, rtscts)

    def test_plan_and_bad_cli_are_non_mutating(self):
        for flags, code in [([], 0), (['--profiles', 'unknown'], 2), (['--profiles'], 2)]:
            result = subprocess.run([str(ROOT / 'install.sh'), '--data-dir', str(self.root), *flags],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, code)
            self.assertFalse(self.root.exists())

    def test_credentials_and_network_key_survive_rerun(self):
        opts = dict(profiles=['zigbee'], device='/dev/serial/by-id/test', adapter='ember')
        self.assertTrue(self.prepare(**opts))
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertFalse(self.prepare(**opts))
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        credentials = json.loads((self.root / 'secrets.json').read_text())
        self.assertEqual(len(set(credentials.values())), len(credentials))
        z2m = json.loads((self.root / 'zigbee2mqtt/configuration.yaml').read_text())
        self.assertEqual(len(z2m['advanced']['network_key']), 16)
        self.assertEqual(z2m['serial']['adapter'], 'ember')
        for p in ['secrets.json', '.env', 'zigbee2mqtt/configuration.yaml']:
            self.assertEqual((self.root / p).stat().st_mode & 0o777, 0o600)

    def test_existing_data_and_wrong_variant_preserved(self):
        self.root.mkdir()
        original = self.root / 'important'
        original.write_text('existing history')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(original.read_text(), 'existing history')
        original.unlink(); self.root.rmdir()
        self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/test', adapter='zstack')
        with self.assertRaises(ValueError):
            self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/test', adapter='ember')

    def test_zigbee_added_to_existing_core_root_preserves_state(self):
        self.prepare()
        before = {n: (self.root / n).read_bytes() for n in ['secrets.json', 'mosquitto/config/passwd',
                                                            'mosquitto/config/acl', 'compose.yaml']}
        (self.root / 'ha/.storage').mkdir()
        (self.root / 'ha/.storage/onboarding').write_text('{"done": true}')
        (self.root / '.env').write_text((self.root / '.env').read_text().replace(
            'MQTT_BIND_ADDRESS=127.0.0.1', 'MQTT_BIND_ADDRESS=127.0.0.1'))
        self.assertTrue(self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/usb-x-if00-port0', adapter='ember'))
        for name, content in before.items():
            self.assertEqual((self.root / name).read_bytes(), content, name)
        self.assertEqual((self.root / 'ha/.storage/onboarding').read_text(), '{"done": true}')
        marker = json.loads((self.root / '.homeauto.json').read_text())
        self.assertEqual((marker['profiles'], marker['zigbee_adapter'], marker['zigbee_rtscts'], marker['zigbee_network']),
                         (['zigbee'], 'ember', True, 'new'))
        z2m = json.loads((self.root / 'zigbee2mqtt/configuration.yaml').read_text())
        self.assertEqual(z2m['mqtt']['password'], json.loads(before['secrets.json'])['zigbee'])
        self.assertTrue(z2m['serial']['rtscts'])
        env = (self.root / '.env').read_text()
        self.assertIn('ZIGBEE_DEVICE=/dev/serial/by-id/usb-x-if00-port0\n', env)
        self.assertIn('MQTT_BIND_ADDRESS=127.0.0.1\n', env)
        self.assertEqual((self.root / 'zigbee2mqtt/configuration.yaml').stat().st_mode & 0o777, 0o600)
        # Rerun with the same selectors is a no-op; differing adapter refused.
        self.assertFalse(self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/usb-x-if00-port0', adapter='ember'))
        with self.assertRaises(ValueError):
            self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/usb-x-if00-port0', adapter='zstack')

    def test_add_zigbee_validates_before_writing_and_never_after_z2m_ran(self):
        self.prepare()
        marker = (self.root / '.homeauto.json').read_bytes()
        for bad in [dict(device='/dev/ttyUSB0', adapter='ember'), dict(device='/dev/serial/by-id/x', adapter='ember', network=''),
                    dict(device='/dev/serial/by-id/x', adapter='ember', rtscts=None)]:
            with self.assertRaises(ValueError, msg=str(bad)):
                self.prepare(profiles=['zigbee'], **bad)
            self.assertEqual((self.root / '.homeauto.json').read_bytes(), marker)
            self.assertFalse((self.root / 'zigbee2mqtt/configuration.yaml').exists())
        # Partial earlier attempt (config written, marker not): repeatable while Z2M never ran.
        (self.root / 'zigbee2mqtt/configuration.yaml').write_text('{}')
        self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/x', adapter='zstack')
        self.assertIn('zstack', (self.root / 'zigbee2mqtt/configuration.yaml').read_text())
        # A network formed by Z2M must never be regenerated by another add.
        other = Path(self.temp.name) / 'other'
        install.prepare(other, [], '', '', False, 'homeauto-other', 'Australia/Sydney')
        (other / 'zigbee2mqtt/database.db').write_text('formed')
        with self.assertRaises(ValueError):
            install.prepare(other, ['zigbee'], '/dev/serial/by-id/x', 'ember', False, 'homeauto-other',
                            'Australia/Sydney', 'new', True)
        self.assertNotIn('zigbee', json.loads((other / '.homeauto.json').read_text())['profiles'])

    def test_other_profile_changes_still_refused(self):
        self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/x', adapter='ember')
        with self.assertRaises(ValueError):
            self.prepare(profiles=[])  # removal
        root = self.root
        self.root = Path(self.temp.name) / 'core'
        self.prepare()
        with self.assertRaises(ValueError):
            self.prepare(profiles=['mariadb'])  # SQL history needs a backed-up migration, not an add
        with self.assertRaises(ValueError):
            self.prepare(profiles=['zigbee', 'mariadb'], device='/dev/serial/by-id/x', adapter='ember')
        self.root = root

    def test_invalid_variant_and_path_leave_nothing(self):
        with self.assertRaises(ValueError):
            self.prepare(profiles=['zigbee'], device='/dev/ttyUSB0', adapter='ember')
        self.assertFalse(self.root.exists())
        with self.assertRaises(ValueError):
            safe_root(Path('/media/mediasmb/homeauto'))
        self.root.symlink_to(Path(self.temp.name))
        with self.assertRaises(ValueError):
            self.prepare()

    def test_device_path_cannot_inject_environment(self):
        for device in ['/dev/serial/by-id/usb-x\nMQTT_BIND_ADDRESS=0.0.0.0', '/dev/serial/by-id/../../ttyUSB0',
                       '/dev/serial/by-id/a b', '/dev/serial/by-id/']:
            with self.assertRaises(ValueError, msg=repr(device)):
                self.prepare(profiles=['zigbee'], device=device, adapter='ember')
            self.assertFalse(self.root.exists())
        self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/usb-SMLIGHT_SMLIGHT_SLZB-07_0a1b-if00-port0',
                     adapter='ember')
        env = env_read(self.root / '.env')
        self.assertEqual(env['MQTT_BIND_ADDRESS'], '127.0.0.1')

    def test_zigbee_requires_explicit_network_decision(self):
        opts = dict(profiles=['zigbee'], device='/dev/serial/by-id/test', adapter='ember')
        with self.assertRaises(ValueError):
            self.prepare(network='', **opts)
        self.assertFalse(self.root.exists())
        with self.assertRaises(ValueError):
            self.prepare(network='new')  # decision without the zigbee profile
        self.assertFalse(self.root.exists())
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/stack/install.py'), '--prepare',
                                 '--data-dir', str(self.root), '--with-zigbee', '--zigbee-device',
                                 '/dev/serial/by-id/test', '--zigbee-adapter', 'ember', '--zigbee-rtscts', 'true'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--zigbee-network new', result.stderr)
        self.assertFalse(self.root.exists())

    def test_flow_control_is_explicit_recorded_and_written(self):
        opts = dict(profiles=['zigbee'], device='/dev/serial/by-id/test', adapter='ember')
        with self.assertRaisesRegex(ValueError, 'zigbee-rtscts'):
            self.prepare(rtscts=None, **opts)
        self.assertFalse(self.root.exists())
        with self.assertRaises(ValueError):
            self.prepare(rtscts=True)  # without the zigbee profile
        self.prepare(rtscts=True, **opts)
        z2m = json.loads((self.root / 'zigbee2mqtt/configuration.yaml').read_text())
        self.assertIs(z2m['serial']['rtscts'], True)
        self.assertIs(json.loads((self.root / '.homeauto.json').read_text())['zigbee_rtscts'], True)
        with self.assertRaises(ValueError):
            self.prepare(rtscts=False, **opts)  # recorded once; not silently changed

    def test_z2m_schema_version_and_discovery_acl(self):
        self.prepare(profiles=['zigbee'], device='/dev/serial/by-id/test', adapter='ember')
        z2m = json.loads((self.root / 'zigbee2mqtt/configuration.yaml').read_text())
        self.assertEqual(z2m['version'], 5)
        marker = json.loads((self.root / '.homeauto.json').read_text())
        self.assertEqual(marker['zigbee_network'], 'new')
        acl = (self.root / 'mosquitto/config/acl').read_text().split('\n\n')
        zigbee = next(block for block in acl if block.startswith('user zigbee'))
        self.assertIn('topic readwrite homeassistant/#', zigbee)
        self.assertNotIn('ha/actions', zigbee)

    def test_no_shell_execution_or_interpolation(self):
        env = Path(self.temp.name) / 'env'
        env.write_text('X=$(touch unsafe)\n')
        with self.assertRaises(ValueError):
            env_read(env)
        self.assertFalse((ROOT / 'unsafe').exists())


class PreflightTests(unittest.TestCase):
    def facts(self):
        return dict(os='debian', version='13', arch='aarch64', kernel='fixture', pages=4096,
                    cgroup2=True, docker_ready=True, mixed_packages=False, packages=['containerd'],
                    features={'overlay': 'm'}, free_bytes=100 * 1024**3, writable=True, ntp=True,
                    serial_present=False, serial_busy=False, ports=set(), interfaces=['eth0'], usb=[])

    def test_missing_zigbee_never_blocks_core(self):
        core = preflight.checks(self.facts(), set())
        self.assertNotIn('BLOCK', [r['status'] for r in core])
        zigbee = preflight.checks(self.facts(), {'zigbee'})
        self.assertTrue(any(r['check'] == 'coordinator' and r['status'] == 'BLOCK' for r in zigbee))

    def test_docker_conflicts_and_ports_block(self):
        facts = self.facts(); facts.update(docker_ready=False, mixed_packages=True, ports={('0.0.0.0', 8123)})
        rows = preflight.checks(facts, set())
        self.assertEqual(sum(r['status'] == 'BLOCK' for r in rows), 3)

    def test_disabled_kernel_feature_blocks(self):
        facts = self.facts(); facts['features'] = {'bridge': 'n', 'veth': 'm'}
        rows = {r['check']: r for r in preflight.checks(facts, set())}
        self.assertEqual(rows['kernel-bridge']['status'], 'BLOCK')
        self.assertEqual(rows['kernel-veth']['status'], 'WARN')

    def test_coordinator_variant_hint(self):
        cases = {'SLZB-07': 'ember', 'SMLIGHT SLZB-07Mg24': 'ember', 'SLZB-07MG26': 'ember',
                 'SLZB-07p7': 'zstack', 'SLZB-07p10': 'zstack'}
        for product, adapter in cases.items():
            self.assertEqual(preflight.variant_hint(product)[2], adapter, product)
        for product in [None, '', 'CP2102N USB to UART Bridge Controller', 'SLZB-07X', 'SLZB-06p7']:
            self.assertIsNone(preflight.variant_hint(product), product)

    def test_coordinator_variant_mismatch_blocks_only_zigbee(self):
        facts = self.facts()
        facts.update(serial_present=True, serial_descriptor=dict(vid='10c4', pid='ea60', manufacturer='SMLIGHT',
                                                                 product='SLZB-07p7'))
        rows = {r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'ember')}
        self.assertEqual(rows['coordinator-variant']['status'], 'BLOCK')
        rows = {r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'zstack')}
        self.assertEqual(rows['coordinator-variant']['status'], 'PASS')
        # SMLIGHT documents rtscts false for pX and true for MGx.
        self.assertEqual({r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'zstack', False)}
                         ['coordinator-variant']['status'], 'PASS')
        self.assertEqual({r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'zstack', True)}
                         ['coordinator-variant']['status'], 'BLOCK')
        facts['serial_descriptor']['product'] = 'SLZB-07Mg24'
        self.assertEqual({r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'ember', False)}
                         ['coordinator-variant']['status'], 'BLOCK')
        self.assertEqual({r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'ember', True)}
                         ['coordinator-variant']['status'], 'PASS')
        facts['serial_descriptor']['product'] = 'SLZB-07p7'
        facts['serial_descriptor']['product'] = 'CP2102N USB to UART Bridge Controller'
        rows = {r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'ember')}
        self.assertEqual(rows['coordinator-variant']['status'], 'WARN')
        self.assertNotIn('BLOCK', [r['status'] for r in preflight.checks(facts, set(), 'ember')])

    def test_port_collision_is_address_aware(self):
        rows = lambda ports, **kw: {r['check']: r['status'] for r in preflight.checks(
            {**self.facts(), 'ports': ports, **kw}, {'zigbee', 'mariadb'}, 'ember')}
        # LAN-only listeners on loopback-published ports coexist.
        lan = rows({('192.168.1.5', 1883), ('192.168.1.5', 8080), ('192.168.1.5', 3306)})
        self.assertEqual([lan[k] for k in ['port-mosquitto', 'port-zigbee', 'port-mariadb']], ['PASS'] * 3)
        # Wildcard or same-address listeners block; IPv6 wildcard counts.
        self.assertEqual(rows({('::', 1883)})['port-mosquitto'], 'BLOCK')
        self.assertEqual(rows({('127.0.0.1', 8080)})['port-zigbee'], 'BLOCK')
        self.assertEqual(rows({('127.0.0.53', 3306)})['port-mariadb'], 'BLOCK')
        # HA binds every address (host network), so any 8123 listener blocks.
        self.assertEqual(rows({('192.168.1.5', 8123)})['port-homeassistant'], 'BLOCK')
        # An MQTT override to a LAN address collides with that address.
        self.assertEqual(rows({('192.168.1.5', 1883)}, mqtt_bind='192.168.1.5')['port-mosquitto'], 'BLOCK')

    def test_listener_parsing(self):
        cases = {'127.0.0.1:1883': ('127.0.0.1', 1883), '[::]:8123': ('::', 8123), '*:80': ('*', 80),
                 '0.0.0.0%lo:53': ('0.0.0.0', 53), '[fe80::1%eth0]:22': ('fe80::1', 22), 'junk': None}
        for raw, expected in cases.items():
            self.assertEqual(preflight.parse_listener(raw), expected, raw)

    def test_only_debian_12_13_platforms_pass(self):
        for os_id, version, status in [('debian', '13', 'PASS'), ('debian', '12', 'PASS'), ('raspbian', '12', 'PASS'),
                                       ('debian', '11', 'WARN'), ('debian', '14', 'WARN'), ('ubuntu', '24.04', 'WARN')]:
            rows = {r['check']: r['status'] for r in preflight.checks({**self.facts(), 'os': os_id, 'version': version}, set())}
            self.assertEqual(rows['platform'], status, (os_id, version))

    @unittest.skipUnless(__import__('shutil').which('ss'), 'ss (iproute2) unavailable')
    def test_preflight_cli_reports_json_without_host_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/diagnostics/homeauto-preflight.py'),
                                     '--format', 'json', '--data-dir', str(Path(temp) / 'absent')],
                                    capture_output=True, text=True, timeout=120)
            report = json.loads(result.stdout)
            self.assertIn(result.returncode, {0, 1, 2})  # 3 would be an evidence/collection error
            self.assertEqual(report['exit_code'], result.returncode)
            self.assertTrue({'platform', 'docker', 'storage', 'port-homeassistant'} <= {c['check'] for c in report['checks']})
            self.assertFalse((Path(temp) / 'absent').exists())

    def test_existing_managed_port_warns(self):
        facts = self.facts(); facts.update(ports={('0.0.0.0', 8123)}, managed_services=['homeassistant'])
        self.assertNotIn('BLOCK', [r['status'] for r in preflight.checks(facts, set())])

class LifecycleTests(unittest.TestCase):
    def test_project_root_collision_is_rejected(self):
        from unittest.mock import patch
        import homeauto
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            install.prepare(root, [], '', '', False, 'same-project', 'Australia/Sydney')
            def fake(argv, **kwargs):
                if argv[1] == 'ps':
                    return subprocess.CompletedProcess(argv, 0, 'a' * 12 + '\n', '')
                return subprocess.CompletedProcess(argv, 0, json.dumps({
                    'com.docker.compose.project.config_files': '/other/compose.yaml',
                    'com.docker.compose.project.working_dir': '/other',
                    'com.docker.compose.service': 'homeassistant'}), '')
            with patch.object(homeauto, 'run', side_effect=fake):
                with self.assertRaises(ValueError):
                    homeauto.owned_services(root)

    def test_configured_but_absent_dongle_starts_core(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            install.prepare(root, ['zigbee'], '/dev/serial/by-id/absent', 'ember', False,
                            'isolated-test', 'Australia/Sydney', 'new', True)
            calls = []
            def fake(argv, **kwargs):
                calls.append(argv)
                code = 2 if '--profiles' in argv else 0
                return subprocess.CompletedProcess(argv, code, '', '')
            with patch.object(install, 'owned_services', return_value=set()), patch.object(install, 'run', side_effect=fake):
                self.assertEqual(install.apply(root), 1)
            starts = [a for a in calls if 'up' in a]
            self.assertEqual(len(starts), 1)
            self.assertEqual(starts[0][-2:], ['homeassistant', 'mosquitto'])

    def test_unacknowledged_first_zigbee_start_is_blocked_but_core_runs(self):
        """Roots prepared before the acknowledgement existed must not form a network."""
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            install.prepare(root, ['zigbee'], '/dev/serial/by-id/present', 'ember', False,
                            'legacy-marker', 'Australia/Sydney', 'new', True)
            marker = json.loads((root / '.homeauto.json').read_text())
            del marker['zigbee_network']
            (root / '.homeauto.json').write_text(json.dumps(marker))
            calls = []
            def fake(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, '', '')
            with patch.object(install, 'owned_services', return_value=set()), patch.object(install, 'run', side_effect=fake):
                self.assertEqual(install.apply(root), 1)
            self.assertFalse(any('zigbee2mqtt' in a for a in calls if 'up' in a))
            (root / 'zigbee2mqtt/coordinator_backup.json').write_text('{}')  # network already formed by Z2M
            calls.clear()
            with patch.object(install, 'owned_services', return_value=set()), patch.object(install, 'run', side_effect=fake):
                self.assertEqual(install.apply(root), 0)
            self.assertTrue(any('zigbee2mqtt' in a for a in calls if 'up' in a))


if __name__ == '__main__':
    unittest.main()
