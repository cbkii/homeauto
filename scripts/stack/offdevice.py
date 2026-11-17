#!/usr/bin/env python3
"""Copy the latest verified backup to a different physical disk or network mount.

Never deletes from the local backup directory; prunes the target only after a new
copy has been re-verified there. Refuses the same disk, RAM-backed filesystems and
the shared media path (backups must not be exposed over SMB).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import atomic  # noqa: E402

LOG = logging.getLogger('homeauto-offdevice')
ARCHIVE = re.compile(r'homeauto-\d{8}T\d{6}Z-[0-9a-f]{8}\.tar\.gz')
VOLATILE = {'tmpfs', 'ramfs', 'overlay', 'squashfs', 'devtmpfs', 'proc', 'sysfs'}
SUBDIR = 'homeauto-backups'


def disk_of(path: Path) -> str | None:
    """Whole-disk kernel name behind a path (nvme0n1, sda); None for non-block (NFS, CIFS, btrfs anon)."""
    st = os.stat(path)
    node = Path(f'/sys/dev/block/{os.major(st.st_dev)}:{os.minor(st.st_dev)}')
    if os.major(st.st_dev) == 0 or not node.exists():
        return None
    real = node.resolve()
    return (real.parent if (real / 'partition').exists() else real).name


def fstype_of(path: Path, mounts: str | None = None) -> str:
    best, kind = '', 'unknown'
    text = mounts if mounts is not None else Path('/proc/self/mounts').read_text()
    resolved = str(path.resolve())
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        point = fields[1].replace('\\040', ' ')
        if (resolved == point or resolved.startswith(point.rstrip('/') + '/')) and len(point) >= len(best):
            best, kind = point, fields[2]
    return kind


def check_target(target: Path, sources: list[Path], *, disk=disk_of, fstype=fstype_of) -> str:
    if not target.is_absolute() or not target.is_dir():
        raise ValueError('Off-device target must be an existing absolute directory (mounted)')
    for parent in [target, *target.parents]:
        if parent.is_symlink():
            raise ValueError('Symlinked off-device target refused')
    if str(target.resolve()).startswith('/media/mediasmb'):
        raise ValueError('Refusing the shared media path: private backups must not be exposed over SMB')
    kind = fstype(target)
    if kind in VOLATILE:
        raise ValueError(f'Refusing {kind} target: not durable storage')
    target_dev, target_disk = os.stat(target).st_dev, disk(target)
    for source in sources:
        if os.stat(source).st_dev == target_dev:
            raise ValueError('Target is on the same filesystem as application/backup state')
        if target_disk and target_disk == disk(source):
            raise ValueError('Target is on the same physical disk as application/backup state')
    return target_disk or kind


def copy_latest(backup_dir: Path, target: Path, sources: list[Path], *, keep: int = 14,
                disk=disk_of, fstype=fstype_of) -> Path:
    from restore import verify
    where = check_target(target, sources, disk=disk, fstype=fstype)
    name = json.loads((backup_dir / 'last-success.json').read_text())['archive']
    if not ARCHIVE.fullmatch(name):
        raise ValueError('Unexpected archive name in success marker')
    source = backup_dir / name
    destination = target / SUBDIR
    destination.mkdir(mode=0o700, exist_ok=True)
    if destination.is_symlink() or destination.stat().st_mode & 0o077:
        raise ValueError('Off-device directory must be private (0700)')
    final = destination / name
    partial = destination / ('.' + name + '.partial')
    try:
        with source.open('rb') as reader, partial.open('xb') as writer:
            os.fchmod(writer.fileno(), 0o600)
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        verify(partial)  # hashes and structure of the copy as written to the target
        os.replace(partial, final)
        fd = os.open(destination, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        partial.unlink(missing_ok=True)
    copies = sorted(p for p in destination.iterdir() if ARCHIVE.fullmatch(p.name) and p.is_file())
    for old in copies[:-keep]:
        old.unlink()
    atomic(backup_dir / 'last-offdevice.json', json.dumps(dict(
        schema=1, created_utc=datetime.now(timezone.utc).isoformat(), archive=name, medium=where)) + '\n')
    LOG.info('SUCCESS: %s verified on %s; %d copies retained there', name, where, min(len(copies), keep))
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--keep', type=int, default=14)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if not 1 <= args.keep <= 365:
            raise ValueError('Retention count must be 1..365')
        copy_latest(args.backup_dir, args.target, [args.data_dir, args.backup_dir], keep=args.keep)
        return 0
    except ValueError as exc:
        LOG.error('STOP: %s. Local backups untouched.', exc)
        return 2
    except (OSError, KeyError) as exc:
        LOG.error('FAILED: off-device copy incomplete (%s); local backups untouched', type(exc).__name__)
        return 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
