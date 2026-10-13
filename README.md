# Ampio for Home Assistant

Local Home Assistant integration for Ampio. Home Assistant connects directly to the Ampio MQTT broker with an Ampio username and password. It does not require Home Assistant's MQTT integration or a shared broker.

## Status

A separate, unaffiliated [community Ampio integration](https://github.com/pszypowicz/ampio-homeassistant) and [draft Core PR](https://github.com/home-assistant/core/pull/179548) already exist. See [existing integration](docs/EXISTING_INTEGRATION.md) before publishing or installing both.

Source implementation for a hardware pilot. Install it from this GitHub repository as a HACS custom repository. It is not in the default HACS catalog or Home Assistant Core. It requires an Ampio server build that publishes `haCommandSource: true` in `ampio/fromDB/<user>/data/info` and accepts commands on `ampio/control/<user>/ha/api`. A live Ampio installation is required to validate device semantics, permissions and installer behavior.

## Install for a pilot

1. Update `ampio-server` to a build with the HA topic change. Configure its Mosquitto authorization plugin to allow the authenticated Ampio user to publish to their own `ampio/control/<user>/ha/api`; deny other users' topic trees.
2. Create a regular Ampio user in Designer and assign access to the desired objects. Avoid using the administrator account for a permanent HA setup.
3. In HACS, open **Integrations → Custom repositories**, add `https://github.com/ampio-com/ampio-ha` with category **Integration**, then download Ampio and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Ampio**. Enter the local server address, MQTT port and Ampio credentials. Use port `1883` for native MQTT if enabled, or select WebSocket and port `9001` if that listener is enabled. A network connection to the Ampio server is required.

The integration stores host, port, transport, username and password in the HA config entry. It exposes only objects visible to that Ampio account. It waits for the server catalog and initial states before creating entities. On reconnect it requests them again; while offline, entities are unavailable.

## Supported in this pilot

- `switch`: normal relay and flag outputs with stable on/off values. PIN-protected and read-only outputs are excluded. Turning on or off waits for the server state.
- `button`: impulse and timed relay outputs, simple event outputs, and configured scenes.
- `light`: plain 0–255 LED outputs without custom range or dictionary.
- `cover`: basic rollers and percentage rollers. Slats are excluded.
- `sensor`: temperature and generic numeric/text inputs. Unit-sensitive power and energy classes are excluded pending hardware fixtures.
- `binary_sensor`: Ampio input, motion and presence types; device classes require per-type validation.
- `select`: writable equality dictionaries with unique numeric values and labels. A dictionary that is not an equality list does not become a dimmer; threshold dictionaries are text sensors.

Other Ampio types, including alarms, locks, climate, cameras, multimedia and energy aggregation, need separate hardware validation before exposure. See the mapping in `ampio-server/docs/HOME_ASSISTANT_OBJECT_MAPPING.md`.

The `ha` segment only tags the command source. The server removes it and dispatches to the existing API handler with a distinct action log `source`. The tag is not an authentication proof of the client application: another program with the same Ampio credentials may publish it. Object permissions still apply.

## Remove

In **Settings → Devices & services**, open Ampio and select **Delete**. Then remove the `custom_components/ampio` directory (or uninstall it through HACS) and restart Home Assistant. If a dedicated Ampio user was created, remove or disable that account in Designer separately.

## Development

The protocol client is the PyPI package `ampio-python`. Home Assistant installs `ampio-python==0.1.0` from the integration manifest. Edit `packages/ampio-python` and publish a new release to ship protocol changes.

Run `python3 -m compileall custom_components/ampio` and `python3 -m unittest discover -s tests`. A hardware pilot must verify ACL isolation, catalog changes, reboot/reconnect, action attribution, device ranges and dictionaries. See `docs/CORE_HANDOFF.md` for the later Core submission scope.
