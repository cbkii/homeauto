# Support boundaries

Debian 12 and Debian 13 (Trixie), ARM64/AMD64 are source-validation targets.
The Radxa Dragon Q8B is the primary commissioning target. No target has current
hardware sign-off from this Work session. [Q8B evidence](platforms/Q8B_AUDIT_2026-11-15.md)
is dated observation, not a runtime test of these changes.

Home Assistant Container requires Docker Engine >=23 and Compose. Standard
system Docker is the initial target; rootless/userns-remapped daemon, alternate
architectures and custom integrations need permission/runtime qualification.
No automatic Docker install, kernel/UEFI/firmware update, firewall/network change,
router replacement, HA OS/Supervisor or coordinator flashing is provided.

Core HA runs without privileged mode, device mounts or D-Bus. This deliberately
qualifies the HA/MQTT/SQLite feature set first. Bluetooth needs the opt-in overlay
with NET_ADMIN/NET_RAW and read-only `/run/dbus`, plus working host BlueZ. Other
hardware integrations require separately reviewed capabilities/device mappings;
core least privilege is not a promise that every HA integration already works.

Current explicit image candidates are in `docker-compose.yml`; they require
ARM64/AMD64 manifest checks and real service tests before promotion. Registry
availability does not prove runtime compatibility. No unattended image updates.

Default dashboard and broker bindings are loopback except HA host discovery.
Container port publication can bypass UFW; the firewall helper must remain a
planner, not assurance of network isolation. Inspect Docker forwarding and LAN
access before changing any binding. No WAN/NAT configuration is automated.

Optional SQL, extras, actions, Bluetooth and Zigbee must not block HA/MQTT core.
A complete Compose wait may fail if an optional service is unhealthy; core stays
independently restartable. Missing coordinator does not become a core dependency.

References checked 15 November 2026:
- https://www.home-assistant.io/installation/linux/
- https://www.home-assistant.io/integrations/bluetooth/
- https://docs.docker.com/engine/install/debian/
- https://www.zigbee2mqtt.io/guide/installation/02_docker.html
