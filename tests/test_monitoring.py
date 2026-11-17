import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/stack'))
sys.path.insert(0, str(ROOT / 'scripts/lib'))
sys.path.insert(0, str(ROOT / 'tests'))
from test_install import install  # noqa: E402
from backup import create_backup  # noqa: E402
from test_recovery import FakeRuntime  # noqa: E402
import offdevice  # noqa: E402
import schedule  # noqa: E402

spec = importlib.util.spec_from_file_location('health', ROOT / 'scripts/monitor/health.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


def facts(**overrides):
    base = dict(services={'homeassistant': dict(State='running', Health='healthy'),
                          'mosquitto': dict(State='running', Health='healthy')},
                profiles=[], bluetooth=False, coordinator_present=True, hci_present=True,
                free_bytes=500 * 1024**3, total_bytes=1000 * 1024**3, backup_age_hours=3.0, copy_age_hours=20.0)
    base.update(overrides)
    return base


def statuses(rows):
    return {r['check']: r['status'] for r in rows}


class HealthTests(unittest.TestCase):
    def evaluate(self, **overrides):
        return statuses(health.evaluate(facts(**overrides), backup_max_hours=36, copy_max_hours=192))

    def test_healthy_core(self):
        self.assertEqual(set(self.evaluate().values()), {'PASS'})

    def test_core_down_fails_but_optional_loss_only_warns(self):
        rows = self.evaluate(services={'mosquitto': dict(State='running', Health='healthy')},
                             profiles=['zigbee'], coordinator_present=False)
        self.assertEqual(rows['service-homeassistant'], 'FAIL')
        self.assertEqual(rows['service-zigbee2mqtt'], 'WARN')
        self.assertEqual(rows['usb-coordinator'], 'WARN')
        rows = self.evaluate(services={**facts()['services'], 'homeassistant': dict(State='running', Health='unhealthy')})
        self.assertEqual(rows['service-homeassistant'], 'FAIL')

    def test_interrupted_backup_marker_fails(self):
        self.assertEqual(self.evaluate(stopped_marker=True)['backup-interrupted'], 'FAIL')
        self.assertNotIn('backup-interrupted', self.evaluate())

    def test_backup_staleness_and_missing_copy(self):
        self.assertEqual(self.evaluate(backup_age_hours=None)['backup'], 'FAIL')
        self.assertEqual(self.evaluate(backup_age_hours=40)['backup'], 'FAIL')
        self.assertEqual(self.evaluate(copy_age_hours=None)['backup-offdevice'], 'WARN')

    def test_storage_thresholds(self):
        self.assertEqual(self.evaluate(free_bytes=150 * 1024**3)['storage'], 'WARN')
        self.assertEqual(self.evaluate(free_bytes=4 * 1024**3)['storage'], 'FAIL')

    def test_age_parsing_rejects_garbage(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'm.json'
            self.assertIsNone(health.age_hours(path, datetime.now(timezone.utc)))
            path.write_text('{"created_utc": "nonsense"}')
            self.assertIsNone(health.age_hours(path, datetime.now(timezone.utc)))


class OffDeviceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root, self.backups, self.target = self.base / 'app', self.base / 'backups', self.base / 'usb'
        self.target.mkdir()
        install.prepare(self.root, [], '', '', False, 'offdevice-test', 'Australia/Sydney')

    def test_same_filesystem_and_same_disk_refused(self):
        with self.assertRaises(ValueError):
            offdevice.check_target(self.target, [self.root])  # temp dirs share a filesystem
        with self.assertRaises(ValueError):
            offdevice.check_target(Path('/media/mediasmb/x'), [self.root])

    def test_partition_on_same_disk_refused_even_if_filesystem_differs(self):
        real = os.stat
        def fake_stat(path, *a, **k):
            st = real(path, *a, **k)
            if Path(path) == self.target:
                return os.stat_result((st.st_mode, st.st_ino, st.st_dev + 1) + tuple(st)[3:])
            return st
        patcher = mock.patch.object(offdevice.os, 'stat', side_effect=fake_stat)
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(ValueError):
            offdevice.check_target(self.target, [self.root], disk=lambda p: 'nvme0n1', fstype=lambda p: 'ext4')
        with self.assertRaises(ValueError):
            offdevice.check_target(self.target, [self.root], disk=lambda p: None, fstype=lambda p: 'tmpfs')
        self.assertEqual(offdevice.check_target(
            self.target, [self.root], disk=lambda p: 'sda' if Path(p) == self.target else 'nvme0n1',
            fstype=lambda p: 'ext4'), 'sda')

    def test_copy_is_verified_private_and_retained(self):
        allow = dict(disk=lambda p: None, fstype=lambda p: 'ext4')
        patcher = mock.patch.object(offdevice, 'check_target', return_value='fixture')
        patcher.start()
        self.addCleanup(patcher.stop)
        archives = []
        for _ in range(3):
            archives.append(create_backup(self.root, self.backups, runtime=FakeRuntime(['homeassistant'])))
        copied = offdevice.copy_latest(self.backups, self.target, [self.root], keep=2, **allow)
        self.assertEqual(copied.name, archives[-1].name)
        self.assertEqual(copied.read_bytes(), archives[-1].read_bytes())
        self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.target / offdevice.SUBDIR).stat().st_mode & 0o777, 0o700)
        marker = json.loads((self.backups / 'last-offdevice.json').read_text())
        self.assertEqual(marker['archive'], copied.name)
        self.assertEqual(len(list(self.backups.glob('homeauto-*.tar.gz'))), 3)  # local never pruned here

    def test_corrupt_source_never_lands_or_updates_marker(self):
        patcher = mock.patch.object(offdevice, 'check_target', return_value='fixture')
        patcher.start()
        self.addCleanup(patcher.stop)
        archive = create_backup(self.root, self.backups, runtime=FakeRuntime(['homeassistant']))
        data = bytearray(archive.read_bytes()); data[len(data) // 2] ^= 0xFF
        archive.write_bytes(bytes(data))
        with self.assertRaises(Exception):
            offdevice.copy_latest(self.backups, self.target, [self.root])
        self.assertFalse(list((self.target / offdevice.SUBDIR).iterdir()))
        self.assertFalse((self.backups / 'last-offdevice.json').exists())


class BackupCopyExitTests(unittest.TestCase):
    def test_copy_failure_exits_4_and_keeps_local_archive(self):
        import backup
        with tempfile.TemporaryDirectory() as temp:
            root, backups = Path(temp) / 'app', Path(temp) / 'backups'
            install.prepare(root, [], '', '', False, 'copy-exit', 'Australia/Sydney')
            real = backup.create_backup
            fake = lambda *a, **k: real(*a, runtime=FakeRuntime(['homeassistant']), **k)
            argv = ['backup.py', '--data-dir', str(root), '--backup-dir', str(backups), '--copy-to', str(Path(temp) / 'missing')]
            with mock.patch.object(backup, 'create_backup', fake), mock.patch.object(sys, 'argv', argv):
                self.assertEqual(backup.main(), 4)
            self.assertEqual(len(list(backups.glob('homeauto-*.tar.gz'))), 1)
            self.assertTrue((backups / 'last-success.json').exists())
            self.assertFalse((backups / 'last-offdevice.json').exists())


class UnitTests(unittest.TestCase):
    def test_units_include_target_and_health_timer_and_verify(self):
        values = schedule.units(Path('/srv/homeauto'), Path('/srv/homeauto-backups'), Path('/mnt/offsite'))
        self.assertIn('--copy-to /mnt/offsite', values['homeauto-backup.service'])
        self.assertIn('RequiresMountsFor=/srv/homeauto /srv/homeauto-backups /mnt/offsite', values['homeauto-backup.service'])
        self.assertIn('--publish', values['homeauto-health.service'])
        self.assertIn('SuccessExitStatus=1', values['homeauto-health.service'])
        plain = schedule.units(Path('/srv/homeauto'), Path('/srv/homeauto-backups'))
        self.assertNotIn('--copy-to', plain['homeauto-backup.service'])

    @unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd-analyze unavailable')
    def test_generated_units_pass_systemd_analyze(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for name, content in schedule.units(Path('/srv/homeauto'), Path('/srv/homeauto-backups')).items():
                path = Path(temp) / name
                path.write_text(content)
                paths.append(str(path))
            result = subprocess.run(['systemd-analyze', 'verify', '--man=no', *paths],
                                    capture_output=True, text=True, timeout=60)
            # Runner images emit diagnostics about their own units (netplan, snapd); judge only ours.
            problems = [l for l in result.stderr.splitlines()
                        if ('homeauto-' in l or temp in l) and 'docker.service' not in l]
            self.assertFalse(problems, '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
