import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import sqlite3
import tarfile
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


if __name__ == '__main__':
    unittest.main()
