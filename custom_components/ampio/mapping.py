"""Classify Ampio objects into Home Assistant features without importing Home Assistant."""

from __future__ import annotations

import base64
import math
from typing import Any

from .dictionary import kind

RELAY_TYPES = {"przekaznik", "flaga", "flaga_l", "flaga_p"}
NUMERIC_SENSOR_TYPES = {"temp", "lin_wej", "sensor", "bit8", "bit16", "sbit16", "bit32", "diag"}
BINARY_SENSOR_TYPES = {"wej", "wej_d", "wej_g", "satel_wej", "motion", "presence"}
COVER_TYPES = {"roleta", "roleta_procenty"}


def relay_levels(device: dict[str, Any]) -> tuple[int, int]:
    """Return off/on values, including the legacy 10/30 relay range."""
    try:
        minimum = int(float(device.get("min")))
    except (TypeError, ValueError):
        minimum = 0
    try:
        maximum = int(float(device.get("max")))
    except (TypeError, ValueError):
        maximum = 255
    if (minimum, maximum) == (10, 30):
        return 0, 255
    if maximum == 0:
        maximum = 255
    return minimum, maximum


def state_number(state: dict[str, Any]) -> float | None:
    """Parse a state without treating the string \"0\" as true."""
    raw = state.get("state")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _params(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> dict[str, Any]:
    try:
        return params.get(int(device["id"]), {})
    except (KeyError, TypeError, ValueError):
        return {}


def writable(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> bool:
    """Respect Ampio's read-only flag and omit PIN-protected controls."""
    if device.get("bezpieczne") or device.get("haslo"):
        return False
    try:
        flags = int(_params(device, params).get("params") or 0)
    except (TypeError, ValueError):
        flags = 0
    return not flags & 0x40


def _duration(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> int:
    try:
        return int(_params(device, params).get("czas") or 0)
    except (TypeError, ValueError):
        return 0


def is_stable_switch(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> bool:
    if device.get("typ_komponentu") not in RELAY_TYPES or not writable(device, params):
        return False
    if device.get("funkcja") != device.get("interpretacja"):
        return False
    return _duration(device, params) <= 0


def is_impulse(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> bool:
    if device.get("typ_komponentu") not in RELAY_TYPES or not writable(device, params):
        return False
    return _duration(device, params) > 0 or device.get("funkcja") != device.get("interpretacja")


def impulse_command(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> str:
    object_id = int(device["id"])
    _off, on_value = relay_levels(device)
    duration = _duration(device, params)
    if duration > 0:
        return f"/api/set/{object_id}/setValue/{on_value}/{duration}"
    return f"/api/set/{object_id}/setValue/{on_value}"


def is_light(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> bool:
    if device.get("typ_komponentu") != "led" or kind(device) != "none" or not writable(device, params):
        return False
    try:
        flags = int(_params(device, params).get("params") or 0)
    except (TypeError, ValueError):
        flags = 0
    return not flags & 0x100000


def is_select(device: dict[str, Any], params: dict[int, dict[str, Any]]) -> bool:
    return writable(device, params) and kind(device) == "select"


def is_descriptive_sensor(device: dict[str, Any]) -> bool:
    return kind(device) == "descriptive"


def hardware_id(device: dict[str, Any]) -> int | None:
    """Return the Ampio module id shared by objects on one physical device."""
    try:
        value = int(device.get("id_urzadzenia") or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def hardware_name(hardware: dict[int, dict[str, Any]], device_id: int) -> str:
    """Use the name from the device_details list when the server sent it."""
    record = hardware.get(device_id) or {}
    label = _device_label(record.get("nazwa_urzadzenia") or record.get("device_name"))
    return label or f"Ampio {device_id}"


def hardware_details(record: dict[str, Any]) -> dict[str, str]:
    """Type, firmware and MAC from the separate device_details query."""
    details: dict[str, str] = {}
    device_type = record.get("typ_urzadzenia")
    if device_type not in (None, ""):
        pcb = record.get("wersja_pcb")
        details["model"] = f"type {device_type}" if pcb in (None, "") else f"type {device_type} / pcb {pcb}"
    software = record.get("wersja_softu")
    if software not in (None, ""):
        details["sw_version"] = str(software)
    if record.get("wersja_pcb") not in (None, ""):
        details["hw_version"] = str(record.get("wersja_pcb"))
    formatted = _mac_hex(record.get("mac_local") or record.get("mac"))
    if formatted:
        details["serial_number"] = formatted
    return details


def _mac_hex(raw: Any) -> str:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return f"{value:X}"


def _device_label(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError):
        return text
    if decoded and decoded.isprintable():
        return decoded
    return text
