#!/usr/bin/env python3
"""Back up and apply an explicitly reviewed Compose candidate, never auto-downgrade."""
import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import atomic, compose, operation_lock, owned_services, run, state
from backup import Interrupted, create_backup, install_signal_handlers
from install import _apply

LOG = logging.getLogger('homeauto-upgrade')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/srv/homeauto'))
    parser.add_argument('--backup-dir', type=Path, default=Path('/srv/homeauto-backups'))
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    install_signal_handlers()  # SIGTERM during the checkpoint must still resume services
    applying = False
    try:
        state(args.data_dir)
        if args.candidate.is_symlink() or not args.candidate.is_file():
            raise ValueError('Candidate must be a regular file')
        candidate = args.candidate.read_text()
        if not args.apply:
            print('PLAN: validate candidate, back up matching state/images, pull selected versions, start core first.\n'
                  'A failed post-migration upgrade requires restoring matching data/config/images; no automatic downgrade.')
            return 0
        with operation_lock(args.data_dir):
            owned_services(args.data_dir)
            with tempfile.TemporaryDirectory(prefix='.candidate-', dir=args.data_dir) as tmp:
                path = Path(tmp) / 'compose.yaml'
                atomic(path, candidate)
                argv = compose(args.data_dir, 'config', '--quiet')
                # Replace only first base compose file; preserve optional Bluetooth overlay.
                argv[argv.index('-f') + 1] = str(path)
                result = run(argv, timeout=30)
                if result.returncode:
                    raise ValueError('Candidate Compose invalid')
            archive = create_backup(args.data_dir, args.backup_dir, lock_held=True)
            prior = (args.data_dir / 'compose.yaml').read_text()
            atomic(args.data_dir / 'compose.previous.yaml', prior)
            atomic(args.data_dir / 'compose.yaml', candidate)
            try:
                result = run(compose(args.data_dir, 'pull'), timeout=600)
            except BaseException:
                # Includes Interrupted: nothing has restarted, so the candidate must not stay
                # active for a later `install --apply` to pick up silently.
                atomic(args.data_dir / 'compose.yaml', prior)
                raise
            if result.returncode:
                # No services changed; restoring just the old config is still safe here.
                atomic(args.data_dir / 'compose.yaml', prior)
                raise RuntimeError('Pull failed before restart; previous configuration restored')
            applying = True
            code = _apply(args.data_dir)
            if code:
                LOG.error('Upgrade incomplete. Backup: %s. Do not downgrade images against migrated data.', archive)
                return 2
            LOG.info('Services healthy; complete functional/reboot/restore acceptance. Backup: %s', archive)
            return 0
    except Interrupted:
        if applying:
            LOG.error('INTERRUPTED during restart onto the candidate: compose.yaml is the candidate and '
                      'compose.previous.yaml the prior file. Run install.py --apply to finish, or restore '
                      'the pre-upgrade backup; no automatic downgrade.')
        else:
            LOG.error('INTERRUPTED: upgrade not applied; previous configuration kept '
                      '(run backup.py --resume if any service remains stopped)')
        return 5
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        LOG.error('STOP: upgrade incomplete; inspect private local state. No automatic data/schema downgrade attempted.')
        return 2


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    sys.exit(main())
