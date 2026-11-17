"""Ported release-hardening guards (formerly scripts/test/test_release_hardening.sh greps)."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preflight', ROOT / 'scripts/diagnostics/homeauto-preflight.py')
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
TRACKED = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True).stdout.split()
SELF = 'tests/test_release_hardening.py'


def files(*suffixes):
    return [ROOT / f for f in TRACKED if f.endswith(suffixes) and f != SELF and (ROOT / f).is_file()]


class ReleaseHardening(unittest.TestCase):
    def test_no_eval_or_shell_execution(self):
        for path in files('.sh'):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(r'\beval\b', line) and not line.lstrip().startswith('#'):
                    self.fail(f'eval in {path.relative_to(ROOT)}:{number}')
        for path in files('.py'):
            text = path.read_text()
            for pattern in (r'shell\s*=\s*True', r'\bos\.system\(', r'\bos\.popen\('):
                self.assertIsNone(re.search(pattern, text), f'{pattern} in {path.relative_to(ROOT)}')

    def test_no_malformed_command_tokens(self):
        # Regressions once introduced by whitespace-stripping edits (see git history).
        pattern = re.compile(r'cp\.env|\.env\.example\.env|source\.env|\[\[? -f\.env|install -m 0600\.env|'
                             r'sudo\./|run:\./|if!|find\.|using\.env|but\.env|no\.env|before\.env|and\.env')
        for path in files('.sh', '.md', '.yml', '.yaml', '.py'):
            match = pattern.search(path.read_text())
            self.assertIsNone(match, f'{match and match.group(0)!r} in {path.relative_to(ROOT)}')

    def test_adb_serial_formatting(self):
        for port, ip, expected in [(None, '192.168.1.60', '192.168.1.60:5555'), ('4444', '10.0.0.8', '10.0.0.8:4444')]:
            env = {k: v for k, v in os.environ.items() if k != 'ANDROID_TV_PORT'}
            if port:
                env['ANDROID_TV_PORT'] = port
            result = subprocess.run(['bash', '-c', f'source scripts/adb/_adb_common.sh; adb_serial {ip}'],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.stdout, expected)

    def test_docker_minimum_version_semantics(self):
        for text, ok in [('23.0.0', True), ('24.0.7+dfsg', True), ('26.1.5+dfsg1', True), ('29.9.3\n', True),
                         ('20.10.24', False), ('', False), ('dev', False)]:
            self.assertEqual(preflight.docker_version_ok(text), ok, text)

    def test_profile_model_and_install_flags(self):
        services = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']
        self.assertEqual({k for k, v in services.items() if not v.get('profiles')}, {'homeassistant', 'mosquitto'})
        self.assertEqual(services['zigbee2mqtt']['profiles'], ['zigbee'])
        self.assertEqual(services['esphome']['profiles'], ['extras'])
        installer = (ROOT / 'scripts/stack/install.py').read_text()
        for flag in ['--with-', '--with-all', '--zigbee-network', '--plan', '--prepare', '--apply']:
            self.assertIn(flag, installer)


if __name__ == '__main__':
    unittest.main()
