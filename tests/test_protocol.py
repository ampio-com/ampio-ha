"""Protocol regression tests using an in-process MQTT double."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "ampio"


class _Ack:
    def __init__(self, published: bool = True) -> None:
        self.rc = 0
        self._published = published

    def wait_for_publish(self, _timeout=None) -> None:
        return None

    def is_published(self) -> bool:
        return self._published


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.published = []
        self.stopped = False
        self.ack = True

    def username_pw_set(self, *_args):
        pass

    def reconnect_delay_set(self, **_kwargs):
        pass

    def connect(self, *_args):
        pass

    def publish(self, topic, payload, **_kwargs):
        self.published.append((topic, payload))
        return _Ack(self.ack)

    def subscribe(self, *_args, **_kwargs):
        return 0, 1

    def disconnect(self):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        self.stopped = True


mqtt = types.ModuleType("paho.mqtt.client")
mqtt.Client = FakeClient
mqtt.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
mqtt.MQTT_ERR_SUCCESS = 0
sys.modules.setdefault("paho", types.ModuleType("paho"))
sys.modules.setdefault("paho.mqtt", types.ModuleType("paho.mqtt"))
sys.modules["paho.mqtt.client"] = mqtt

spec = importlib.util.spec_from_file_location("ampio_protocol_test", ROOT / "protocol.py")
protocol = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(protocol)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootstrap_state_and_command_origin(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._handle_message("ampio/fromDB/anna/data/info", {"Results": {"device_id": "gateway-1", "haCommandSource": True}})
        client._handle_message("ampio/fromDB/anna/data/device_details", {"List": [{"id": 12, "prawa": "1", "typ_komponentu": "przekaznik"}]})
        client._handle_message("ampio/fromDB/anna/data/params_devices", {"List": []})
        client._handle_message("ampio/fromDB/anna/data/states", {"List": [{"id": 12, "stan_json": json.dumps({"state": "0"})}]})
        await asyncio.wait_for(client._ready, 1)
        client._handle_message("ampio/fromDB/anna/ob/12/state", {"state": "255"})
        self.assertEqual(client.states[12]["state"], "255")
        client.command("/api/set/12/setValue/0")
        self.assertEqual(client._client.published[-1], ("ampio/control/anna/ha/api", "/api/set/12/setValue/0"))

    async def test_missing_capability_is_rejected(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._handle_message("ampio/fromDB/anna/data/info", {"Results": {"device_id": "gateway-1"}})
        with self.assertRaises(protocol.AmpioCompatibilityError):
            await client._ready

    async def test_catalog_replaces_removed_objects_and_bad_state_is_ignored(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        topic = "ampio/fromDB/anna/data/device_details"
        client._handle_message(topic, {"List": [{"id": 1}, {"id": 2}]})
        client._handle_message(topic, {"List": [{"id": 2}]})
        self.assertEqual(set(client.catalog), {2})
        client._handle_message("ampio/fromDB/anna/data/states", {"List": [{"id": 2, "stan_json": "invalid"}]})
        self.assertEqual(client.states, {})

    async def test_retained_md5_is_raw_text_and_requests_catalog(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        message = types.SimpleNamespace(topic="ampio/fromDB/anna/md5/devices", payload=b"abc123")
        client._on_message(client._client, None, message)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(client._client.published[-1], ("ampio/control/anna/data", "device_details"))

    async def test_reconnect_requires_fresh_snapshot(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._states_loaded = True
        client._section_sent["devices"] = 1
        client._disconnected()
        self.assertFalse(client.available)
        self.assertFalse(client.states_ready)
        self.assertEqual(client._section_sent, {})

    async def test_stale_catalog_response_is_discarded(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._section_sent["device_details"] = 1
        client._section_dirty.add("device_details")
        topic = "ampio/fromDB/anna/data/device_details"
        client._handle_message(topic, {"List": [{"id": 1}]})
        self.assertEqual(client.catalog, {})
        self.assertIn("device_details", client._section_sent)
        client._handle_message(topic, {"List": [{"id": 2}]})
        self.assertEqual(set(client.catalog), {2})

    async def test_command_requires_current_authorization(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client.catalog[12] = {"id": 12}
        with self.assertRaises(protocol.AmpioError):
            client.command("/api/set/99/setValue/1")
        client.scenes[4] = {"id": 4}
        client.command("/api/run/scene/4")
        self.assertEqual(client._client.published[-1][0], "ampio/control/anna/ha/api")

    async def test_confirm_waits_for_state_and_times_out(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client.catalog[12] = {"id": 12}
        pending = asyncio.create_task(client.async_confirm("/api/set/12/setValue/255", lambda state: state.get("state") == "255", timeout=1))
        await asyncio.sleep(0)
        client._handle_message("ampio/fromDB/anna/ob/12/state", {"state": "255"})
        await pending
        with self.assertRaises(protocol.AmpioTimeoutError):
            await client.async_confirm("/api/set/12/setValue/0", lambda state: state.get("state") == "0", timeout=0.01)

    async def test_reconnect_auth_failure_is_reported_once(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected.set_result(None)
        client._ready.set_result(None)
        seen: list[Exception] = []
        client.add_auth_listener(seen.append)
        client._reject(protocol.AmpioAuthError("rejected"))
        client._reject(protocol.AmpioAuthError("rejected"))
        self.assertEqual(len(seen), 1)
        client._connected_ok()
        client._reject(protocol.AmpioAuthError("rejected again"))
        self.assertEqual(len(seen), 2)

    async def test_refresh_requests_catalog_and_states(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._client.published.clear()
        await client.refresh()
        self.assertEqual(
            [item[1] for item in client._client.published],
            ["device_details", "params_devices", "scenes", "api/json/states", "", ""],
        )
        self.assertEqual(
            [item[0] for item in client._client.published[-2:]],
            ["ampio/control/anna/get_conditions/1", "ampio/control/anna/get_conditions/2"],
        )

    async def test_conditions_and_irrigation_run_as_separate_lists(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._handle_message(
            "ampio/fromDB/anna/conditions/1",
            {"List": [{"id": 4, "name": "Trawnik", "active": 1, "type": 1}]},
        )
        client._handle_message(
            "ampio/fromDB/anna/conditions/2",
            {"List": [{"id": 8, "name": "Wieczór", "active": 1, "type": 2}]},
        )
        self.assertEqual(set(client.irrigations), {4})
        self.assertEqual(set(client.conditions), {8})
        client.command("/api/run/condition/4")
        client.command("/api/run/condition/8")
        self.assertEqual(
            [item[1] for item in client._client.published[-2:]],
            ["/api/run/condition/4", "/api/run/condition/8"],
        )
        with self.assertRaises(protocol.AmpioError):
            client.command("/api/run/condition/9")
        client._handle_message("ampio/fromDB/anna/conditions/1", {"error": True, "List": []})
        self.assertEqual(set(client.irrigations), {4})

    async def test_failed_device_details_does_not_clear_the_catalog(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        topic = "ampio/fromDB/anna/data/device_details"
        client._handle_message(topic, {"List": [{"id": 12, "prawa": "1", "typ_komponentu": "przekaznik"}]})
        client._handle_message(topic, {"error": True, "List": []})
        self.assertEqual(set(client.catalog), {12})

    async def test_device_details_do_not_replace_objects(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._handle_message(
            "ampio/fromDB/anna/data/device_details",
            {"List": [
                {"id": 12, "id_urzadzenia": 7, "prawa": "1", "nazwa_urzadzenia": "Salon", "typ_urzadzenia": 12, "wersja_softu": 400, "mac_local": 255},
                {"id": 13, "id_urzadzenia": 0, "prawa": "1", "nazwa_urzadzenia": "Loose"},
            ]},
        )
        self.assertEqual(set(client.catalog), {12, 13})
        self.assertEqual(set(client.hardware), {7})
        self.assertEqual(client.hardware[7]["nazwa_urzadzenia"], "Salon")

    async def test_live_md5_discards_the_inflight_catalog_and_refetches(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._section_sent["device_details"] = 1
        message = types.SimpleNamespace(
            topic="ampio/fromDB/anna/md5/devices", payload=b"new", retain=False,
        )
        client._on_message(client._client, None, message)
        await asyncio.sleep(0)
        self.assertIn("device_details", client._section_dirty)
        client._handle_message(
            "ampio/fromDB/anna/data/device_details",
            {"List": [{"id": 1, "prawa": "1", "typ_komponentu": "przekaznik"}]},
        )
        self.assertEqual(client.catalog, {})
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(client._client.published[-1], ("ampio/control/anna/data", "device_details"))
        self.assertIn("device_details", client._section_sent)

    async def test_retained_md5_before_the_session_is_up_does_not_fail_connect(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        message = types.SimpleNamespace(
            topic="ampio/fromDB/anna/md5/devices", payload=b"abc123", retain=True,
        )
        client._on_message(client._client, None, message)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(client._client.published, [])
        self.assertFalse(client._connected.done())

    async def test_retained_digest_does_not_discard_the_inflight_catalog(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._section_sent["device_details"] = 1
        message = types.SimpleNamespace(
            topic="ampio/fromDB/anna/md5/devices", payload=b"abc123", retain=True,
        )
        client._on_message(client._client, None, message)
        await asyncio.sleep(0)
        self.assertNotIn("device_details", client._section_dirty)
        self.assertEqual(client._client.published, [])

    async def test_broker_rejecting_a_subscription_fails_setup(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._subscribe_mids[7] = "ampio/fromDB/anna/data/#"
        client._on_subscribe(client._client, None, 7, [types.SimpleNamespace(is_failure=True, value=128)], None)
        await asyncio.sleep(0)
        self.assertIsInstance(client._connected.exception(), protocol.AmpioError)

    async def test_unacknowledged_publish_is_an_error(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client.catalog[12] = {"id": 12}
        client._client.ack = False
        with self.assertRaises(protocol.AmpioTimeoutError):
            await client.async_confirm("/api/set/12/setValue/1")

    async def test_cancelled_connect_stops_the_session(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        task = asyncio.create_task(client.connect(timeout=5))
        await asyncio.sleep(0.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(client._running)
        self.assertTrue(client._client.stopped)

    async def test_live_state_survives_older_snapshot(self):
        client = protocol.AmpioClient("localhost", 1883, "anna", "secret")
        client._connected_ok()
        client._state_request = 1
        client._handle_message("ampio/fromDB/anna/ob/12/state", {"state": "255"})
        client._handle_message("ampio/fromDB/anna/data/states", {"List": [{"id": 12, "stan_json": {"state": "0"}}]})
        self.assertEqual(client.states[12]["state"], "255")


spec_dict = importlib.util.spec_from_file_location("ampio_dictionary_test", ROOT / "dictionary.py")
dictionary = importlib.util.module_from_spec(spec_dict)
assert spec_dict and spec_dict.loader
spec_dict.loader.exec_module(dictionary)


class DictionaryTests(unittest.TestCase):
    def test_four_column_equality_dictionary(self):
        device = {"typ_komponentu": "led", "uwagi": "0=Off=1=0;255=On=1=1;"}
        self.assertEqual(dictionary.choices(device), {"Off": "0", "On": "255"})

    def test_duplicate_labels_are_rejected(self):
        device = {"typ_komponentu": "led", "uwagi": "0=Same=1=0;1=Same=1=1;"}
        self.assertEqual(dictionary.choices(device), {})

    def test_threshold_dictionary_is_not_a_select(self):
        device = {"typ_komponentu": "led", "uwagi": "0=Low=2=0;10=High=2=1;"}
        self.assertEqual(dictionary.kind(device), "descriptive")
        self.assertEqual(dictionary.choices(device), {})


mapping_pkg = types.ModuleType("ampio_component")
mapping_pkg.__path__ = [str(ROOT)]
sys.modules["ampio_component"] = mapping_pkg
symbols_spec = importlib.util.spec_from_file_location("ampio_component.symbols", ROOT / "symbols.py")
symbols_module = importlib.util.module_from_spec(symbols_spec)
sys.modules["ampio_component.symbols"] = symbols_module
assert symbols_spec and symbols_spec.loader
symbols_spec.loader.exec_module(symbols_module)
dictionary_spec = importlib.util.spec_from_file_location("ampio_component.dictionary", ROOT / "dictionary.py")
dictionary_module = importlib.util.module_from_spec(dictionary_spec)
sys.modules["ampio_component.dictionary"] = dictionary_module
assert dictionary_spec and dictionary_spec.loader
dictionary_spec.loader.exec_module(dictionary_module)
mapping_spec = importlib.util.spec_from_file_location("ampio_component.mapping", ROOT / "mapping.py")
mapping = importlib.util.module_from_spec(mapping_spec)
assert mapping_spec and mapping_spec.loader
mapping_spec.loader.exec_module(mapping)


class MappingTests(unittest.TestCase):
    def test_impulse_relay_is_a_button_and_stable_relay_is_a_switch(self):
        stable = {"id": 1, "typ_komponentu": "przekaznik", "funkcja": "1", "interpretacja": "1", "min": 0, "max": 1}
        impulse = {"id": 2, "typ_komponentu": "przekaznik", "funkcja": "1", "interpretacja": "1", "min": 0, "max": 255}
        params = {2: {"czas": 5}}
        self.assertTrue(mapping.is_stable_switch(stable, {}))
        self.assertFalse(mapping.is_impulse(stable, {}))
        self.assertTrue(mapping.is_impulse(impulse, params))
        self.assertFalse(mapping.is_stable_switch(impulse, params))
        self.assertEqual(mapping.impulse_command(impulse, params), "/api/set/2/setValue/255/5")
        timed = {**impulse, "czas": 8}
        self.assertEqual(mapping.impulse_command(timed, {}), "/api/set/2/setValue/255/8")

    def test_roller_position_matches_five_percent_steps(self):
        self.assertEqual(mapping.roller_step(0), 0)
        self.assertEqual(mapping.roller_step(37), 35)
        self.assertEqual(mapping.roller_step(38), 40)
        self.assertEqual(mapping.roller_step(100), 100)

    def test_dictionary_led_is_not_a_dimmer(self):
        led = {"id": 3, "typ_komponentu": "led", "uwagi": "0=Off=1=0;1=On=1=1;"}
        self.assertFalse(mapping.is_light(led, {}))
        self.assertTrue(mapping.is_select(led, {}))

    def test_string_zero_is_numeric_off(self):
        self.assertEqual(mapping.state_number({"state": "0"}), 0.0)

    def test_objects_share_one_hardware_device_name(self):
        objects = {
            1: {"id": 1, "id_urzadzenia": 7, "nazwa_urzadzenia": "U2Fsb24="},
            2: {"id": 2, "id_urzadzenia": 7},
            3: {"id": 3, "id_urzadzenia": 0},
        }
        self.assertEqual(mapping.hardware_id(objects[1]), 7)
        self.assertIsNone(mapping.hardware_id(objects[3]))
        hardware = {7: {"id": 7, "nazwa_urzadzenia": "U2Fsb24=", "typ_urzadzenia": 12, "wersja_softu": 400, "mac_local": 255}}
        self.assertEqual(mapping.hardware_name(hardware, 7), "Salon")
        self.assertEqual(mapping.hardware_name({}, 7), "Ampio 7")
        self.assertEqual(mapping.hardware_details(hardware[7])["model"], "M-RGBW")
        self.assertEqual(mapping.symbol_name(10, 8), "M-SERV-MINI-s")
        self.assertEqual(mapping.symbol_name(10, 99), "M-SERV-s")
        self.assertEqual(mapping.hardware_details(hardware[7])["sw_version"], "400")
        self.assertEqual(mapping.hardware_details(hardware[7])["serial_number"], "FF")


if __name__ == "__main__":
    unittest.main()
