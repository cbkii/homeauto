import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
spec = importlib.util.spec_from_file_location('commissioning', ROOT / 'scripts/smoke/commissioning.py')
commissioning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(commissioning)


class FakeBroker:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def read(self, *args, wait=3):
        self.calls.append(args)
        return self.replies.pop(0)


INFO = json.dumps(dict(version='2.14.3', network=dict(channel=15),
                       coordinator=dict(type='EmberZNet', ieee_address='0x00124b0000000000',
                                        meta=dict(revision='8.0.2'))))


class CommissioningTests(unittest.TestCase):
    def test_mqtt_auth_outcomes(self):
        self.assertEqual(commissioning.stage_mqtt(FakeBroker([(27, [])]))[0], 'PASS')
        self.assertEqual(commissioning.stage_mqtt(FakeBroker([(5, [])])), ('FAIL', 'ha credentials rejected'))
        self.assertEqual(commissioning.stage_mqtt(FakeBroker([(1, [])]))[0], 'FAIL')

    def test_bridge_reports_firmware_but_never_ieee(self):
        status, detail = commissioning.stage_bridge(FakeBroker([(27, [
            ('zigbee2mqtt/bridge/state', '{"state":"online"}'), ('zigbee2mqtt/bridge/info', INFO)])]))
        self.assertEqual(status, 'PASS')
        self.assertIn('EmberZNet', detail)
        self.assertIn('8.0.2', detail)
        self.assertNotIn('0x00124b', detail)

    def test_bridge_offline_or_garbage_fails(self):
        for rows in [[], [('zigbee2mqtt/bridge/state', '{"state":"offline"}')],
                     [('zigbee2mqtt/bridge/state', 'not json')]]:
            self.assertEqual(commissioning.stage_bridge(FakeBroker([(27, rows)]))[0], 'FAIL')

    def test_discovery_counts_only_z2m_configs(self):
        rows = [('homeassistant/sensor/a/b/config', '{"origin":{"name":"Zigbee2MQTT"}}'),
                ('homeassistant/sensor/c/d/config', '{"origin":{"name":"other"}}')]
        self.assertEqual(commissioning.stage_discovery(FakeBroker([(27, rows)])),
                         ('PASS', '1 retained Zigbee2MQTT discovery configs'))
        self.assertEqual(commissioning.stage_discovery(FakeBroker([(27, rows[1:])]))[0], 'FAIL')

    def test_event_requires_live_message_and_ha_update(self):
        broker = FakeBroker([(27, [])])
        self.assertEqual(commissioning.stage_event(broker, 'door', 5, None, None)[0], 'FAIL')
        self.assertIn('-R', broker.calls[0])  # stale retained state is not an event
        states = iter(['t0', 't1'])
        opener = lambda request, timeout: io.BytesIO(json.dumps({'last_updated': next(states)}).encode())
        broker = FakeBroker([(0, [('zigbee2mqtt/door', '{"contact":false}')])])
        status, detail = commissioning.stage_event(broker, 'door', 5, 'binary_sensor.door', 'token', opener)
        self.assertEqual(status, 'PASS')
        self.assertIn('binary_sensor.door updated', detail)

    def test_event_without_ha_update_fails(self):
        opener = lambda request, timeout: io.BytesIO(b'{"last_updated": "same"}')
        clock = iter(range(0, 1000, 5))
        broker = FakeBroker([(0, [('zigbee2mqtt/door', '{}')])])
        with mock.patch.object(commissioning.time, 'sleep'), \
                mock.patch.object(commissioning.time, 'monotonic', side_effect=lambda: next(clock)):
            result = commissioning.stage_event(broker, 'door', 5, 'binary_sensor.door', 't', opener)
        self.assertEqual(result[0], 'FAIL')

    def test_password_travels_on_stdin_not_argv(self):
        captured = {}
        def runner(argv, **kwargs):
            captured.update(argv=argv, **kwargs)
            return subprocess.CompletedProcess(argv, 27, '', '')
        broker = commissioning.Broker.__new__(commissioning.Broker)
        broker.root, broker.runner, broker.password = Path('/unused'), runner, 'secret-value'
        with mock.patch.object(commissioning, 'compose', lambda root, *args: ['docker', 'compose', *args]):
            broker.read('-t', 'x')
        self.assertNotIn('secret-value', ' '.join(captured['argv']))
        self.assertIn('secret-value', captured['input'])


if __name__ == '__main__':
    unittest.main()
