#!/usr/bin/env python3
"""Validate generated Zigbee2MQTT settings with the pinned image's own schema; no radio contacted."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/stack'))
from install import prepare  # noqa: E402

CHECK = r"""
const s = require('/app/dist/util/settings.js');
const errors = s.validate();
const version = s.getPersistedSettings().version;
console.log(JSON.stringify({errors, version, current: s.CURRENT_VERSION}));
process.exit(errors.length === 0 && version === s.CURRENT_VERSION ? 0 : 1);
"""


def image() -> str:
    import yaml
    return yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']['zigbee2mqtt']['image']


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'app'
        prepare(root, ['zigbee'], '/dev/serial/by-id/usb-fixture-if00-port0', 'ember', False,
                'z2m-schema-ci', 'Australia/Sydney', 'new')
        data = root / 'zigbee2mqtt'
        data.chmod(0o755)
        (data / 'configuration.yaml').chmod(0o644)
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                                 '-e', 'ZIGBEE2MQTT_DATA=/app/data', '-v', f'{data}:/app/data:ro',
                                 '--entrypoint', 'node', image(), '-e', CHECK],
                                capture_output=True, text=True, timeout=300)
        lines = [line for line in result.stdout.splitlines() if line.startswith('{')]
        report = json.loads(lines[-1]) if lines else {}
        if result.returncode or report.get('errors'):
            # Schema errors name settings paths only; generated key material is never echoed.
            raise SystemExit(f"FAIL: Zigbee2MQTT rejected generated settings: {report.get('errors', 'no report')}")
        print(f"PASS: {image()} accepts generated settings (schema version {report['version']})")


if __name__ == '__main__':
    main()
