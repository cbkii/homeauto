# Optional host action bridge

Try native HA **Android TV Remote** / **Android Debug Bridge** first. The host
bridge is an opt-in fallback. Core never installs/enables it or waits for it.

`--with-actions` during preparation creates a protected `actions.json` with the
dedicated MQTT bridge account and empty target allowlists. Edit it locally:
`tv` maps friendly names to private IPv4 `host`, `port` (default 5555), and an
allowlist of `packages`; `bluetooth` maps names to exact MACs. Unknown targets,
packages, keys, expired/replayed/retained commands and payloads >512 bytes are
rejected. MQTTv5 retain-as-published preserves the retained flag even on live delivery. One worker and a 16-item queue bound concurrency. Commands use fixed
argv with timeouts, no shell or raw command execution; logs omit payload/targets.
Pairing/PIN automation and the former plain-text protocol are intentionally
removed. Re-authorise ADB as the dedicated user; existing root ADB keys are not
copied. Bluetooth D-Bus/polkit permissions need separate qualification.

For an explicitly selected bridge, first review the Debian package plan for
`python3-paho-mqtt` (Paho 2), and `adb`/`bluez` only as needed. The complete unit
assumes a stable checkout at `/opt/homeauto`. Review or back up any existing files
before replacing them. The initial setup commands are:

```bash
sudo systemd-sysusers /opt/homeauto/scripts/ha-action-bridge/homeauto-actions.conf
sudo install -d -m 0750 -o root -g homeauto-actions /etc/homeauto
sudo install -m 0640 -o root -g homeauto-actions /srv/homeauto/actions.json /etc/homeauto/actions.json
sudo -u homeauto-actions python3 /opt/homeauto/scripts/ha-action-bridge/bridge.py --config /etc/homeauto/actions.json --check-config
sudo install -m 0644 /opt/homeauto/scripts/ha-action-bridge/ha-action-bridge.service /etc/systemd/system/ha-action-bridge.service
sudo systemd-analyze verify /etc/systemd/system/ha-action-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now ha-action-bridge.service
systemctl status ha-action-bridge.service --no-pager
journalctl -u ha-action-bridge.service --no-pager
```

The dedicated system user has no sudo or Docker group membership. The unit uses
its own state/home directory, read-only system, private devices/temp, bounded
restart/backoff, and journald. Config is group-readable only to this account.

HA publishes non-retained JSON to `ha/actions/tv_home` (or `tv_power`, `tv_back`,
`tv_launch_app`, `bt_connect`): `target`, unique `request_id` (8–80 safe chars),
and numeric Unix `expires` between now and 60 seconds ahead. Launch also requires
an allowlisted `package`. Credentials are never in the MQTT payload.

Rollback: `sudo systemctl disable --now ha-action-bridge.service`. It has no
core dependency. Preserve the private config while investigating; delete it only
as an explicit separate action. Do not enable the old root shell dispatcher.

References: https://www.home-assistant.io/integrations/androidtv_remote/
https://www.home-assistant.io/integrations/androidtv/
https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html
