import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ComposeContract(unittest.TestCase):
    def test_optional_services_cannot_hold_core(self):
        data = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
        services = data['services']
        self.assertEqual({k for k, v in services.items() if not v.get('profiles')}, {'homeassistant', 'mosquitto'})
        self.assertFalse(services['homeassistant'].get('depends_on'))
        self.assertFalse(services['homeassistant'].get('privileged', False))
        self.assertNotIn('network_mode', services['mariadb'])
        self.assertTrue(all(p.startswith('127.0.0.1:') for p in services['mariadb']['ports']))
        for service in services.values():
            self.assertNotIn(':latest', service['image'])
            self.assertNotIn(':stable', service['image'])
            self.assertIn('healthcheck', service)
            self.assertIn('max-size', service['logging']['options'])

    def test_ha_broker_is_ui_managed_and_sqlite_default(self):
        text = (ROOT / 'ha/configuration.yaml').read_text()
        self.assertNotRegex(text, r'(?m)^\s*broker:')
        self.assertNotIn('db_url:', text)
        self.assertEqual(text, (ROOT / 'ha/configuration.yaml.example').read_text())



class BareComposeFailsClosed(unittest.TestCase):
    """A habitual `docker compose up` in a pulled Pi-era checkout must not recreate the
    legacy `homeauto` project against an empty default data directory."""
    def test_no_silent_default_data_dir(self):
        text = (ROOT / 'docker-compose.yml').read_text()
        self.assertNotIn('HOMEAUTO_DATA_DIR:-', text)
        self.assertIn('HOMEAUTO_DATA_DIR:?', text)

    @unittest.skipUnless(shutil.which('docker'), 'docker CLI unavailable')
    def test_bare_config_refused_but_managed_env_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            shutil.copy(ROOT / 'docker-compose.yml', Path(temp) / 'docker-compose.yml')
            env = {k: v for k, v in os.environ.items() if k != 'HOMEAUTO_DATA_DIR'}
            bare = subprocess.run(['docker', 'compose', 'config', '--quiet'], cwd=temp, env=env,
                                  capture_output=True, text=True, timeout=60)
            self.assertNotEqual(bare.returncode, 0)
            self.assertIn('HOMEAUTO_DATA_DIR', bare.stderr)
        managed = subprocess.run(['docker', 'compose', '--env-file', str(ROOT / '.env.example'), '-f',
                                  str(ROOT / 'docker-compose.yml'), 'config', '--quiet'],
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(managed.returncode, 0, managed.stderr)

if __name__ == '__main__':
    unittest.main()
