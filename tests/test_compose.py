import unittest
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
