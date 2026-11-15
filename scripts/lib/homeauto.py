"""Shared, non-shell configuration and bounded command handling."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROFILES = {'zigbee', 'extras', 'mariadb', 'actions'}


def run(argv: list[str], *, timeout: int = 30, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=False, capture_output=True, text=True,
                          timeout=timeout, **kwargs)


def env_read(path: Path) -> dict[str, str]:
    """Accept literal KEY=value only; never execute/interpolate input."""
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in values:
            raise ValueError('Invalid or duplicate environment key')
        if any(c in value for c in '\r\n\x00') or '$' in value or '`' in value:
            raise ValueError('Environment substitutions are not supported')
        values[key] = value
    return values


def atomic(path: Path, content: str, mode: int = 0o600) -> None:
    fd, name = tempfile.mkstemp(prefix='.homeauto-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def safe_root(path: Path) -> Path:
    if not path.is_absolute() or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(path)):
        raise ValueError('Data path must be absolute and contain simple path characters')
    if '..' in path.parts or str(path) in {'/', '/srv', '/var', '/home', '/opt', '/media'}:
        raise ValueError('Unsafe data root')
    if path == REPO or REPO in path.parents or str(path).startswith('/media/mediasmb'):
        raise ValueError('Use a separate application root, not source or media storage')
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError('Symlinks are not accepted in application paths')
    return path


def state(root: Path) -> dict:
    safe_root(root)
    marker = root / '.homeauto.json'
    if not marker.is_file() or marker.is_symlink():
        raise ValueError('Not a managed homeauto data root')
    data = json.loads(marker.read_text())
    if data.get('schema') != 1 or data.get('data_dir') != str(root):
        raise ValueError('Application marker does not match data root')
    return data


def compose(root: Path, *args: str) -> list[str]:
    data = state(root)
    argv = ['docker', 'compose', '--project-name', data['project'],
            '--env-file', str(root / '.env'), '-f', str(root / 'compose.yaml')]
    if data.get('bluetooth'):
        argv += ['-f', str(root / 'compose.bluetooth.yaml')]
    for profile in data['profiles']:
        if profile != 'actions':
            argv += ['--profile', profile]
    return argv + list(args)
