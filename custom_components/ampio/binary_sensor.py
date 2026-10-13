"""Ampio binary inputs."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AmpioEntity, setup_dynamic_entities
from .mapping import BINARY_SENSOR_TYPES, state_number
from .protocol import AmpioClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up binary inputs. Device classes stay unset until each type is confirmed."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="binary_sensor", feature="binary", source=lambda client: client.catalog,
        matches=lambda obj, _client: obj.get("typ_komponentu") in BINARY_SENSOR_TYPES, factory=AmpioBinarySensor,
    )


class AmpioBinarySensor(AmpioEntity, BinarySensorEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "binary")

    @property
    def is_on(self) -> bool | None:
        if self.object_id not in self.client.states:
            return None
        number = state_number(self.client.states[self.object_id])
        return None if number is None else number != 0
