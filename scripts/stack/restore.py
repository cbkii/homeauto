#!/usr/bin/env python3
"""Verify and optionally restore bytes into an unoccupied directory. Never start services."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tarfile
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import safe_root, sha256_stream


def verify(archive: Path) -> dict:
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or member.name in seen or not (member.isdir() or member.isfile()):
                raise ValueError('Unsafe/duplicate archive member')
            if not path.parts or path.parts[0] not in {'state', 'manifest.json', 'mariadb-logical.sql'}:
                raise ValueError('Unexpected archive member')
            seen.add(member.name)
        member = tar.getmember('manifest.json')
        if member.size > 16 * 1024**2 or not member.isfile():
            raise ValueError('Invalid manifest')
        manifest = json.load(tar.extractfile(member))
        if manifest.get('schema') != 1:
            raise ValueError('Unsupported manifest')
        for relative, evidence in {**manifest['directories'], **manifest['files']}.items():
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or str(path) != relative or relative in {'', '.'}:
                raise ValueError('Unsafe manifest path')
            if not isinstance(evidence['mode'], int) or evidence['mode'] & ~0o777:
                raise ValueError('Unsafe restored permissions')
            if any(not isinstance(evidence[k], int) or evidence[k] < 0 for k in ['uid', 'gid']):
                raise ValueError('Invalid ownership')
        expected = {'manifest.json', 'state'} | {'state/' + p for p in manifest['files']} | {
            'state/' + p for p in manifest['directories']}
        if manifest.get('sql_sha256'):
            expected.add('mariadb-logical.sql')
            stream = tar.extractfile('mariadb-logical.sql')
            if sha256_stream(stream) != manifest['sql_sha256']:
                raise ValueError('SQL dump hash mismatch')
        if seen != expected:
            raise ValueError('Archive does not match manifest inventory')
        for path, evidence in manifest['files'].items():
            member = tar.getmember('state/' + path)
            if not member.isfile() or member.size != evidence['size']:
                raise ValueError('File size/type mismatch')
            with tar.extractfile(member) as stream:
                if sha256_stream(stream) != evidence['sha256']:
                    raise ValueError('File hash mismatch')
        for required in ['.homeauto.json', 'compose.yaml', 'secrets.json']:
            if required not in manifest['files']:
                raise ValueError('Required state absent')
        return manifest


def restore(archive: Path, destination: Path, *, _after_verify=None):
    safe_root(destination)
    if '..' in destination.parts or destination.exists() or not destination.parent.is_dir():
        raise ValueError('Restore destination must be unoccupied with an existing parent')
    manifest = verify(archive)
    if _after_verify:
        _after_verify()  # test hook: simulate the archive being replaced after verification
    staging = Path(tempfile.mkdtemp(prefix='.homeauto-restore-', dir=destination.parent))
    try:
        with tarfile.open(archive, 'r:gz') as tar:
            for relative in manifest['directories']:
                (staging / relative).mkdir(parents=True, exist_ok=True)
            for relative, evidence in manifest['files'].items():
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                # Re-hash while copying: the archive may have changed since verify() ran.
                member = tar.getmember('state/' + relative)
                if not member.isfile() or member.size != evidence['size']:
                    raise ValueError('Archive changed after verification (type/size)')
                digest, copied = hashlib.sha256(), 0
                with tar.extractfile(member) as source, path.open('xb') as target:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(block)
                        copied += len(block)
                        target.write(block)
                if copied != evidence['size'] or digest.hexdigest() != evidence['sha256']:
                    raise ValueError('Archive changed after verification (hash)')
                os.chmod(path, evidence['mode'])
                if os.geteuid() == 0:
                    os.chown(path, evidence['uid'], evidence['gid'])
            for relative, evidence in sorted(manifest['directories'].items(), reverse=True):
                path = staging / relative
                os.chmod(path, evidence['mode'])
                if os.geteuid() == 0:
                    os.chown(path, evidence['uid'], evidence['gid'])
        os.chmod(staging, 0o700)
        if destination.exists():
            raise ValueError('Restore destination became occupied')
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        manifest = restore(args.archive, args.destination) if args.destination else verify(args.archive)
        print(f"SUCCESS: {len(manifest['files'])} verified files; no services started. Archive is private.")
        if args.destination:
            print('A rehearsal at another path remains blocked by the original root marker; use an isolated target for recovery.')
        return 0
    except (OSError, ValueError, KeyError, tarfile.TarError):
        print('FAILED: invalid archive or occupied destination; no live state replaced', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
