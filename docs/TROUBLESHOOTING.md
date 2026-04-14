# Troubleshooting

Common issues and how to resolve them.

---

## Home Assistant not reachable at :8123

**Check container status:**
```bash
docker compose ps
docker compose logs homeassistant
```

**Common causes:**
- Stack not started — run `docker compose up -d`.
- First-boot initialisation still in progress — wait 60–90 s, then try again.
- HA is starting but failed its own init — check logs for Python errors.

---

## MQTT connection errors in Home Assistant or Zigbee2MQTT

**Symptoms:** HA shows MQTT integration as unavailable; Zigbee2MQTT logs
`Connection refused` or `bad user name or password`.

**Check Mosquitto is running:**
```bash
docker compose ps mosquitto
docker compose logs mosquitto
```

**Verify credentials match across all three places:**
1. `.env` (`MQTT_USER`, `MQTT_PASS`)
2. `ha/secrets.yaml` (`mqtt_user`, `mqtt_password`)
3. `zigbee2mqtt/configuration.yaml` (`mqtt.user`, `mqtt.password`)

**Regenerate the password file if credentials were changed:**
```bash
sudo ./install.sh --rotate-mqtt-password --no-start
docker compose restart mosquitto
```

**Test connectivity manually:**
```bash
mosquitto_sub -h 127.0.0.1 -u <user> -P <pass> -t 'test/#' -v &
mosquitto_pub -h 127.0.0.1 -u <user> -P <pass> -t test/ping -m hello
```

---

## Zigbee2MQTT won't start / can't open serial port

**Check device mapping:**
```bash
ls -l /dev/serial/by-id/
```

The path in `.env` (`ZIGBEE_DEVICE`) must exist and be a valid USB-serial device.

**Rediscover adapter:**
```bash
./system/zigbee-discover.sh
```

Update `.env` and restart:
```bash
docker compose restart zigbee2mqtt
```

**Check for port conflicts** (e.g., another process holding the serial port):
```bash
fuser /dev/serial/by-id/<your-adapter>
```

---

## ha-action-bridge not executing scripts

**Check service status:**
```bash
systemctl status ha-action-bridge
journalctl -fu ha-action-bridge
```

**Verify MQTT credentials in bridge env file:**
```bash
sudo cat /etc/ha-action-bridge.env
```

These are written by `install.sh` from `.env`.  If credentials changed,
re-run `sudo ./install.sh --no-start` to refresh them, then:
```bash
systemctl restart ha-action-bridge
```

**Test by publishing an action manually:**
```bash
mosquitto_pub -h 127.0.0.1 -u <user> -P <pass> \
  -t ha/actions/tv_power -m "192.168.1.60"
```

Then check `journalctl -fu ha-action-bridge` for dispatch output.

---

## ADB helper scripts fail

**Symptoms:** `adb: command not found`, or the TV doesn't respond.

**Prerequisites:**
- `adb` must be installed on the host: `apt-get install -y adb`
- The Android TV must have USB debugging (ADB over TCP) enabled.
- The TV must be reachable on the LAN from the host.

**Verify:**
```bash
adb connect <android-tv-ip>
adb devices
```

If `adb connect` returns `connection refused`, enable ADB on the TV:
*Settings → Device Preferences → Developer Options → Network debugging*.

**LAN-only check:** helper scripts refuse non-RFC1918 IPs.  Ensure
`ANDROID_TV_IP` is a private LAN address.

---

## Bluetooth scripts fail

**Symptoms:** `bluetoothctl` errors, device not found, pairing fails.

**Check BlueZ service:**
```bash
systemctl status bluetooth
```

**Check available adapters:**
```bash
bluetoothctl list
```

**Common issues:**
- The host Bluetooth adapter is not available or is blocked.
- `BT_DEVICE_MAC` is incorrect — double-check the MAC address.
- The device is out of range or already connected to another host.
- For `bt_pair_trust`: the device must be in pairing mode when the script runs.

**Unblock the adapter if rfkill-blocked:**
```bash
rfkill unblock bluetooth
```

---

## Zigbee devices not appearing in HA

1. Confirm Zigbee2MQTT is running and connected to the coordinator:
   - Check `http://<host-ip>:8080` frontend.
   - Check `docker compose logs zigbee2mqtt`.
2. Confirm `permit_join: true` in `zigbee2mqtt/configuration.yaml` while pairing.
3. Confirm the `homeassistant: true` flag is set in Zigbee2MQTT config so it
   publishes HA discovery messages via MQTT.

---

## Docker daemon not running (CI / non-standard environments)

`docker compose config` and `docker compose ps` require a running Docker daemon.
In CI environments that use nested containers (e.g., GitHub Actions with
DinD not configured), the Docker socket may be unavailable.

For the QA script, this is expected to fail in such environments.  Run on a
real host with a Docker daemon for full validation.

---

## Stack upgrade fails / containers stuck

**Force-recreate all containers:**
```bash
docker compose up -d --force-recreate
```

**Pull fresh images:**
```bash
docker compose pull
docker compose up -d
```

**Remove orphaned volumes if state is corrupt:**
```bash
docker compose down -v
docker compose up -d
```

⚠️ `down -v` removes anonymous volumes.  Named volumes and bind mounts (your
`ha/`, `zigbee2mqtt/`, `mosquitto/` directories) are preserved.
