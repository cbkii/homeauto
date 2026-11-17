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
        network = kwargs.get('network', 'new' if 'zigbee' in kwargs.get('profiles', []) else '')
        return install.prepare(self.root, kwargs.get('profiles', []), kwargs.get('device', ''),
                               kwargs.get('adapter', ''), False, 'homeauto-test', 'Australia/Sydney', network)

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

    def test_invalid_variant_and_path_leave_nothing(self):
        with self.assertRaises(ValueError):
            self.prepare(profiles=['zigbee'], device='/dev/ttyUSB0', adapter='ember')
        self.assertFalse(self.root.exists())
        with self.assertRaises(ValueError):
            safe_root(Path('/media/mediasmb/homeauto'))
        self.root.symlink_to(Path(self.temp.name))
        with self.assertRaises(ValueError):
            self.prepare()

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
                                 '/dev/serial/by-id/test', '--zigbee-adapter', 'ember'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--zigbee-network new', result.stderr)
        self.assertFalse(self.root.exists())

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
        facts = self.facts(); facts.update(docker_ready=False, mixed_packages=True, ports={8123})
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
        facts['serial_descriptor']['product'] = 'CP2102N USB to UART Bridge Controller'
        rows = {r['check']: r for r in preflight.checks(facts, {'zigbee'}, 'ember')}
        self.assertEqual(rows['coordinator-variant']['status'], 'WARN')
        self.assertNotIn('BLOCK', [r['status'] for r in preflight.checks(facts, set(), 'ember')])

    def test_existing_managed_port_warns(self):
        facts = self.facts(); facts.update(ports={8123}, managed_services=['homeassistant'])
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
                            'isolated-test', 'Australia/Sydney', 'new')
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
                            'legacy-marker', 'Australia/Sydney', 'new')
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
