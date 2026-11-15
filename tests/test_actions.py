import importlib.util
import json
from pathlib import Path
import queue
import time
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).resolve().parents[1] / 'scripts/ha-action-bridge/bridge.py')
bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.config = {'tv': {'lounge': {'host': '192.168.1.2', 'packages': ['com.example.app']}}, 'bluetooth': {}}
        self.payload = dict(target='lounge', request_id='test_request_123', expires=time.time() + 30)

    def test_only_allowed_target_schema_and_package(self):
        action, payload = bridge.validate('ha/actions/tv_home', json.dumps(self.payload).encode(), self.config)
        self.assertEqual(action, 'tv_home')
        for bad in [dict(self.payload, target='other'), dict(self.payload, command='sh'),
                    dict(self.payload, expires=0), dict(self.payload, expires=time.time() + 1000)]:
            with self.assertRaises(ValueError):
                bridge.validate('ha/actions/tv_home', json.dumps(bad).encode(), self.config)
        for package in ['com.example.app; reboot', 'com.unknown.app']:
            with self.assertRaises(ValueError):
                bridge.validate('ha/actions/tv_launch_app', json.dumps(dict(self.payload, package=package)).encode(), self.config)

    def test_replay_retained_and_oversize_refused(self):
        dispatcher = bridge.Dispatcher(self.config)
        encoded = json.dumps(self.payload).encode()
        with self.assertRaises(ValueError):
            dispatcher.receive('ha/actions/tv_home', encoded, retained=True)
        dispatcher.receive('ha/actions/tv_home', encoded)
        with self.assertRaises(ValueError):
            dispatcher.receive('ha/actions/tv_home', encoded)
        with self.assertRaises(ValueError):
            dispatcher.receive('ha/actions/tv_home', b'x' * 513)
        self.assertEqual(dispatcher.pending.qsize(), 1)

    def test_bounded_queue(self):
        dispatcher = bridge.Dispatcher(self.config)
        for index in range(16):
            dispatcher.receive('ha/actions/tv_home', json.dumps(dict(self.payload, request_id=f'test_request_{index:03}')).encode())
        with self.assertRaises(queue.Full):
            dispatcher.receive('ha/actions/tv_home', json.dumps(dict(self.payload, request_id='test_request_999')).encode())


if __name__ == '__main__':
    unittest.main()
