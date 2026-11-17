#!/usr/bin/env python3
"""Check exact selected tags for ARM64/AMD64; no pull/update or daemon required."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from homeauto import REPO, run

IMAGES = [
    'ghcr.io/home-assistant/home-assistant:2026.11.1',
    'eclipse-mosquitto:2.0.22',
    'ghcr.io/koenkk/zigbee2mqtt:2.14.3',
    'mariadb:11.8.3',
    'ghcr.io/esphome/esphome:2026.10.2',
    'nodered/node-red:4.1.1',
]


def architectures(data):
    if isinstance(data, list):
        return {x.get('Descriptor', {}).get('platform', {}).get('architecture') for x in data}
    return {x.get('platform', {}).get('architecture') for x in data.get('manifests', [])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=['text', 'json'], default='text')
    args = parser.parse_args()
    records = []
    for image in IMAGES:
        try:
            result = run(['docker', 'manifest', 'inspect', '--verbose', image], timeout=90)
            if result.returncode:
                raise ValueError('Registry unavailable or image missing')
            data = json.loads(result.stdout)
            arches = architectures(data)
            ok = {'arm64', 'amd64'} <= arches
            descriptors = data if isinstance(data, list) else [data]
            records.append(dict(image=image, status='PASS' if ok else 'BLOCK',
                                architectures=sorted(a for a in arches if a),
                                digests=[x.get('Descriptor', {}).get('digest') for x in descriptors]))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            records.append(dict(image=image, status='BLOCK', detail='Manifest unavailable/unparseable'))
    if args.format == 'json':
        print(json.dumps(records, indent=2))
    else:
        for row in records:
            print(row['status'], row['image'])
    return 0 if all(r['status'] == 'PASS' for r in records) else 2


if __name__ == '__main__':
    sys.exit(main())
