# homeauto stack

Home Assistant Docker-based stack for Raspberry Pi 5 (Debian / Raspberry Pi OS).

## Features
- Home Assistant (Container)
- Zigbee2MQTT (Tuya-friendly)
- Mosquitto MQTT broker
- Android TV control via ADB
- Bluetooth control via host BlueZ
- One-command install, update, uninstall

## Quick start
```bash
cp .env.example .env
nano .env
sudo ./install.sh
```

Access Home Assistant at: http://<pi-ip>:8123
