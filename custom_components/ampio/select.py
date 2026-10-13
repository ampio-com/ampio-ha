"""Ampio writable equality dictionaries."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .dictionary import choices
from .entity import AmpioEntity, async_send_command, setup_dynamic_entities
from .mapping import is_select, state_number
from ampio_python import AmpioClient


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up equality dictionaries. Threshold dictionaries are sensors."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="select", feature="select", source=lambda client: client.catalog,
        matches=lambda obj, client: is_select(obj, client.params), factory=AmpioSelect,
    )


class AmpioSelect(AmpioEntity, SelectEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "select")

    @property
    def options(self) -> list[str]:
        return list(choices(self.device))

    @property
    def current_option(self) -> str | None:
        number = state_number(self.client.states.get(self.object_id, {}))
        if number is None:
            return None
        for label, raw in choices(self.device).items():
            if float(raw) == number:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        raw = choices(self.device).get(option)
        if raw is None:
            raise ValueError("Invalid Ampio option")
        await async_send_command(
            self.client, f"/api/set/{self.object_id}/setValue/{raw}",
            lambda state: state_number(state) == float(raw),
        )
