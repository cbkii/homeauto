#!/usr/bin/env python3
"""Real SQL dump, broker persistence, cold snapshot and isolated SQL restore."""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/stack'))
from install import prepare
from backup import create_backup
from restore import restore, verify
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/lib'))
from homeauto import compose


def command(argv, timeout=180):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Integration command failed; private output suppressed')
    return result.stdout.strip()


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run this disposable integration test as root for production bind ownership')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'live'
        target = Path(temp) / 'rehearsal'
        project = 'recovery-ci-' + secrets.token_hex(5)
        restored = project + '-restored'
        prepare(root, ['mariadb'], '', '', False, project, 'Australia/Sydney')
        with sqlite3.connect(root / 'ha/test.db') as db:
            db.execute('CREATE TABLE history (value TEXT)')
            db.execute("INSERT INTO history VALUES ('preserved')")
        try:
            command(compose(root, 'up', '-d', '--wait', '--wait-timeout', '240', 'mosquitto', 'mariadb'), timeout=300)
            command(compose(root, 'exec', '-T', 'mariadb', 'mariadb', '--defaults-extra-file=/run/secrets/db_backup',
                            '-e', "CREATE DATABASE recovery_test; CREATE TABLE recovery_test.events(value TEXT); INSERT INTO recovery_test.events VALUES ('preserved');"))
            archive = create_backup(root, Path(temp) / 'backups')
            if verify(archive)['db_logical_dump_status'] != 'ok':
                raise RuntimeError('Logical database backup missing')
            restore(archive, target)
            command(['docker', 'run', '-d', '--name', restored, '--network', 'none',
                     '-e', 'MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db_root',
                     '-v', f'{target}/private/db_root:/run/secrets/db_root:ro',
                     '-v', f'{target}/private/db_backup.cnf:/run/secrets/db_backup:ro',
                     '-v', f'{target}/mariadb:/var/lib/mysql', 'mariadb:11.8.3'])
            for _ in range(60):
                result = subprocess.run(['docker', 'exec', restored, 'healthcheck.sh', '--connect', '--innodb_initialized'],
                                        capture_output=True, timeout=10)
                if result.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Restored DB never became healthy')
            value = command(['docker', 'exec', restored, 'mariadb', '--defaults-extra-file=/run/secrets/db_backup',
                             '-N', '-e', 'SELECT value FROM recovery_test.events'])
            if value != 'preserved':
                raise RuntimeError('Restored SQL history differs')
            with sqlite3.connect(target / 'ha/test.db') as db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('SELECT value FROM history').fetchone()[0] != 'preserved':
                    raise RuntimeError('Restored SQLite history differs')
            print('PASS: real private SQL backup, original services resumed, isolated cold DB and SQLite restore')
        finally:
            subprocess.run(['docker', 'rm', '-f', restored], capture_output=True, timeout=60)
            subprocess.run(compose(root, 'down', '--timeout', '60'), capture_output=True, timeout=120)


if __name__ == '__main__':
    main()
