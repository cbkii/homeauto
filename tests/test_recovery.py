import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import sqlite3
import tarfile
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/stack'))
sys.path.insert(0, str(ROOT / 'tests'))
from test_install import install
from backup import create_backup
from restore import restore, verify


class FakeRuntime:
    def __init__(self, services=None, fail_dump=False, fail_stop=False, fail_start=False):
        self.running = set(services or [])
        self.fail_dump = fail_dump
        self.fail_stop = fail_stop
        self.fail_start = fail_start
        self.stops = []; self.starts = []

    def rows(self):
        return [dict(Service=s, State='running') for s in self.running]

    def images(self):
        return {s: 'sha256:fixture' for s in self.running}

    def stop(self, services):
        self.stops.append(list(services))
        self.running -= set(services)
        if self.fail_stop:
            raise RuntimeError('stop failed')

    def start(self, services):
        self.starts.append(list(services))
        if self.fail_start:
            raise RuntimeError('restart failed')
        self.running |= set(services)

    def dump(self, path):
        if self.fail_dump:
            path.write_text('partial')
            raise RuntimeError('dump failed')
        path.write_text('-- SQL dump\n' + 'valid SQL;\n' * 50)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'app'
        self.destination = self.parent / 'backups'

    def prepare(self, profiles=None):
        install.prepare(self.root, profiles or [], '', '', False, 'backup-test', 'Australia/Sydney')
        with sqlite3.connect(self.root / 'ha/test.db') as db:
            db.execute('CREATE TABLE events (value TEXT)')
            db.execute("INSERT INTO events VALUES ('actual history')")

    def test_snapshot_restore_is_private_and_preserves_state(self):
        self.prepare()
        runtime = FakeRuntime(['homeassistant', 'mosquitto'])
        path = create_backup(self.root, self.destination, runtime=runtime)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(runtime.running, {'homeassistant', 'mosquitto'})
        self.assertEqual(verify(path)['db_logical_dump_status'], 'not-enabled')
        target = self.parent / 'rehearsal'
        restore(path, target)
        for relative in ['ha/test.db', 'secrets.json', '.homeauto.json']:
            self.assertEqual((self.root / relative).read_bytes(), (target / relative).read_bytes())
        with sqlite3.connect(target / 'ha/test.db') as db:
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT value FROM events').fetchone()[0], 'actual history')
        with self.assertRaises(ValueError):
            restore(path, target)

    def test_dump_failure_never_publishes_success_and_resumes_writers(self):
        self.prepare(['mariadb'])
        runtime = FakeRuntime(['homeassistant', 'mosquitto', 'mariadb'], fail_dump=True)
        with self.assertRaises(RuntimeError):
            create_backup(self.root, self.destination, runtime=runtime)
        self.assertFalse(list(self.destination.glob('*.tar.gz')))
        self.assertFalse((self.destination / 'last-success.json').exists())
        self.assertEqual(runtime.running, {'homeassistant', 'mosquitto', 'mariadb'})
        self.assertFalse(list(self.destination.glob('.homeauto-backup-*')))

    def test_missing_required_database_and_stop_failure(self):
        self.prepare(['mariadb'])
        with self.assertRaises(ValueError):
            create_backup(self.root, self.destination, runtime=FakeRuntime(['homeassistant']))
        runtime = FakeRuntime(['homeassistant', 'mariadb'], fail_stop=True)
        with self.assertRaises(RuntimeError):
            create_backup(self.root, self.destination, runtime=runtime)
        self.assertEqual(runtime.running, {'homeassistant', 'mariadb'})
        self.assertFalse(list(self.destination.glob('*.tar.gz')))

    def test_online_sql_and_offline_are_truthfully_distinguished(self):
        self.prepare(['mariadb'])
        path = create_backup(self.root, self.destination, runtime=FakeRuntime(['homeassistant', 'mariadb']))
        self.assertEqual(verify(path)['db_logical_dump_status'], 'ok')
        path = create_backup(self.root, self.destination, runtime=FakeRuntime(), offline=True)
        self.assertEqual(verify(path)['db_logical_dump_status'], 'cold-snapshot-only')

    def test_link_and_manifest_traversal_rejected(self):
        self.prepare()
        (self.root / 'link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):
            create_backup(self.root, self.destination, runtime=FakeRuntime())
        bad = self.parent / 'bad.tar.gz'
        with tarfile.open(bad, 'w:gz') as tar:
            item = tarfile.TarInfo('../escape')
            item.size = 1; tar.addfile(item, io.BytesIO(b'x'))
        with self.assertRaises(ValueError):
            verify(bad)

    def test_dry_run_does_not_create_destination(self):
        self.prepare()
        self.assertIsNone(create_backup(self.root, self.destination, dry_run=True))
        self.assertFalse(self.destination.exists())


class TransitionalStateTests(unittest.TestCase):
    def test_transitional_states_never_publish_even_in_offline_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            install.prepare(root, [], '', '', False, 'transition-test', 'Australia/Sydney')
            for status in ['restarting', 'paused', 'removing']:
                runtime = FakeRuntime()
                runtime.rows = lambda: [dict(Service='homeassistant', State=status)]
                for offline in [False, True]:
                    with self.assertRaises(ValueError):
                        create_backup(root, Path(temp) / 'backups', runtime=runtime, offline=offline)
            self.assertFalse((Path(temp) / 'backups').exists())


class RuntimeStopPredicateTests(unittest.TestCase):
    """Regression: real Runtime.stop must ignore MariaDB kept running for the dump."""
    def runtime(self, states):
        import backup
        runtime = backup.Runtime.__new__(backup.Runtime)
        runtime.root = Path('/unused')
        runtime.rows = lambda: [dict(Service=s, State=v) for s, v in states.items()]
        original = backup.run, backup.compose
        backup.run = lambda argv, **kw: type('R', (), dict(returncode=0, stdout='', stderr=''))()
        backup.compose = lambda root, *args: ['docker', 'compose', *args]
        self.addCleanup(lambda: setattr(backup, 'run', original[0]))
        self.addCleanup(lambda: setattr(backup, 'compose', original[1]))
        return runtime

    def test_database_left_running_is_not_a_stop_failure(self):
        self.runtime(dict(homeassistant='exited', mosquitto='exited', mariadb='running')).stop(['homeassistant', 'mosquitto'])

    def test_requested_writer_still_running_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.runtime(dict(homeassistant='running', mariadb='running')).stop(['homeassistant'])

    def test_requested_writer_missing_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.runtime(dict(mariadb='running')).stop(['homeassistant'])


class SlowRecoveryTests(unittest.TestCase):
    def test_verified_archive_kept_but_success_marker_withheld(self):
        import backup
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            destination = Path(temp) / 'backups'
            install.prepare(root, [], '', '', False, 'slow-test', 'Australia/Sydney')
            runtime = FakeRuntime(['homeassistant', 'mosquitto'], fail_start=True)
            with self.assertRaises(backup.RecoveryError) as caught:
                create_backup(root, destination, runtime=runtime)
            archive = caught.exception.archive
            self.assertTrue(archive.is_file())
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.assertEqual(verify(archive)['db_logical_dump_status'], 'not-enabled')
            self.assertFalse((destination / 'last-success.json').exists())
            self.assertFalse(list(destination.glob('.homeauto-*')))



class InterruptAndResumeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root, self.destination = self.base / 'app', self.base / 'backups'
        install.prepare(self.root, [], '', '', False, 'interrupt-test', 'Australia/Sydney')

    def test_real_sigterm_mid_backup_resumes_and_publishes_nothing(self):
        import signal
        import backup
        backup.install_signal_handlers()
        self.addCleanup(signal.signal, signal.SIGTERM, signal.SIG_DFL)
        self.addCleanup(signal.signal, signal.SIGINT, signal.default_int_handler)
        self.addCleanup(signal.signal, signal.SIGHUP, signal.SIG_DFL)

        class Signalling(FakeRuntime):
            def stop(self, services):
                super().stop(services)
                os.kill(os.getpid(), signal.SIGTERM)  # as systemd TimeoutStartSec would

        runtime = Signalling(['homeassistant', 'mosquitto'])
        with self.assertRaises(backup.Interrupted):
            create_backup(self.root, self.destination, runtime=runtime)
        self.assertEqual(runtime.running, {'homeassistant', 'mosquitto'})
        self.assertFalse((self.root / backup.MARKER).exists())
        self.assertFalse(list(self.destination.glob('*.tar.gz')))
        self.assertFalse(list(self.destination.glob('.homeauto-*')))

    def test_marker_written_before_stop_and_left_when_resume_fails(self):
        import backup
        seen = {}

        class Observing(FakeRuntime):
            def stop(self, services):
                seen['marker'] = json.loads((root / backup.MARKER).read_text())['services']
                super().stop(services)
        root = self.root
        runtime = Observing(['homeassistant', 'mosquitto'], fail_dump=False, fail_start=True)
        with self.assertRaises(backup.RecoveryError):
            create_backup(self.root, self.destination, runtime=runtime)
        self.assertEqual(seen['marker'], ['homeassistant', 'mosquitto'])
        self.assertTrue((self.root / backup.MARKER).exists())  # ExecStopPost/--resume will retry

    def test_resume_is_idempotent_and_validates_marker(self):
        import backup
        runtime = FakeRuntime()
        self.assertEqual(backup.resume(self.root, runtime=runtime), [])
        backup.write_marker(self.root, ['homeassistant'])
        self.assertEqual(backup.resume(self.root, runtime=runtime), ['homeassistant'])
        self.assertIn('homeassistant', runtime.running)
        self.assertFalse((self.root / backup.MARKER).exists())
        (self.root / backup.MARKER).write_text('{"services": ["x; rm -rf /"]}')
        with self.assertRaises(ValueError):
            backup.resume(self.root, runtime=runtime)

    def test_marker_never_enters_snapshot(self):
        import backup
        backup.write_marker(self.root, ['homeassistant'])
        path = create_backup(self.root, self.destination, runtime=FakeRuntime(), offline=True)
        self.assertNotIn(backup.MARKER, verify(path)['files'])

    def test_non_canonical_and_nested_destinations_refused(self):
        for bad in [Path(str(self.base) + '/../' + self.base.name + '/app/backups'),
                    self.root / 'backups', self.base, Path('/'), Path('relative/backups')]:
            with self.assertRaises(ValueError, msg=str(bad)):
                create_backup(self.root, bad, runtime=FakeRuntime())
        self.assertFalse((self.root / 'backups').exists())

    def test_old_layout_root_dumps_without_db_backup_secret(self):
        import backup
        install.prepare(self.base / 'db', ['mariadb'], '', '', False, 'old-layout', 'Australia/Sydney')
        (self.base / 'db/private/db_backup.cnf').unlink(missing_ok=True)
        runtime = backup.Runtime.__new__(backup.Runtime)
        runtime.root = self.base / 'db'
        captured = {}

        def fake_run(argv, **kwargs):
            captured.update(argv=argv, input=kwargs['input'])
            kwargs['stdout'].write(b'-- dump\n' * 20)
            return subprocess.CompletedProcess(argv, 0)
        from unittest import mock
        with mock.patch.object(backup.subprocess, 'run', fake_run), \
                mock.patch.object(backup, 'compose', lambda root, *a: ['docker', 'compose', *a]):
            runtime.dump(self.base / 'dump.sql')
        password = (self.base / 'db/private/db_root').read_text().strip()
        self.assertNotIn(password, ' '.join(captured['argv']))
        self.assertIn(password.encode(), captured['input'])
        self.assertIn('--defaults-extra-file=/dev/stdin', captured['argv'])

    def test_stale_staging_from_killed_run_cleaned_but_fresh_kept(self):
        import backup
        self.destination.mkdir(mode=0o700)
        old_dir = self.destination / '.homeauto-backup-dead'; old_dir.mkdir()
        old_tmp = self.destination / '.homeauto-x.tar.gz'; old_tmp.write_bytes(b'x')
        fresh = self.destination / '.homeauto-backup-live'; fresh.mkdir()
        other = self.destination / 'operator-notes'; other.write_text('keep')
        for path in (old_dir, old_tmp, other):
            os.utime(path, (1, 1))
        self.assertEqual(backup.clean_stale(self.destination), 2)
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()), ['.homeauto-backup-live', 'operator-notes'])

    def test_retention_prunes_by_timestamped_name_only(self):
        import backup
        self.destination.mkdir(mode=0o700)
        names = [f'homeauto-2026111{d}T030000Z-0000000{d}.tar.gz' for d in range(5)]
        for name in names:
            (self.destination / name).write_bytes(b'x')
        (self.destination / 'homeauto-notes.txt').write_text('keep')
        self.assertEqual(backup.prune(self.destination, 2), 3)
        self.assertEqual(sorted(p.name for p in self.destination.iterdir()),
                         sorted(names[-2:] + ['homeauto-notes.txt']))


if __name__ == '__main__':
    unittest.main()


class RestoreIntegrityTests(unittest.TestCase):
    def test_archive_swapped_after_verify_is_not_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / 'app'
            install.prepare(root, [], '', '', False, 'swap-test', 'Australia/Sydney')
            good = create_backup(root, base / 'backups', runtime=FakeRuntime(['homeassistant']))
            config = root / 'ha/configuration.yaml'
            original = config.read_bytes()
            config.write_bytes(original[:-2] + b'#\n')  # same size, different bytes
            other = create_backup(root, base / 'other', runtime=FakeRuntime(['homeassistant']))

            def swap():  # keep good's manifest; take the tampered file body from `other`
                with tarfile.open(good, 'r:gz') as src, tarfile.open(other, 'r:gz') as alt, \
                        tarfile.open(base / 'evil.tar.gz', 'w:gz') as out:
                    for member in src.getmembers():
                        body = alt if member.name == 'state/ha/configuration.yaml' else src
                        item = body.getmember(member.name)
                        out.addfile(item, body.extractfile(item) if item.isfile() else None)
                os.replace(base / 'evil.tar.gz', good)
            target = base / 'restored'
            with self.assertRaisesRegex(ValueError, 'changed after verification \\(hash\\)'):
                restore(good, target, _after_verify=swap)
            self.assertFalse(target.exists())
            self.assertFalse(list(base.glob('.homeauto-restore-*')))

    def test_dotdot_destination_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            install.prepare(base / 'app', [], '', '', False, 'dot-test', 'Australia/Sydney')
            archive = create_backup(base / 'app', base / 'backups', runtime=FakeRuntime())
            with self.assertRaises(ValueError):
                restore(archive, Path(str(base) + '/x/../restored'))
