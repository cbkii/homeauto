# Existing deployments and MariaDB

Do not run the fresh installer over an existing checkout/data directory. The
new installer deliberately refuses unmarked occupied roots and preserves old
HA `.storage`, secrets, SQL history and Zigbee network state.

1. Record the running checkout commit, exact image IDs, active profiles and
   coordinator identity. Keep that checkout and its original `.env` private.
2. Take a consistent backup on the old version: stop writers for file copies;
   use a verified MariaDB logical dump. Copy it off-device and test restoration.
3. Stage a separate root/project on an isolated host (or separate ports); never
   run two instances against one coordinator, database or MQTT network.
4. Preserve the existing `recorder.db_url` and its secrets if MariaDB history is
   required. Enable the new `mariadb` profile and restore the tested dump to the
   same supported DB version before starting the existing HA configuration.
   The service's `MARIADB_DATABASE`/`MARIADB_USER` (`homeauto`) apply only when an
   empty datadir is first initialised; they do not rename anything. Keep the legacy
   database and user by importing a dump that includes the `mysql` system schema
   (`--all-databases`), or create the legacy database/user and grants explicitly
   before starting HA. Then confirm `recorder.db_url` connects with the legacy names.
5. Existing host-networked HA may reach the optional DB via `127.0.0.1:3306`.
   Preserve the original DB name/user/password and update the protected password
   files deliberately. Do not replace them with fresh generated credentials.
6. Remove only obsolete HA YAML broker keys, and add the MQTT integration via
   UI. Retain valid YAML MQTT entities. Do not rewrite HA `.storage` directly.
7. Validate imported history, entities, automations and Zigbee events before
   network/service cutover. Stop old writers before final sync.

HA does not support automatic recorder history migration between DB engines.
Choosing SQLite for a fresh deployment does not migrate an existing MariaDB
history. Rollback needs matching old images/configuration/data; an image-only
downgrade after DB migration is unsafe. Keep the Pi bootable until acceptance.

The historical Compose file is preserved for comparison. Existing deployments
remain on their old checkout until an operator completes this explicit migration;
there is no unattended in-place conversion.

References: https://www.home-assistant.io/integrations/recorder/
