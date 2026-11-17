import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q8b_report', ROOT / 'scripts/diagnostics/q8b-report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class RedactionTests(unittest.TestCase):
    def test_addresses_reduced_to_class(self):
        text = ('mac 0c:ef:af:12:34:56 lan 192.168.1.20 wan 203.0.113.9 lo 127.0.0.1 '
                'v6 2001:db8:85a3::8a2e:370:7334 ll fe80::1c2d:3e4f:5a6b:7c8d any :: ula fd12:3456:789a::1')
        out = report.redact(text)
        for leaked in ['0c:ef:af', '192.168', '203.0.113', '2001:db8', 'fe80::1c2d', 'fd12:3456']:
            self.assertNotIn(leaked, out)
        self.assertIn('PRIVATE', out)
        self.assertIn('OTHER', out)
        self.assertIn('LOOPBACK', out)

    def test_versions_times_and_text_survive(self):
        text = 'Docker 29.9.3 at 12:34:56 kernel 7.0.11-vendor-sc8280xp page 4096 hci0'
        self.assertEqual(report.redact(text), text)

    def test_by_id_serial_replaced_but_model_kept(self):
        name = 'usb-SMLIGHT_SMLIGHT_SLZB-07_56d27748d2d5ef118aa7694b49d2c684-if00-port0'
        shown = report.shown_by_id(name)
        self.assertNotIn('56d27748', shown)
        self.assertTrue(shown.startswith('usb-SMLIGHT_SMLIGHT_SLZB-07_h'))
        self.assertTrue(shown.endswith('-if00-port0'))
        self.assertEqual(shown, report.shown_by_id(name))  # stable across runs for replug comparison


class ReadOnlyRunTests(unittest.TestCase):
    def test_default_run_is_json_labelled_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'never-created'
            result = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/diagnostics/q8b-report.py'),
                                     '--data-dir', str(root)], capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr[-400:])
            data = json.loads(result.stdout)
            self.assertFalse(root.exists())
            self.assertNotIn('docker_smoke', data)
            self.assertNotIn('hostname', data['identity'])
            for name in ['identity', 'docker', 'kernel_network', 'storage', 'ports', 'serial', 'bluetooth',
                         'thermal', 'systemd', 'images', 'homeauto']:
                self.assertIn(data[name]['evidence'], {'ENUMERATION', 'RUNTIME', 'UNAVAILABLE'}, name)


if __name__ == '__main__':
    unittest.main()
