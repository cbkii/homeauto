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


def owned_services(root: Path) -> set[str]:
    """Refuse a Compose project already owned by another state root."""
    data = state(root)
    result = run(['docker', 'ps', '-a', '--filter',
                  'label=com.docker.compose.project=' + data['project'], '--format', '{{.ID}}'])
    if result.returncode:
        raise ValueError('Cannot establish Compose project ownership')
    services = set()
    for container in result.stdout.splitlines():
        if not re.fullmatch(r'[0-9a-f]{12,64}', container):
            raise ValueError('Invalid container evidence')
        inspected = run(['docker', 'inspect', '--format', '{{json .Config.Labels}}', container])
        if inspected.returncode:
            raise ValueError('Cannot inspect project ownership')
        labels = json.loads(inspected.stdout)
        files = labels.get('com.docker.compose.project.config_files', '').split(',')
        directory = labels.get('com.docker.compose.project.working_dir', '')
        if str(root / 'compose.yaml') not in files or directory != str(root):
            raise ValueError('Compose project belongs to another application root; choose an unused project')
        services.add(labels.get('com.docker.compose.service', ''))
    return services


from contextlib import contextmanager
import fcntl


@contextmanager
def operation_lock(root: Path):
    """One lifecycle writer at a time; never follow a supplied lock symlink."""
    state(root)
    fd = os.open(root / '.operation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another homeauto lifecycle operation is active') from exc
        yield
    finally:
        os.close(fd)
