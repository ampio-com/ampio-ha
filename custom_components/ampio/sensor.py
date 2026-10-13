"""Ampio numeric sensors and descriptive dictionaries."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AmpioEntity, setup_dynamic_entities
from .mapping import NUMERIC_SENSOR_TYPES, is_descriptive_sensor, state_number
from .protocol import AmpioClient


def _supported(obj: dict, _client: AmpioClient) -> bool:
    return obj.get("typ_komponentu") in NUMERIC_SENSOR_TYPES or is_descriptive_sensor(obj)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up numeric inputs and threshold dictionaries. Power classes stay excluded."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="sensor", feature="value", source=lambda client: client.catalog,
        matches=_supported, factory=AmpioSensor,
    )


class AmpioSensor(AmpioEntity, SensorEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "value")

    @property
    def device_class(self) -> SensorDeviceClass | None:
        if is_descriptive_sensor(self.device):
            return None
        return SensorDeviceClass.TEMPERATURE if self.device.get("typ_komponentu") == "temp" else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        if is_descriptive_sensor(self.device):
            return None
        return "°C" if self.device.get("typ_komponentu") == "temp" else None

    @property
    def native_value(self) -> float | int | str | None:
        state = self.client.states.get(self.object_id, {})
        if is_descriptive_sensor(self.device):
            description = state.get("desc")
            return None if description in (None, "") else str(description)
        if "state" not in state:
            return None
        number = state_number(state)
        if number is not None:
            return number
        raw = state.get("state")
        return None if raw is None else str(raw)
