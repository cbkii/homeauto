#!/usr/bin/env python3
"""Private consistent cold-state backup, plus required logical SQL dump if selected."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import atomic, compose, operation_lock, owned_services, run, safe_root, state

LOG = logging.getLogger('homeauto-backup')
EXCLUDE = {'.operation.lock'}


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
        result = run(compose(self.root, 'stop', '--timeout', '60', *services), timeout=120)
        if result.returncode or any(r['State'] not in {'exited', 'created'} for r in self.rows()):
            raise RuntimeError('Writers did not stop; no snapshot taken')

    def start(self, services: list[str]):
        if not services:
            return
        result = run(compose(self.root, 'start', *services), timeout=120)
        if result.returncode:
            raise RuntimeError('Could not resume original services')
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            rows = {r['Service']: r for r in self.rows()}
            if all(rows.get(s, {}).get('State') == 'running' and
                   rows.get(s, {}).get('Health') in {'healthy', '', None} for s in services):
                return
            time.sleep(2)
        raise RuntimeError('Original services did not recover healthy state')

    def dump(self, path: Path):
        # File secret keeps the SQL password out of argv, resolved Compose and logs.
        argv = compose(self.root, 'exec', '-T', '--user', '0', 'mariadb', 'mariadb-dump',
                       '--defaults-extra-file=/run/secrets/db_backup', '--all-databases',
                       '--single-transaction', '--quick', '--routines', '--events')
        with path.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            result = subprocess.run(argv, stdout=stream, stderr=subprocess.PIPE, timeout=300, check=False)
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
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
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
            manifest['sql_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    atomic(staging / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return manifest


def create_backup(root: Path, destination: Path, *, runtime=None, offline=False,
                  dry_run=False, lock_held=False) -> Path | None:
    data = state(root)
    if not destination.is_absolute() or destination == root or root in destination.parents:
        raise ValueError('Backup destination must be outside application root')
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
        staging = Path(tempfile.mkdtemp(prefix='.homeauto-backup-', dir=destination))
        name = 'homeauto-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + os.urandom(4).hex() + '.tar.gz'
        temporary = destination / ('.' + name)
        archive = destination / name
        published = False
        try:
            images = runtime.images()
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
            # Health recovery is part of success; retain failed archives privately only as staging.
            runtime.start(running)
            os.replace(temporary, archive)
            published = True
            atomic(destination / 'last-success.json', json.dumps(dict(
                schema=1, created_utc=datetime.now(timezone.utc).isoformat(), archive=archive.name)) + '\n')
            LOG.info('SUCCESS: private verified archive %s; copy off-device and rehearse restore', archive)
            return archive
        finally:
            try:
                if not published:
                    runtime.start(running)
            finally:
                shutil.rmtree(staging)
                if temporary.exists():
                    temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--keep', type=int, default=7, help='Retain this many completed archives; no deletion on failed backup')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if not 1 <= args.keep <= 365:
            raise ValueError('Retention count must be 1..365')
        completed = create_backup(args.data_dir, args.backup_dir, offline=args.offline, dry_run=args.dry_run)
        if completed:
            archives = sorted((p for p in args.backup_dir.glob('homeauto-*.tar.gz') if p.is_file() and not p.is_symlink()), key=lambda p: p.stat().st_mtime, reverse=True)
            from restore import verify
            for old in archives[args.keep:]:
                verify(old)
                old.unlink()
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        LOG.error('FAILED: backup incomplete; inspect private state and original service health. No success archive published.')
        return 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
