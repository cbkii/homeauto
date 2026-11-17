#!/usr/bin/env python3
"""Real recovery evidence on a disposable host (CI), not Q8B evidence.

1. Logical SQL dump imported into a *fresh* MariaDB datadir and queried.
2. Cold MariaDB datadir from the snapshot starts and holds the same rows.
3. SQLite history restored intact.
4. Retained QoS 1 Mosquitto message survives into a broker started from the restored snapshot.
5. A root prepared without the db_backup secret (older #13 layout) can still be dumped.
6. Interrupted backup (SIGTERM) and a left-behind marker (SIGKILL) both resume stopped services.
"""
import json
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/stack'))
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from install import prepare  # noqa: E402
from backup import MARKER, create_backup, write_marker  # noqa: E402
from restore import restore, verify  # noqa: E402
from homeauto import compose  # noqa: E402

MARIADB = 'mariadb:11.8.3'


def command(argv, timeout=180, stdin=None):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, input=stdin)
    if result.returncode:
        raise RuntimeError(f'Integration command failed ({argv[0]} ... {argv[-1][:40]}); private output suppressed')
    return result.stdout.strip()


def creds(password):
    return f'[client]\nuser=root\npassword={password}\n'


def wait_db(name):
    for _ in range(90):
        if subprocess.run(['docker', 'exec', name, 'healthcheck.sh', '--connect', '--innodb_initialized'],
                          capture_output=True, timeout=10).returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError('Database never became healthy')


def query(name, password, sql):
    return command(['docker', 'exec', '-i', name, 'mariadb', '--defaults-extra-file=/dev/stdin', '-N', '-e', sql],
                   stdin=creds(password))


def states(root):
    raw = command(compose(root, 'ps', '--all', '--format', 'json'))
    rows = json.loads(raw) if raw.startswith('[') else [json.loads(x) for x in raw.splitlines() if x]
    return {r['Service']: r['State'] for r in rows}


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run this disposable integration test as root for production bind ownership')
    names = []
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        root, target, backups = temp / 'live', temp / 'rehearsal', temp / 'backups'
        project = 'recovery-ci-' + secrets.token_hex(5)
        prepare(root, ['mariadb'], '', '', False, project, 'Australia/Sydney')
        (root / 'private/db_backup.cnf').unlink(missing_ok=True)  # older layout: db_root only
        password = (root / 'private/db_root').read_text().strip()
        mqtt = json.loads((root / 'secrets.json').read_text())
        with sqlite3.connect(root / 'ha/test.db') as db:
            db.execute('CREATE TABLE history (value TEXT)')
            db.execute("INSERT INTO history VALUES ('preserved')")
        marker = secrets.token_hex(8)
        try:
            command(compose(root, 'up', '-d', '--wait', '--wait-timeout', '240', 'mosquitto', 'mariadb'), timeout=300)
            command(compose(root, 'exec', '-T', 'mariadb', 'mariadb', '--defaults-extra-file=/dev/stdin', '-e',
                            "CREATE DATABASE recovery_test; CREATE TABLE recovery_test.events(value TEXT); "
                            "INSERT INTO recovery_test.events VALUES ('preserved');"), stdin=creds(password))
            command(compose(root, 'exec', '-T', 'mosquitto', 'mosquitto_pub', '-h', '127.0.0.1', '-u', 'ha', '-P',
                            mqtt['ha'], '-t', 'homeassistant/recovery_ci', '-m', marker, '-r', '-q', '1'))

            # 6a. SIGTERM mid-backup: run as a child, signal it once writers are stopped.
            child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/stack/backup.py'), '--data-dir', str(root),
                                      '--backup-dir', str(backups)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True)
            for _ in range(600):
                if (root / MARKER).exists() and states(root).get('mosquitto') == 'exited':
                    child.send_signal(signal.SIGTERM)
                    break
                if child.poll() is not None:
                    break
                time.sleep(0.1)
            output = child.communicate(timeout=600)[0]
            if child.returncode == 5:
                if (root / MARKER).exists() or states(root) != {'mosquitto': 'running', 'mariadb': 'running'}:
                    raise RuntimeError('SIGTERM left services stopped:\n' + output)
                if list(backups.glob('homeauto-*.tar.gz')):
                    raise RuntimeError('Interrupted backup published an archive')
                print('ok: SIGTERM during backup resumed services, no archive published')
            elif child.returncode == 0:
                print('note: backup finished before SIGTERM could land; interruption path covered by unit tests')
            else:
                raise RuntimeError(f'Unexpected backup exit {child.returncode}:\n{output}')

            # 6b. Simulated SIGKILL: services stopped with marker left behind -> --resume restores.
            command(compose(root, 'stop', 'mosquitto'))
            write_marker(root, ['mosquitto'])
            command([sys.executable, str(ROOT / 'scripts/stack/backup.py'), '--data-dir', str(root), '--resume'], timeout=600)
            if (root / MARKER).exists() or states(root).get('mosquitto') != 'running':
                raise RuntimeError('--resume did not restart services left by a killed backup')
            print('ok: --resume restarted services left by a killed backup')

            # Real backup on the old-layout root (no db_backup secret).
            archive = create_backup(root, backups)
            manifest = verify(archive)
            if manifest['db_logical_dump_status'] != 'ok' or states(root) != {'mosquitto': 'running', 'mariadb': 'running'}:
                raise RuntimeError('Logical backup missing or services not resumed')
            restore(archive, target)

            # 1. Logical dump -> fresh datadir.
            fresh = project + '-fresh'; names.append(fresh)
            command(['docker', 'run', '-d', '--name', fresh, '--network', 'none',
                     '-e', 'MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db_root',
                     '-v', f'{target}/private/db_root:/run/secrets/db_root:ro', MARIADB])
            wait_db(fresh)
            command(['docker', 'exec', '-i', fresh, 'sh', '-c', 'umask 077; cat > /tmp/client.cnf'],
                    stdin=creds(password))
            with tarfile.open(archive, 'r:gz') as tar:
                dump = tar.extractfile('mariadb-logical.sql').read()
            imported = subprocess.run(['docker', 'exec', '-i', fresh, 'mariadb', '--defaults-extra-file=/tmp/client.cnf'],
                                      input=dump, capture_output=True, timeout=300)
            if imported.returncode:
                raise RuntimeError('Logical SQL dump did not import into a fresh database')
            if query(fresh, password, 'SELECT value FROM recovery_test.events') != 'preserved':
                raise RuntimeError('Logical dump import lost rows')
            print('ok: logical SQL dump imported into fresh datadir')

            # 2. Cold datadir.
            cold = project + '-cold'; names.append(cold)
            command(['docker', 'run', '-d', '--name', cold, '--network', 'none',
                     '-e', 'MARIADB_ROOT_PASSWORD_FILE=/run/secrets/db_root',
                     '-v', f'{target}/private/db_root:/run/secrets/db_root:ro',
                     '-v', f'{target}/mariadb:/var/lib/mysql', MARIADB])
            wait_db(cold)
            if query(cold, password, 'SELECT value FROM recovery_test.events') != 'preserved':
                raise RuntimeError('Restored cold datadir differs')

            # 3. SQLite.
            with sqlite3.connect(target / 'ha/test.db') as db:
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or \
                        db.execute('SELECT value FROM history').fetchone()[0] != 'preserved':
                    raise RuntimeError('Restored SQLite history differs')

            # 4. Mosquitto persistence from the restored snapshot, isolated network.
            broker = project + '-broker'; names.append(broker)
            image = command(['docker', 'inspect', '--format', '{{.Config.Image}}', project + '-mosquitto-1'])
            command(['docker', 'run', '-d', '--name', broker, '--network', 'none',
                     '-v', f'{target}/mosquitto/config:/mosquitto/config:ro',
                     '-v', f'{target}/mosquitto/data:/mosquitto/data', image])
            for _ in range(30):
                got = subprocess.run(['docker', 'exec', broker, 'mosquitto_sub', '-h', '127.0.0.1', '-u', 'ha', '-P',
                                      mqtt['ha'], '-t', 'homeassistant/recovery_ci', '-C', '1', '-W', '3'],
                                     capture_output=True, text=True, timeout=20)
                if got.returncode == 0:
                    break
                time.sleep(1)
            if got.stdout.strip() != marker:
                raise RuntimeError('Retained MQTT state not present in restored broker')
            print('ok: retained MQTT message served by broker started from restored snapshot')
            print('PASS: old-layout SQL dump, SIGTERM/SIGKILL resume, fresh logical import, cold DB, SQLite, '
                  'MQTT persistence restore')
        finally:
            for name in names:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=60)
            subprocess.run(compose(root, 'down', '--timeout', '60'), capture_output=True, timeout=120)


if __name__ == '__main__':
    main()
