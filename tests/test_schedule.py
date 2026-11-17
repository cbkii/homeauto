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
import schedule  # noqa: E402


def ok(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 0, '', '')


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.root, self.backups, self.units = base / 'app', base / 'backups', base / 'units'
        self.units.mkdir()
        install.prepare(self.root, [], '', '', False, 'schedule-test', 'Australia/Sydney')

    def install(self):
        return schedule.install(self.root, self.backups, self.units, runner=ok)

    def test_install_is_idempotent_and_unit_contents_are_safe(self):
        self.assertEqual(sorted(self.install()), ['homeauto-backup.service', 'homeauto-backup.timer', 'homeauto-health.service', 'homeauto-health.timer'])
        self.assertEqual(self.install(), [])  # identical: no-op
        service = (self.units / 'homeauto-backup.service').read_text()
        for needle in ['ExecStopPost=', '--resume', 'KillMode=mixed', 'TimeoutStopSec=10min',
                       'ProtectHome=read-only', f'ReadWritePaths={self.root} {self.backups}',
                       f'RequiresMountsFor={self.root} {self.backups}']:
            self.assertIn(needle, service)
        self.assertEqual(self.backups.stat().st_mode & 0o777, 0o700)

    def test_differing_timer_blocks_before_any_write(self):
        (self.units / 'homeauto-backup.timer').write_text('[Timer]\nOnCalendar=hourly\n')
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse((self.units / 'homeauto-backup.service').exists())  # no orphan
        self.assertFalse(self.backups.exists())

    def test_write_failure_rolls_back_partial_install(self):
        real = schedule.atomic
        calls = []
        def flaky(path, content, mode=0o600):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('disk full')
            real(path, content, mode)
        with mock.patch.object(schedule, 'atomic', flaky):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse(list(self.units.iterdir()))

    def test_insecure_existing_destination_and_home_paths_refused(self):
        self.backups.mkdir(mode=0o755)
        self.backups.chmod(0o755)
        with self.assertRaises(ValueError):
            self.install()
        for bad in [Path('/home/pipi/backups'), Path('/root/backups'), Path('/srv/../srv/x')]:
            with self.assertRaises(ValueError, msg=str(bad)):
                schedule.check_paths(self.root, bad)
        with self.assertRaises(ValueError):
            schedule.check_paths(self.root, self.root / 'nested')

    def test_remove_is_idempotent_and_spares_foreign_units(self):
        self.assertEqual(schedule.remove(self.units, runner=ok), [])
        self.install()
        calls = []
        def record(argv, **kwargs):
            calls.append(argv); return ok(argv)
        self.assertEqual(sorted(schedule.remove(self.units, runner=record)),
                         ['homeauto-backup.service', 'homeauto-backup.timer', 'homeauto-health.service', 'homeauto-health.timer'])
        self.assertIn(['systemctl', 'disable', '--now', 'homeauto-backup.timer', 'homeauto-health.timer'], calls)
        self.assertFalse(list(self.units.iterdir()))
        (self.units / 'homeauto-backup.timer').write_text('[Timer]\n')  # someone else's unit
        with self.assertRaises(ValueError):
            schedule.remove(self.units, runner=ok)
        self.assertTrue((self.units / 'homeauto-backup.timer').exists())

    def test_partial_previous_install_removed(self):
        self.install()
        for name in ['homeauto-backup.timer', 'homeauto-health.service', 'homeauto-health.timer']:
            (self.units / name).unlink()
        self.assertEqual(schedule.remove(self.units, runner=ok), ['homeauto-backup.service'])

    @unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd-analyze unavailable')
    def test_generated_units_pass_systemd_analyze(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for name, content in schedule.units(Path('/srv/homeauto'), Path('/srv/homeauto-backups')).items():
                (Path(temp) / name).write_text(content)
                paths.append(str(Path(temp) / name))
            result = subprocess.run(['systemd-analyze', 'verify', '--man=no', *paths],
                                    capture_output=True, text=True, timeout=60)
            # Runner images report problems in their own units; judge only ours.
            problems = [line for line in result.stderr.splitlines()
                        if ('homeauto-' in line or temp in line) and 'docker.service' not in line]
            self.assertFalse(problems, '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
