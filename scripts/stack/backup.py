#!/usr/bin/env python3
"""Private consistent cold-state backup, plus required logical SQL dump if selected."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import atomic, compose, operation_lock, owned_services, run, safe_root, sha256_stream, state

LOG = logging.getLogger('homeauto-backup')
MARKER = '.backup-stopped.json'  # services this backup stopped; survives SIGKILL/power loss
EXCLUDE = {'.operation.lock', MARKER}
RECOVERY_SECONDS = 360  # HA start_period 120 s + 6 x 30 s health retries on a large recorder DB.


class RecoveryError(RuntimeError):
    """Archive is verified and published, but original services did not recover."""
    def __init__(self, archive: Path):
        super().__init__('Services did not recover after a verified backup')
        self.archive = archive


class Interrupted(Exception):
    """SIGTERM/SIGINT/SIGHUP during a backup: unwind through finally and resume services."""
    archive = None  # set when a verified archive was already published


SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def _interrupt(signum, frame):
    # Ignore repeats so a second Ctrl-C/SIGHUP cannot abort the resume in `finally`;
    # systemd's SIGKILL + ExecStopPost --resume remains the backstop.
    for sig in SIGNALS:
        signal.signal(sig, signal.SIG_IGN)
    raise Interrupted(signal.Signals(signum).name)


def install_signal_handlers():
    # Python's default SIGTERM action kills the process without running finally blocks,
    # which would leave Home Assistant stopped after a systemd timeout or shutdown.
    for sig in SIGNALS:
        signal.signal(sig, _interrupt)


def write_marker(root: Path, services: list[str]):
    atomic(root / MARKER, json.dumps(dict(schema=1, services=services,
                                          created_utc=datetime.now(timezone.utc).isoformat())) + '\n')


def resume(root: Path, *, runtime=None) -> list[str]:
    """Start services recorded by an interrupted/killed backup; idempotent no-op otherwise."""
    marker = root / MARKER
    if marker.is_symlink():
        raise ValueError('Symlinked recovery marker refused')
    if not marker.is_file():
        return []
    services = json.loads(marker.read_text())['services']
    if not isinstance(services, list) or not all(isinstance(s, str) and s.isidentifier() for s in services):
        raise ValueError('Invalid recovery marker')
    with operation_lock(root):
        (runtime or Runtime(root)).start(services)
        marker.unlink()
    return services


class Runtime:
    def __init__(self, root: Path):
        self.root = root
        owned_services(root)

    def rows(self) -> list[dict]:
        result = run(compose(self.root, 'ps', '--all', '--format', 'json'))
        if result.returncode:
            raise RuntimeError('Cannot establish running service state')
        raw = result.stdout.strip()
        if not raw:
            return []
        return json.loads(raw) if raw.startswith('[') else [json.loads(line) for line in raw.splitlines()]

    def images(self) -> dict:
        images = {}
        for row in self.rows():
            result = run(['docker', 'inspect', '--format', '{{.Image}}', row['ID']])
            if result.returncode or not result.stdout.strip().startswith('sha256:'):
                raise RuntimeError('Cannot record immutable running image ID')
            image_id = result.stdout.strip()
            digests = run(['docker', 'image', 'inspect', '--format', '{{json .RepoDigests}}', image_id])
            if digests.returncode:
                raise RuntimeError('Cannot record registry digest')
            images[row['Service']] = dict(id=image_id, repo_digests=json.loads(digests.stdout) or [])
        return images

    def stop(self, services: list[str]):
        if not services:
            return
        result = run(compose(self.root, 'stop', '--timeout', '60', *services), timeout=180)
        # Only the requested writers must be stopped: MariaDB deliberately stays up for the dump.
        rows = {r['Service']: r['State'] for r in self.rows()}
        if result.returncode or any(rows.get(s) not in {'exited', 'created'} for s in services):
            raise RuntimeError('Writers did not stop; no snapshot taken')

    def start(self, services: list[str]):
        if not services:
            return
        # After an interrupted `compose stop` the daemon may still be gracefully stopping a
        # container: an immediate start is then a no-op and the container exits afterwards
        # (observed under a systemd start timeout). Re-issue start, bounded, whenever a
        # requested service is found stopped while waiting for health.
        starts = 0
        deadline = time.monotonic() + RECOVERY_SECONDS
        pending = list(services)
        while time.monotonic() < deadline:
            if pending:
                if starts >= 6:
                    raise RuntimeError('Could not resume original services')
                starts += 1
                if run(compose(self.root, 'start', *pending), timeout=180).returncode:
                    time.sleep(5)
                    continue
            rows = {r['Service']: r for r in self.rows()}
            if all(rows.get(s, {}).get('State') == 'running' and
                   rows.get(s, {}).get('Health') in {'healthy', '', None} for s in services):
                return
            pending = [s for s in services if rows.get(s, {}).get('State') in {'exited', 'created'}]
            time.sleep(2)
        raise RuntimeError('Original services did not recover healthy state')

    def dump(self, path: Path):
        # Option file on stdin keeps the password out of argv/Compose/logs and needs no extra
        # secret, so roots prepared before this release (db_root only) can still be dumped.
        password = (self.root / 'private/db_root').read_text().strip()
        if not password or any(c in password for c in '\r\n'):
            raise RuntimeError('Database root secret unreadable')
        argv = compose(self.root, 'exec', '-T', 'mariadb', 'mariadb-dump',
                       '--defaults-extra-file=/dev/stdin', '--all-databases',
                       '--single-transaction', '--quick', '--routines', '--events')
        with path.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            result = subprocess.run(argv, input=f'[client]\nuser=root\npassword={password}\n'.encode(),
                                    stdout=stream, stderr=subprocess.PIPE, timeout=600, check=False)
            stream.flush(); os.fsync(stream.fileno())
        if result.returncode or path.stat().st_size < 100:
            raise RuntimeError('Required SQL dump failed or was empty')


def snapshot(root: Path, staging: Path, images: dict, db_status: str) -> dict:
    """Caller proves all writers stopped. Never follow links or copy devices."""
    files = {}
    directories = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if relative.parts[0] in EXCLUDE:
            continue
        info = path.lstat()
        target = staging / 'state' / relative
        if stat.S_ISDIR(info.st_mode):
            target.mkdir(parents=True, exist_ok=True)
            directories[str(relative)] = dict(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
        elif stat.S_ISREG(info.st_mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target, follow_symlinks=False)
            with target.open('rb') as stream:
                digest = sha256_stream(stream)
            files[str(relative)] = dict(sha256=digest, size=info.st_size,
                                       mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
        else:
            raise ValueError('Special files/symlinks in application state; snapshot refused')
    if '.homeauto.json' not in files or 'compose.yaml' not in files or 'secrets.json' not in files:
        raise ValueError('Incomplete application state')
    manifest = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(),
                    db_logical_dump_status=db_status, images=images, files=files, directories=directories)
    if db_status == 'ok':
        dump = staging / 'mariadb-logical.sql'
        with dump.open('rb') as stream:
            manifest['sql_sha256'] = sha256_stream(stream)
    atomic(staging / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return manifest


def clean_stale(destination: Path, max_age: float = 6 * 3600) -> int:
    """Remove private staging/temporary leftovers of killed runs (SIGKILL/power loss)."""
    removed = 0
    for path in destination.iterdir():
        stale = time.time() - path.lstat().st_mtime > max_age
        if path.is_symlink() or not stale:
            continue
        if path.name.startswith('.homeauto-backup-') and path.is_dir():
            shutil.rmtree(path); removed += 1
        elif path.name.startswith('.homeauto-') and path.name.endswith('.tar.gz') and path.is_file():
            path.unlink(); removed += 1
    return removed


def create_backup(root: Path, destination: Path, *, runtime=None, offline=False,
                  dry_run=False, lock_held=False) -> Path | None:
    data = state(root)
    if not destination.is_absolute() or '..' in destination.parts:
        raise ValueError('Backup destination must be an absolute path without ..')
    real_dest, real_root = destination.resolve(), root.resolve()
    if (real_dest == real_root or real_root in real_dest.parents or real_dest in real_root.parents
            or str(real_dest) in {'/', '/srv', '/var', '/home', '/opt', '/media'}
            or str(real_dest).startswith('/media/mediasmb')):
        raise ValueError('Backup destination must be a dedicated directory independent of the application root')
    for path in [destination, *destination.parents]:
        if path.is_symlink():
            raise ValueError('Symlinked backup destination refused')
    if dry_run:
        LOG.info('PLAN: inspect runtime, stop writers, snapshot private state, resume original services')
        return None
    with nullcontext() if lock_held else operation_lock(root):
        runtime = runtime or Runtime(root)
        rows = runtime.rows()
        if any(r['State'] not in {'running', 'exited', 'created'} for r in rows):
            raise ValueError('Transitional/restarting/paused container; establish stable service state first')
        running = sorted(r['Service'] for r in rows if r['State'] == 'running')
        if offline and running:
            raise ValueError('Offline backup requires every project container stopped')
        if 'mariadb' in data['profiles'] and 'mariadb' not in running and not offline:
            raise ValueError('Required MariaDB is not running; no successful online backup possible')
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        if destination.stat().st_mode & 0o077:
            raise ValueError('Backup destination must be private (0700)')
        clean_stale(destination)
        staging = Path(tempfile.mkdtemp(prefix='.homeauto-backup-', dir=destination))
        name = 'homeauto-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + os.urandom(4).hex() + '.tar.gz'
        temporary = destination / ('.' + name)
        archive = destination / name
        published = False
        resumed = False  # False: finally must (re)start `running`; True/None: handled already
        stopped_marker = bool(running) and not offline
        try:
            images = runtime.images()
            if stopped_marker:
                write_marker(root, running)  # before the first stop: recovery survives SIGKILL
            db_status = 'not-enabled'
            if 'mariadb' in data['profiles']:
                if offline:
                    db_status = 'cold-snapshot-only'
                else:
                    # Stop application writers before the SQL dump, keep DB until dump completes.
                    runtime.stop([s for s in running if s != 'mariadb'])
                    runtime.dump(staging / 'mariadb-logical.sql')
                    db_status = 'ok'
            runtime.stop(running)
            snapshot(root, staging, images, db_status)
            with tarfile.open(temporary, 'w:gz') as tar:
                for child in staging.iterdir():
                    tar.add(child, arcname=child.name, recursive=True)
            os.chmod(temporary, 0o600)
            # Verify bytes and structure before publishing the successful archive.
            from restore import verify
            verify(temporary)
            # A verified archive is kept even if services then recover slowly or fail; the
            # last-success marker (used by monitoring) is written only after recovery.
            os.replace(temporary, archive)
            published = True
            try:
                runtime.start(running)
                resumed = True
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                resumed = None  # attempted and failed: leave marker for --resume, no second wait
                raise RecoveryError(archive) from exc
            if stopped_marker:
                (root / MARKER).unlink(missing_ok=True)
            atomic(destination / 'last-success.json', json.dumps(dict(
                schema=1, created_utc=datetime.now(timezone.utc).isoformat(), archive=archive.name)) + '\n')
            LOG.info('SUCCESS: private verified archive %s; copy off-device and rehearse restore', archive)
            return archive
        except Interrupted as exc:
            exc.archive = archive if published else None
            raise
        finally:
            try:
                if resumed is False:
                    runtime.start(running)
                    if stopped_marker:
                        (root / MARKER).unlink(missing_ok=True)
            finally:
                shutil.rmtree(staging)
                if temporary.exists():
                    temporary.unlink()


def prune(destination: Path, keep: int) -> int:
    """Keep the newest `keep` archives by their UTC timestamped names; never touches other files."""
    import re
    archives = sorted(p for p in destination.iterdir()
                      if re.fullmatch(r'homeauto-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gz', p.name)
                      and p.is_file() and not p.is_symlink())
    for old in archives[:-keep]:
        old.unlink()
    return max(0, len(archives) - keep)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--resume', action='store_true',
                        help='Only restart services left stopped by an interrupted backup (systemd ExecStopPost)')
    parser.add_argument('--keep', type=int, default=7, help='Retain this many completed archives; no deletion on failed backup')
    parser.add_argument('--copy-to', type=Path, help='Mounted directory on another disk for a verified off-device copy')
    args = parser.parse_args()
    os.umask(0o077)
    install_signal_handlers()
    try:
        if args.resume:
            services = resume(args.data_dir)
            LOG.info('RESUMED: %s', ', '.join(services) if services else 'nothing to resume')
            return 0
        if not 1 <= args.keep <= 365:
            raise ValueError('Retention count must be 1..365')
        completed = create_backup(args.data_dir, args.backup_dir, offline=args.offline, dry_run=args.dry_run)
        if completed:
            try:
                prune(args.backup_dir, args.keep)
            except OSError:
                LOG.warning('Retention pruning incomplete; new verified archive kept')
            if args.copy_to:
                from offdevice import copy_latest
                try:
                    copy_latest(args.backup_dir, args.copy_to, [args.data_dir, args.backup_dir])
                except (OSError, ValueError, KeyError, RuntimeError) as exc:
                    LOG.error('FAILED: local archive %s verified; off-device copy failed (%s)', completed.name,
                              exc if isinstance(exc, ValueError) else type(exc).__name__)
                    return 4
        return 0
    except Interrupted as exc:
        LOG.error('INTERRUPTED (%s): %s; original services %s', exc,
                  f'verified archive {exc.archive.name} kept (success marker not updated)' if exc.archive
                  else 'no archive published',
                  'resume FAILED - run backup.py --resume' if (args.data_dir / MARKER).exists() else 'resumed')
        return 5
    except RecoveryError as exc:
        LOG.error('FAILED: archive %s verified, but original services did not recover healthy; '
                  'run backup.py --resume / manage.py status before relying on automation', exc.archive.name)
        return 3
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        LOG.error('FAILED: backup incomplete (%s); no success archive published.%s',
                  exc if isinstance(exc, ValueError) else type(exc).__name__,
                  ' Services may be stopped: run backup.py --resume' if (args.data_dir / MARKER).exists() else '')
        return 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
