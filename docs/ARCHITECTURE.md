# Architecture

The Q8B is an independent Debian LAN server. Its UEFI, kernel, storage, fan,
network interfaces, router and Pi rollback are outside this application's scope.

| Service | Network | Persistent state | Dependency |
| --- | --- | --- | --- |
| Home Assistant | Host, 8123 | `ha/` including SQLite | None |
| Mosquitto | Compose bridge, host loopback 1883 | `mosquitto/` | None |
| Zigbee2MQTT (`zigbee`) | Bridge, loopback 8080 | `zigbee2mqtt/` | Healthy MQTT; its own serial device |
| MariaDB (`mariadb`) | Bridge, loopback 3306 | `mariadb/` | None; HA not automatically switched |
| ESPHome (`extras`) | Host, dashboard loopback 6052 | `esphome/` | None |
| Node-RED (`extras`) | Bridge, loopback 1880 | `nodered/` | None |

HA retains multicast discovery without giving every service the host network.
Its core has no USB, D-Bus or privileged requirement. Bluetooth is a separate
explicit capability/D-Bus overlay, requiring actual host testing.

All state lives outside source under a marked data root. Preparation snapshots
the Compose files and creates credentials and network material once. Operations
use the snapshot, never whichever checkout happens to be the current directory.
Image tags are explicit candidates, **not proof of Q8B qualification**.

HA's broker is configured through its supported UI; its `.storage` is not edited
by scripts. Mosquitto uses separate HA/Zigbee/action/health users with topic ACLs.
The action bridge remains optional; prefer native Android TV integration.
No `shell_command` host execution is used.

Optional service loss can fail a complete `--wait` invocation while HA/MQTT stay
running. Healthchecks report real frontend/broker readiness, not evidence of a
paired Zigbee event. Hotplug recovery may require recreating just Z2M to remap
the serial device; never reset the whole USB controller.
