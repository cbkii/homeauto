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


class BridgeHardeningTests(unittest.TestCase):
    def config(self, **tv):
        return dict(mqtt=dict(username='bridge', password='x'), tv={'lounge': dict(host='192.168.1.20', **tv)},
                    bluetooth={})

    def test_numeric_or_malformed_targets_rejected_at_config_load(self):
        import json, tempfile
        for bad in [dict(host=3232235796), dict(host='192.168.1.20', port='5555'),
                    dict(host='192.168.1.20', port=True), dict(host='192.168.1.20', packages='com.x'),
                    dict(host='8.8.8.8')]:
            data = self.config(); data['tv']['lounge'] = bad
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'a.json'; path.write_text(json.dumps(data)); path.chmod(0o600)
                with self.assertRaises((ValueError, TypeError), msg=str(bad)):
                    bridge.config_read(path)

    def test_worker_survives_unexpected_executor_errors(self):
        import threading, time
        calls = []
        def executor(action, request, config):
            calls.append(request['request_id'])
            if len(calls) == 1:
                raise TypeError('unexpected')
        dispatcher = bridge.Dispatcher(self.config(), executor=executor)
        threading.Thread(target=dispatcher.worker, daemon=True).start()
        for rid in ['first_request_1', 'second_request_2']:
            dispatcher.receive('ha/actions/tv_home', json.dumps(
                dict(target='lounge', request_id=rid, expires=time.time() + 30)).encode())
        dispatcher.pending.join()
        self.assertEqual(calls, ['first_request_1', 'second_request_2'])

    def test_replay_rejected_across_restart_and_cache_private(self):
        import tempfile, time
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / 'seen-requests.json'
            payload = json.dumps(dict(target='lounge', request_id='captured_req_1', expires=time.time() + 30)).encode()
            bridge.Dispatcher(self.config(), cache=cache).receive('ha/actions/tv_home', payload)
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
            restarted = bridge.Dispatcher(self.config(), cache=cache)
            with self.assertRaises(ValueError):
                restarted.receive('ha/actions/tv_home', payload)
            cache.write_text('{"old_req_000001": 1}')  # expired entries are dropped on load
            self.assertEqual(bridge.Dispatcher(self.config(), cache=cache).seen, {})
            cache.write_text('not json')
            self.assertEqual(bridge.Dispatcher(self.config(), cache=cache).seen, {})
