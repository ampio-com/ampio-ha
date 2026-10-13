"""Ampio dimmable LED outputs."""

from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AmpioEntity, async_send_command, setup_dynamic_entities
from .mapping import is_light, state_number
from .protocol import AmpioClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up plain 0–255 LEDs. Dictionary LEDs use select or a descriptive sensor."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="light", feature="light", source=lambda client: client.catalog,
        matches=lambda obj, client: is_light(obj, client.params), factory=AmpioLight,
    )


class AmpioLight(AmpioEntity, LightEntity):
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "light")

    @property
    def brightness(self) -> int | None:
        number = state_number(self.client.states.get(self.object_id, {}))
        if number is None:
            return None
        return max(0, min(255, int(number)))

    @property
    def is_on(self) -> bool | None:
        value = self.brightness
        return value > 0 if value is not None else None

    async def async_turn_on(self, **kwargs: object) -> None:
        value = max(1, min(255, int(kwargs.get(ATTR_BRIGHTNESS, 255))))
        await async_send_command(
            self.client, f"/api/set/{self.object_id}/setValue/{value}",
            lambda state: state_number(state) == value,
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        await async_send_command(
            self.client, f"/api/set/{self.object_id}/setValue/0",
            lambda state: state_number(state) == 0,
        )
