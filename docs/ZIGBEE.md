# Zigbee commissioning (SLZB-07 family and other serial coordinators)

Nothing here flashes firmware, resets the radio or pairs devices. Zigbee is an
optional profile: if the coordinator is missing or blocked, HA and MQTT keep running.

## 1. Identify the exact radio (read-only)

All five SMLIGHT SLZB-07 variants use the same Silicon Labs CP2102N USB bridge,
so `lsusb` (`10c4:ea60`) cannot identify the radio:

| Variant (label) | Radio | `--zigbee-adapter` | `--zigbee-rtscts` |
| --- | --- | --- | --- |
| SLZB-07 | EFR32MG21 | `ember` | `true` |
| SLZB-07Mg24 | EFR32MG24 | `ember` | `true` |
| SLZB-07Mg26 | EFR32MG26 | `ember` | `true` |
| SLZB-07p7 | CC2652P7 | `zstack` | `false` |
| SLZB-07p10 | CC2674P10 | `zstack` | `false` |

Flow control follows SMLIGHT's SLZB-07 Zigbee2MQTT manual (MGx: `rtscts: true`;
pX: `rtscts: false`); other vendors' sticks need their own documented value, so
the installer requires it explicitly. Baud rate stays at the Zigbee2MQTT default.
SMLIGHT notes some SLZB-07 sticks shipped with older EZSP firmware intended for
the deprecated `ezsp` driver; `ember` then fails to connect (not destructive).
Updating radio firmware is a separate, explicitly approved step: this repository
never flashes.

Confirm the printed label, then run the read-only preflight with the stable link:

```bash
ls -l /dev/serial/by-id/                      # use this path, never /dev/ttyUSB*
./install.sh --preflight-only --profiles zigbee \
  --zigbee-device /dev/serial/by-id/<link> --zigbee-adapter <ember|zstack> --zigbee-rtscts <true|false>
```

`coordinator-variant` reads only the USB product descriptor (never the serial
number). `BLOCK` means the descriptor names a variant that needs the other
adapter or the other documented flow control; `WARN` means the descriptor does not identify the radio, so rely on the
label. Neither proves the firmware is Zigbee coordinator firmware (a stick
reflashed for Thread or as a router will simply fail to start in Z2M; this is
not destructive).

## 2. Decide the network before the first start

On first start Zigbee2MQTT compares its configured network with the radio. With
`ember`, and with `zstack` when no `coordinator_backup.json` exists, a mismatch
makes it **form a new network from the configuration, replacing any network on
the stick**. Devices paired to an old network would need re-pairing.

`--prepare` therefore requires `--zigbee-network new`, which records that you
accept a new network (generated private key, PAN and extended PAN, stored once
under the data root and backed up with it). Only use it when the stick holds no
network you need. If you are unsure, assume it does and use section 3.

```bash
sudo ./install.sh --prepare --data-dir /srv/homeauto --with-zigbee \
  --zigbee-device /dev/serial/by-id/<link> --zigbee-adapter <ember|zstack> \
  --zigbee-rtscts <true|false> --zigbee-network new
```

Roots prepared before this decision existed are blocked from a Zigbee first start
(core still starts) until re-prepared in a new root or adopted as below.

## 3. Keeping an existing network (manual, not automated)

There is no automated import. On the old host, stop Zigbee2MQTT and copy its whole
data directory privately (`configuration.yaml`, `coordinator_backup.json`,
`database.db`, `state.json`, any `secret.yaml`). Prepare the new root with
`--zigbee-network new` but **do not apply**. Then, in
`/srv/homeauto/zigbee2mqtt/configuration.yaml`, replace the generated
`advanced.network_key`, `pan_id`, `ext_pan_id` (and set `channel`) with the
**exact** old values, and copy `coordinator_backup.json`, `database.db` and
`state.json` alongside. Keep the generated `mqtt` and `serial` sections. A typo
in a network value is destructive with `ember`: compare before starting.
Never run two Zigbee2MQTT instances against one coordinator or network.

## 4. Start and verify MQTT -> Z2M -> HA

```bash
sudo ./install.sh --apply --data-dir /srv/homeauto
sudo python3 scripts/smoke/commissioning.py --data-dir /srv/homeauto
```

Add the MQTT integration in HA (see README), then pair a device from the Z2M UI
(`ssh -L 8080:127.0.0.1:8080 USER@Q8B`; permit join only while pairing). For the
end-to-end acceptance tier, operate the device while the check waits:

```bash
sudo python3 scripts/smoke/commissioning.py --data-dir /srv/homeauto \
  --device '<friendly name>' --wait 120 \
  --ha-entity binary_sensor.<entity> --ha-token-file /root/.homeauto-ha-token   # 0600
```

The check is read-only: it publishes nothing and prints a UTC-timestamped stage
table (broker auth, bridge online with coordinator type/firmware/channel, retained
HA discovery, live device event, HA entity update). IEEE addresses, payloads and
credentials are not printed. Keep the output as acceptance evidence.

Back up after the first successful start: `coordinator_backup.json` and the
generated network values are what make a later restore or adapter replacement
possible.

References (checked 2026-11-17): SMLIGHT SLZB-07 product pages (variant radios);
Zigbee2MQTT 2.14.3 image (`settings.CURRENT_VERSION` 5, discovery subscription);
https://www.zigbee2mqtt.io/guide/faq/ (backup/restore support: zstack and ember).
