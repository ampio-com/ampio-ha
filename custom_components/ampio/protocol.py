"""Ampio MQTT transport and protocol parsing; no Home Assistant imports."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)
CATALOG_SECTIONS = ("device_details", "params_devices", "groups", "group_devices", "scenes")
STORED_SECTIONS = ("params_devices", "scenes")
MAX_PAYLOAD_BYTES = 2_000_000
COMMAND_TIMEOUT = 8.0
StatePredicate = Callable[[dict[str, Any]], bool]


class AmpioError(Exception):
    """Base Ampio error."""


class AmpioAuthError(AmpioError):
    """Broker rejected the credentials."""


class AmpioCompatibilityError(AmpioError):
    """The server does not support source-tagged HA commands."""


class AmpioTimeoutError(AmpioError):
    """The server did not publish the expected state in time."""


class AmpioClient:
    """One MQTT connection per HA config entry; callbacks are serialized on the HA loop."""

    def __init__(self, host: str, port: int, username: str, password: str, *, websocket: bool = False) -> None:
        if not username or any(character in username for character in "/+#"):
            raise ValueError("Invalid Ampio username for MQTT topics")
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self._loop = asyncio.get_running_loop()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets" if websocket else "tcp")
        self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=2, max_delay=30)
        self._connected: asyncio.Future[None] = self._loop.create_future()
        self._ready: asyncio.Future[None] = self._loop.create_future()
        self._running = False
        self.available = False
        self.gateway_id: str | None = None
        self.info: dict[str, Any] = {}
        self.catalog: dict[int, dict[str, Any]] = {}
        self.hardware: dict[int, dict[str, Any]] = {}
        self.params: dict[int, dict[str, Any]] = {}
        self.scenes: dict[int, dict[str, Any]] = {}
        self.states: dict[int, dict[str, Any]] = {}
        self.catalog_generation = 0
        self._catalog_loaded = False
        self._params_loaded = False
        self._scenes_loaded = False
        self._states_loaded = False
        self._section_sent: dict[str, int] = {}
        self._section_dirty: set[str] = set()
        self._section_epoch = 0
        self._state_request: int | None = None
        self._states_changed_during_request: set[int] = set()
        self._devices_applied = 0
        self._waiters: dict[int, list[tuple[StatePredicate, asyncio.Future[None]]]] = {}
        self._listeners: set[Callable[[], None]] = set()
        self._catalog_listeners: set[Callable[[], None]] = set()
        self._auth_listeners: set[Callable[[AmpioAuthError], None]] = set()
        self._auth_notified = False

    @property
    def states_ready(self) -> bool:
        """A complete state snapshot has arrived for the current connection."""
        return self._states_loaded

    @property
    def params_ready(self) -> bool:
        """The params catalog has arrived, so timed and PIN outputs can be classified."""
        return self._params_loaded

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def add_catalog_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._catalog_listeners.add(listener)
        return lambda: self._catalog_listeners.discard(listener)

    def add_auth_listener(self, listener: Callable[[AmpioAuthError], None]) -> Callable[[], None]:
        """Notify once when a reconnect is rejected. Cleared after the next successful login."""
        self._auth_listeners.add(listener)
        return lambda: self._auth_listeners.discard(listener)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _notify_catalog(self) -> None:
        for listener in tuple(self._catalog_listeners):
            listener()

    async def connect(self, timeout: float = 15) -> None:
        """Connect and wait for server capability, catalog, params and initial state."""
        if self._running:
            return
        self._running = True
        try:
            await asyncio.to_thread(self._client.connect, self.host, self.port, 60)
            self._client.loop_start()
            await asyncio.wait_for(self._connected, timeout)
            await asyncio.wait_for(self._ready, timeout)
        except (OSError, TimeoutError, AmpioError):
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        self._running = False
        self.available = False
        self._states_loaded = False
        self._fail_waiters(AmpioError("Ampio MQTT connection is unavailable"))
        await asyncio.to_thread(self._client.disconnect)
        await asyncio.to_thread(self._client.loop_stop)
        self._notify()

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if getattr(reason_code, "is_failure", False):
            error: Exception
            if _auth_rejected(reason_code):
                error = AmpioAuthError("Ampio rejected the credentials")
            else:
                error = AmpioError(f"Cannot connect to Ampio: {reason_code}")
            self._loop.call_soon_threadsafe(self._reject, error)
            return
        root = f"ampio/fromDB/{self.username}"
        for topic in (f"{root}/data/#", f"{root}/md5/#", f"{root}/ob/#"):
            result, _ = client.subscribe(topic, qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                self._loop.call_soon_threadsafe(self._reject, AmpioError(f"Cannot subscribe: {topic}"))
                return
        self._loop.call_soon_threadsafe(self._connected_ok)
        client.publish(f"ampio/control/{self.username}/info", "info", qos=1)
        for section in CATALOG_SECTIONS:
            if section not in self._section_sent:
                self._send_section_request(client, section)
        if self._state_request is None:
            self._send_state_request(client)

    def _connected_ok(self) -> None:
        self.available = True
        self._catalog_loaded = False
        self._params_loaded = False
        self._scenes_loaded = False
        self._states_loaded = False
        if not self._connected.done():
            self._connected.set_result(None)
        self._auth_notified = False
        self._notify()

    def _reject(self, error: Exception) -> None:
        reconnect = self._connected.done() and self._ready.done()
        if not self._connected.done():
            self._connected.set_exception(error)
        elif not self._ready.done():
            self._ready.set_exception(error)
        self.available = False
        self._fail_waiters(error)
        if reconnect and isinstance(error, AmpioAuthError) and not self._auth_notified:
            self._auth_notified = True
            for listener in tuple(self._auth_listeners):
                listener(error)
            self._client.disconnect()
        self._notify()

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, _flags: Any, _reason_code: Any, _properties: Any) -> None:
        self._loop.call_soon_threadsafe(self._disconnected)

    def _disconnected(self) -> None:
        self.available = False
        self._states_loaded = False
        self._section_sent.clear()
        self._section_dirty.clear()
        self._state_request = None
        self._states_changed_during_request.clear()
        self._fail_waiters(AmpioError("Ampio MQTT connection is unavailable"))
        self._notify()

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        payload_bytes = message.payload or b""
        if len(payload_bytes) > MAX_PAYLOAD_BYTES:
            _LOGGER.warning("Ampio payload on %s exceeds %s bytes", message.topic, MAX_PAYLOAD_BYTES)
            return
        if f"ampio/fromDB/{self.username}/md5/" in message.topic:
            self._loop.call_soon_threadsafe(self._handle_message, message.topic, None)
            return
        try:
            payload = json.loads(payload_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            _LOGGER.warning("Invalid JSON on Ampio topic %s", message.topic)
            return
        self._loop.call_soon_threadsafe(self._handle_message, message.topic, payload)

    def _handle_message(self, topic: str, payload: Any) -> None:
        root = f"ampio/fromDB/{self.username}/"
        if not topic.startswith(root):
            return
        suffix = topic[len(root):]
        catalog_changed = False
        if suffix == "data/info":
            info = payload.get("Results") if isinstance(payload, dict) else None
            if not isinstance(info, dict):
                return
            self.info = info
            self.gateway_id = str(info.get("device_id") or "") or None
            if not info.get("haCommandSource"):
                self._reject(AmpioCompatibilityError("Ampio server does not support ha/api"))
                return
            if not self.gateway_id:
                self._reject(AmpioCompatibilityError("Ampio server has no stable device_id"))
                return
        elif suffix == "data/device_details":
            if self._accept_section("device_details"):
                items = self._items(payload)
                if items is not None:
                    self._store_device_details(items)
                    catalog_changed = True
                    if self._devices_applied > 1:
                        self._request_states()
            self._continue_section("device_details")
        elif suffix == "data/states":
            self._store_states(payload)
        elif suffix.startswith("data/"):
            section = suffix[5:]
            if section in CATALOG_SECTIONS:
                if self._accept_section(section):
                    catalog_changed = self._store_section(section, payload)
                self._continue_section(section)
        elif suffix.startswith("ob/") and suffix.endswith("/state"):
            parts = suffix.split("/")
            if len(parts) != 3 or not parts[1].isdigit() or not isinstance(payload, dict):
                return
            object_id = int(parts[1])
            self.states[object_id] = {**self.states.get(object_id, {}), **payload}
            if self._state_request is not None:
                self._states_changed_during_request.add(object_id)
            self._resolve_waiters(object_id)
        elif suffix.startswith("md5/"):
            section = suffix[4:]
            if section in ("devices", "device_details"):
                self._request_section("device_details")
            elif section in CATALOG_SECTIONS:
                self._request_section(section)
            return
        else:
            return
        if (
            self.info
            and self.gateway_id
            and self._catalog_loaded
            and self._params_loaded
            and self._states_loaded
            and not self._ready.done()
        ):
            self._ready.set_result(None)
        if catalog_changed:
            self._notify_catalog()
        self._notify()

    def _accept_section(self, section: str) -> bool:
        """Apply a response only when no newer catalog signal is already waiting."""
        if section not in self._section_sent:
            return True
        self._section_sent.pop(section)
        return section not in self._section_dirty

    def _continue_section(self, section: str) -> None:
        if section not in self._section_dirty:
            return
        self._section_dirty.discard(section)
        self._request_section(section)

    def _store_device_details(self, items: list[dict[str, Any]]) -> None:
        catalog: dict[int, dict[str, Any]] = {}
        hardware: dict[int, dict[str, Any]] = {}
        for item in items:
            if self._valid_id(item) and str(item.get("prawa", "1")) != "0":
                catalog[int(item["id"])] = item
            module_id = self._module_id(item)
            if module_id is not None:
                hardware[module_id] = item
        self.catalog = catalog
        self.hardware = hardware
        self._catalog_loaded = True
        self._devices_applied += 1
        self.catalog_generation += 1

    def _store_section(self, section: str, payload: Any) -> bool:
        items = self._items(payload)
        if items is None or section not in STORED_SECTIONS:
            return False
        if section == "params_devices":
            self.params = {int(item["id"]): item for item in items if self._valid_id(item)}
            self._params_loaded = True
        elif section == "scenes":
            self.scenes = {int(item["id"]): item for item in items if self._valid_id(item)}
            self._scenes_loaded = True
        return True

    def _store_states(self, payload: Any) -> None:
        items = self._items(payload)
        request = self._state_request
        self._state_request = None
        if request is not None and self._section_dirty_states():
            self._states_changed_during_request.clear()
            self._section_dirty.discard("states")
            self._request_states()
            return
        if items is None:
            return
        next_states = {
            object_id: self.states[object_id]
            for object_id in self._states_changed_during_request
            if object_id in self.states
        }
        for item in items:
            if not self._valid_id(item):
                continue
            object_id = int(item["id"])
            if object_id in self._states_changed_during_request:
                continue
            state = item.get("stan_json")
            if isinstance(state, str):
                try:
                    state = json.loads(state)
                except json.JSONDecodeError:
                    continue
            if isinstance(state, dict):
                next_states[object_id] = state
        self._states_changed_during_request.clear()
        self.states = next_states
        self._states_loaded = True
        for object_id in next_states:
            self._resolve_waiters(object_id)

    def _section_dirty_states(self) -> bool:
        return "states" in self._section_dirty

    def refresh(self) -> None:
        """Ask the server again for objects, parameters, scenes and states."""
        if not self.available:
            raise AmpioError("Ampio MQTT connection is unavailable")
        for section in ("device_details", "params_devices", "scenes"):
            self._request_section(section)
        self._request_states()

    def _request_section(self, section: str) -> None:
        if section in self._section_sent:
            self._section_dirty.add(section)
            return
        self._send_section_request(self._client, section)

    def _send_section_request(self, client: mqtt.Client, section: str) -> None:
        self._section_epoch += 1
        self._section_sent[section] = self._section_epoch
        client.publish(f"ampio/control/{self.username}/data", section, qos=1)

    def _request_states(self) -> None:
        if self._state_request is not None:
            self._section_dirty.add("states")
            return
        self._send_state_request(self._client)

    def _send_state_request(self, client: mqtt.Client) -> None:
        self._section_epoch += 1
        self._state_request = self._section_epoch
        self._states_changed_during_request.clear()
        self._section_dirty.discard("states")
        client.publish(f"ampio/control/{self.username}/states", "api/json/states", qos=1)

    @staticmethod
    def _items(payload: Any) -> list[dict[str, Any]] | None:
        items = payload.get("List") if isinstance(payload, dict) else None
        return items if isinstance(items, list) else None

    @staticmethod
    def _module_id(item: Any) -> int | None:
        if not isinstance(item, dict):
            return None
        try:
            value = int(item.get("id_urzadzenia") or 0)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _valid_id(item: Any) -> bool:
        try:
            return isinstance(item, dict) and int(item["id"]) > 0
        except (KeyError, TypeError, ValueError):
            return False

    def _publish(self, topic: str, payload: str) -> None:
        if not self.available:
            raise AmpioError("Ampio MQTT connection is unavailable")
        result = self._client.publish(topic, payload, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise AmpioError(f"MQTT publish failed: {result.rc}")

    def _authorize(self, path: str) -> int | None:
        if path.startswith("/api/set/"):
            parts = path.split("/")
            if len(parts) < 5 or not parts[3].isdigit() or int(parts[3]) <= 0:
                raise ValueError("Unsupported Ampio command")
            object_id = int(parts[3])
            if object_id not in self.catalog:
                raise AmpioError("Ampio object is not authorized")
            return object_id
        if path.startswith("/api/run/scene/"):
            scene_id = path.removeprefix("/api/run/scene/")
            if not scene_id.isdigit() or int(scene_id) <= 0 or int(scene_id) not in self.scenes:
                raise AmpioError("Ampio scene is not authorized")
            return None
        raise ValueError("Unsupported Ampio command")

    async def async_confirm(self, path: str, predicate: StatePredicate | None = None, timeout: float = COMMAND_TIMEOUT) -> None:
        """Publish a command and, when a resulting state is known, wait for it."""
        object_id = self._authorize(path)
        if predicate is not None and object_id is not None and predicate(self.states.get(object_id, {})):
            return
        future: asyncio.Future[None] | None = None
        if predicate is not None and object_id is not None:
            future = self._loop.create_future()
            self._waiters.setdefault(object_id, []).append((predicate, future))
        try:
            self._publish(f"ampio/control/{self.username}/ha/api", path)
            if future is None:
                return
            await asyncio.wait_for(future, timeout)
        except TimeoutError as err:
            raise AmpioTimeoutError("Ampio did not confirm the command") from err
        finally:
            if future is not None and object_id is not None:
                self._waiters[object_id] = [
                    waiter for waiter in self._waiters.get(object_id, []) if waiter[1] is not future
                ]

    def command(self, path: str) -> None:
        """Publish a command without waiting for a state echo."""
        self._authorize(path)
        self._publish(f"ampio/control/{self.username}/ha/api", path)

    def _resolve_waiters(self, object_id: int) -> None:
        state = self.states.get(object_id, {})
        pending = self._waiters.get(object_id, [])
        if not pending:
            return
        kept: list[tuple[StatePredicate, asyncio.Future[None]]] = []
        for predicate, future in pending:
            if future.done():
                continue
            if predicate(state):
                future.set_result(None)
            else:
                kept.append((predicate, future))
        self._waiters[object_id] = kept

    def _fail_waiters(self, error: Exception) -> None:
        for pending in self._waiters.values():
            for _predicate, future in pending:
                if not future.done():
                    future.set_exception(error)
        self._waiters.clear()


def _auth_rejected(reason_code: Any) -> bool:
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value) in (4, 5, 134, 135)
    except (TypeError, ValueError):
        text = str(reason_code).lower()
        return "auth" in text or "password" in text or "not authorized" in text
