import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/stack'))
import upgrade
from install import prepare


class UpgradeTests(unittest.TestCase):
    def test_pre_restart_exception_restores_old_configuration(self):
        for error in [subprocess.TimeoutExpired(['docker'], 600), OSError('unavailable')]:
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'app'
                prepare(root, [], '', '', False, 'upgrade-test', 'Australia/Sydney')
                old = (root / 'compose.yaml').read_bytes()
                candidate = Path(temp) / 'candidate.yaml'
                candidate.write_text('services: {}\n')
                def fake(argv, **kwargs):
                    if 'pull' in argv:
                        raise error
                    return subprocess.CompletedProcess(argv, 0, '', '')
                argv = ['upgrade.py', '--data-dir', str(root), '--candidate', str(candidate), '--apply']
                with patch.object(sys, 'argv', argv), patch.object(upgrade, 'owned_services', return_value=set()), patch.object(upgrade, 'run', side_effect=fake), patch.object(upgrade, 'create_backup', return_value=Path(temp) / 'backup.tar.gz'), patch.object(upgrade, '_apply') as apply:
                    self.assertEqual(upgrade.main(), 2)
                    apply.assert_not_called()
                self.assertEqual((root / 'compose.yaml').read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
