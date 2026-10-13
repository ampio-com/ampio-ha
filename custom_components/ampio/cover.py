"""Ampio rollers and percentage covers."""

from __future__ import annotations

from homeassistant.components.cover import ATTR_POSITION, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AmpioEntity, async_send_command, setup_dynamic_entities
from .mapping import COVER_TYPES, state_number, writable
from .protocol import AmpioClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up basic and percentage rollers. Slats stay excluded."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="cover", feature="cover", source=lambda client: client.catalog,
        matches=lambda obj, client: obj.get("typ_komponentu") in COVER_TYPES and writable(obj, client.params),
        factory=AmpioCover,
    )


class AmpioCover(AmpioEntity, CoverEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "cover")

    @property
    def supported_features(self) -> CoverEntityFeature:
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if self.device.get("typ_komponentu") == "roleta_procenty":
            features |= CoverEntityFeature.SET_POSITION
        return features

    @property
    def current_cover_position(self) -> int | None:
        if self.device.get("typ_komponentu") != "roleta_procenty":
            return None
        number = state_number(self.client.states.get(self.object_id, {}))
        if number is None:
            return None
        value = int(number)
        return value if 0 <= value <= 100 else None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return position == 0 if position is not None else None

    async def async_open_cover(self, **kwargs: object) -> None:
        await async_send_command(self.client, f"/api/set/{self.object_id}/open")

    async def async_close_cover(self, **kwargs: object) -> None:
        await async_send_command(self.client, f"/api/set/{self.object_id}/close")

    async def async_stop_cover(self, **kwargs: object) -> None:
        await async_send_command(self.client, f"/api/set/{self.object_id}/stop")

    async def async_set_cover_position(self, **kwargs: object) -> None:
        position = int(kwargs[ATTR_POSITION])
        if not 0 <= position <= 100:
            raise ValueError("Invalid cover position")
        await async_send_command(
            self.client, f"/api/set/{self.object_id}/setRollerPos/{position}/101",
            lambda state: state_number(state) == position,
        )
