"""Parse Designer dictionaries without Home Assistant dependencies."""

from __future__ import annotations

import logging
import math

_LOGGER = logging.getLogger(__name__)
_DICTIONARY_TYPES = {"led", "flaga_liniowa", "flaga_liniowa16"}
_OPERATORS = {"1", "2", "3", "4", "5"}
_invalid_logged: set[int] = set()


def kind(device: dict) -> str:
    """Return none, select, descriptive, or invalid."""
    if device.get("typ_komponentu") not in _DICTIONARY_TYPES:
        return "none"
    text = str(device.get("uwagi") or "")
    if not text.strip():
        return "none"
    parsed: list[tuple[str, str]] = []
    values: set[float] = set()
    labels: set[str] = set()
    other_operator = False
    for row in text.split(";"):
        if not row.strip():
            continue
        columns = row.split("=")
        if len(columns) < 4:
            return _invalid(device)
        raw, label, operator = columns[0].strip(), columns[1].strip(), columns[2].strip()
        if not raw or not label or operator not in _OPERATORS:
            return _invalid(device)
        try:
            number = float(raw)
        except ValueError:
            return _invalid(device)
        if not math.isfinite(number) or number in values or label in labels:
            return _invalid(device)
        other_operator = other_operator or operator != "1"
        parsed.append((label, raw))
        values.add(number)
        labels.add(label)
    if not parsed:
        return "none"
    if other_operator:
        return "descriptive"
    if len(parsed) >= 2:
        return "select"
    return _invalid(device)


def choices(device: dict) -> dict[str, str]:
    """Map unique labels to raw values for an equality dictionary."""
    if kind(device) != "select":
        return {}
    result: dict[str, str] = {}
    for row in str(device.get("uwagi") or "").split(";"):
        if not row.strip():
            continue
        columns = row.split("=")
        result[columns[1].strip()] = columns[0].strip()
    return result


def _invalid(device: dict) -> str:
    try:
        object_id = int(device.get("id") or 0)
    except (TypeError, ValueError):
        object_id = 0
    if object_id not in _invalid_logged:
        _invalid_logged.add(object_id)
        _LOGGER.warning("Ampio object %s has an ambiguous dictionary and is not exposed", object_id or "?")
    return "invalid"
