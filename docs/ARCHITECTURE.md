# Architecture

This document describes how the components of the homeauto stack fit together at runtime.

---

## Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  Debian 12 / Raspberry Pi OS Bookworm host                          │
│                                                                      │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐ │
│  │  Docker Compose stack    │  │  Host services (systemd)         │ │
│  │                          │  │                                  │ │
│  │  ┌────────────────────┐  │  │  ha-action-bridge.service        │ │
│  │  │  homeassistant     │  │  │  └─ subscribes MQTT              │ │
│  │  │  :8123 (host net)  │──┼──┼──►  ha/actions/#                │ │
│  │  └────────────────────┘  │  │     executes adb / bluetoothctl  │ │
│  │          │               │  │                                  │ │
│  │          │ MQTT           │  │  bluetooth.service (BlueZ)       │ │
│  │          ▼               │  │  docker.service                  │ │
│  │  ┌────────────────────┐  │  └──────────────────────────────────┘ │
│  │  │  mosquitto         │  │                                      │ │
│  │  │  :1883 (host net)  │  │  /dev/serial/by-id/<zigbee-adapter>  │ │
│  │  └────────────────────┘  │  /run/dbus (D-Bus socket)            │ │
│  │          │               │  /run/udev (udev events)             │ │
│  │          │ MQTT           │                                      │ │
│  │          ▼               │                                      │ │
│  │  ┌────────────────────┐  │                                      │ │
│  │  │  zigbee2mqtt       │  │                                      │ │
│  │  │  :8080 (host net)  │  │                                      │ │
│  │  └────────────────────┘  │                                      │ │
│  └──────────────────────────┘                                      │ │
└──────────────────────────────────────────────────────────────────────┘
```

All three Docker containers use `network_mode: host` so they share the host's
network stack.  This is required for mDNS/multicast discovery (Zeroconf, SSDP)
and keeps the routing topology simple for a home LAN.

---

## Services

### homeassistant

| Property | Value |
|---|---|
| Image | `ghcr.io/home-assistant/home-assistant:stable` |
| Network | host |
| Port | 8123 (HTTP) |
| Config | `./ha/` mounted at `/config` |
| Privileges | `privileged: true` (current phase; required for some integrations) |
| D-Bus | `/run/dbus` mounted read-only (Bluetooth integration) |

The HA container runs **Home Assistant Container** — not HA OS, not Supervisor.
Add-on store and Supervisor features are not available.

### mosquitto

| Property | Value |
|---|---|
| Image | `eclipse-mosquitto:2` |
| Network | host |
| Port | 1883 (MQTT) |
| Config | `./mosquitto/config/` |
| Auth | Required — `allow_anonymous false`, password file |

Mosquitto is the central message bus.  All MQTT consumers (HA, Zigbee2MQTT,
ha-action-bridge) authenticate with the credentials set in `.env`.

### zigbee2mqtt

| Property | Value |
|---|---|
| Image | `koenkk/zigbee2mqtt` |
| Network | host |
| Port | 8080 (web frontend) |
| Config | `./zigbee2mqtt/` mounted at `/app/data` |
| Device | `${ZIGBEE_DEVICE}` → `/dev/zigbee` inside container |

The Zigbee coordinator is mapped into the container using the stable
`/dev/serial/by-id/…` path set in `.env`.

---

## Host-side action bridge

### Why it exists

`shell_command` in Home Assistant Container executes commands **inside the HA
container**, not on the host.  The HA container image does not include `adb` or
`bluetoothctl`, and the host path `/usr/local/bin/ha-actions/` is not mounted
into the container.  A direct `shell_command` approach cannot work.

### How it works

```
HA automation
  └─ action: mqtt.publish { topic: ha/actions/tv_power, payload: "192.168.1.60" }
       │
       ▼
  mosquitto (ha/actions/# topic)
       │
       ▼
  ha-action-bridge.service (host)
    └─ scripts/ha-action-bridge/ha-action-bridge.sh
         └─ ANDROID_TV_IP=192.168.1.60 /usr/local/bin/ha-actions/tv_power.sh
              └─ adb connect 192.168.1.60
                 adb -s 192.168.1.60 shell input keyevent 26
```

1. A Home Assistant automation calls `mqtt.publish` with a topic under
   `ha/actions/`.
2. The **ha-action-bridge** systemd service runs `mosquitto_sub` on the host,
   listening to `ha/actions/#`.
3. On receipt it dispatches to the relevant helper script in
   `/usr/local/bin/ha-actions/`.
4. `adb` and `bluetoothctl` are run on the host where they are available.

### MQTT action topics and payloads

| Topic | Payload | Example payload |
|---|---|---|
| `ha/actions/tv_power` | `<android-tv-ip>` | `192.168.1.60` |
| `ha/actions/tv_home` | `<android-tv-ip>` | `192.168.1.60` |
| `ha/actions/tv_back` | `<android-tv-ip>` | `192.168.1.60` |
| `ha/actions/tv_launch_app` | `<android-tv-ip> <app.package>` | `192.168.1.60 com.netflix.ninja` |
| `ha/actions/bt_connect` | `<bt-mac>` | `AA:BB:CC:DD:EE:FF` |
| `ha/actions/bt_pair_trust` | `<bt-mac> [pin]` | `AA:BB:CC:DD:EE:FF 1234` |

### HA automation example (YAML)

```yaml
automation:
  - alias: "TV Power Toggle"
    trigger: ...
    action:
      - action: mqtt.publish
        data:
          topic: ha/actions/tv_power
          payload: "{{ states('input_text.android_tv_ip') }}"
```

---

## Secrets and credentials

| Secret | Location | Committed? |
|---|---|---|
| `.env` (all credentials) | repo root | ❌ gitignored |
| `ha/secrets.yaml` (HA secrets) | `ha/` | ❌ gitignored |
| `mosquitto/config/passwd` (generated) | `mosquitto/config/` | ❌ gitignored |
| `/etc/ha-action-bridge.env` (bridge credentials) | host `/etc/` | ❌ not in repo |

Example/template files (`.env.example`, `ha/secrets.yaml.example`) **are**
committed and contain only placeholder values.

---

## Networking posture

All services use `network_mode: host`.  No ports are NAT-forwarded from the
host to the internet by this stack.  LAN reachability depends on the host's
firewall configuration (not managed by this repo).

ADB helper scripts explicitly reject non-RFC1918 target IPs.

---

## Startup order

`zigbee2mqtt` and `homeassistant` both declare `depends_on: mosquitto:
condition: service_healthy`.  Compose starts Mosquitto first and waits for it
to pass its healthcheck before starting the dependent services.  This ensures
MQTT is accepting connections before the services that need it start.

Healthchecks:

| Service | Check | Start period |
|---|---|---|
| `mosquitto` | `mosquitto_pub` authenticated publish to `ha/health` | 10 s |
| `homeassistant` | `curl` HTTP GET of `:8123/` | 90 s |
| `zigbee2mqtt` | `wget` HTTP GET of `:8080/` | 60 s |

The Zigbee2MQTT healthcheck will report **unhealthy** if no Zigbee coordinator
is connected (the frontend does not start without a valid adapter).  This is
expected and honest — it does not indicate a configuration error in the stack
itself.

Both HA and Zigbee2MQTT use their own reconnect logic if the MQTT connection is
briefly interrupted after startup.

---

## Zigbee coordinator device mapping

The `.env` variable `ZIGBEE_DEVICE` must point to a stable path such as:

```
/dev/serial/by-id/usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_<serial>-if00-port0
```

This is mapped into the `zigbee2mqtt` container as `/dev/zigbee`, and
`zigbee2mqtt/configuration.yaml` uses `serial.port: /dev/zigbee`.

Use `./system/zigbee-discover.sh` to identify the stable path.
