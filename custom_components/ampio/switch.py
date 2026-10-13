"""Ampio relay switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AmpioEntity, async_send_command, setup_dynamic_entities
from .mapping import is_stable_switch, relay_levels, state_number
from .protocol import AmpioClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up stable Ampio relays. Impulse outputs are buttons."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="switch", feature="switch", source=lambda client: client.catalog,
        matches=lambda obj, client: is_stable_switch(obj, client.params), factory=AmpioSwitch,
    )


class AmpioSwitch(AmpioEntity, SwitchEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "switch")

    @property
    def is_on(self) -> bool | None:
        number = state_number(self.client.states.get(self.object_id, {}))
        if number is None:
            return None
        off, _on = relay_levels(self.device)
        return number not in (0, off)

    async def async_turn_on(self, **kwargs: object) -> None:
        off, on = relay_levels(self.device)
        await async_send_command(
            self.client, f"/api/set/{self.object_id}/setValue/{on}",
            lambda state: (value := state_number(state)) is not None and value not in (0, off),
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        off, _on = relay_levels(self.device)
        await async_send_command(
            self.client, f"/api/set/{self.object_id}/setValue/{off}",
            lambda state: (value := state_number(state)) is not None and value in (0, off),
        )
