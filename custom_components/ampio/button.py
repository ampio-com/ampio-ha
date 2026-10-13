"""Ampio impulse outputs, stateless events and scenes."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AmpioEntity, async_send_command, setup_dynamic_entities
from .mapping import impulse_command, is_impulse, writable
from .protocol import AmpioClient, AmpioError


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up events, timed relays and scenes."""
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="button", feature="event", source=lambda client: client.catalog,
        matches=lambda obj, client: obj.get("typ_komponentu") == "event" and writable(obj, client.params),
        factory=AmpioEventButton,
    )
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="button", feature="impulse", source=lambda client: client.catalog,
        matches=lambda obj, client: is_impulse(obj, client.params), factory=AmpioImpulseButton,
    )
    setup_dynamic_entities(
        hass, entry, async_add_entities,
        platform="button", feature="scene", source=lambda client: client.scenes,
        matches=lambda scene, _client: str(scene.get("active", 1)) != "0", factory=AmpioSceneButton,
    )
    async_add_entities([AmpioRefreshButton(entry.runtime_data)])


class AmpioEventButton(AmpioEntity, ButtonEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "event")

    async def async_press(self) -> None:
        await async_send_command(self.client, f"/api/set/{self.object_id}/setValue/255")


class AmpioImpulseButton(AmpioEntity, ButtonEntity):
    def __init__(self, client: AmpioClient, object_id: int) -> None:
        super().__init__(client, object_id, "impulse")

    async def async_press(self) -> None:
        await async_send_command(self.client, impulse_command(self.device, self.client.params))


class AmpioSceneButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "scene"

    def __init__(self, client: AmpioClient, scene_id: int) -> None:
        self.client = client
        self.scene_id = scene_id
        self.ampio_key = scene_id
        self._attr_unique_id = f"{client.gateway_id}:scene:{scene_id}"

    @property
    def name(self) -> str:
        return str(self.client.scenes.get(self.scene_id, {}).get("sceneName") or f"Scena {self.scene_id}")

    @property
    def device_identifier(self) -> tuple[str, str]:
        return (DOMAIN, f"{self.client.gateway_id}:scenes")

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Expose the Ampio server scene number in the entity details."""
        return {"scene_id": self.scene_id}

    @property
    def available(self) -> bool:
        return self.client.available and self.client.states_ready and self.scene_id in self.client.scenes

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={self.device_identifier},
            name="Sceny",
            manufacturer="Ampio",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.add_listener(self.async_write_ha_state))

    async def async_press(self) -> None:
        await async_send_command(self.client, f"/api/run/scene/{self.scene_id}")


class AmpioRefreshButton(ButtonEntity):
    """Reload objects, module details and states from the Ampio server."""

    _attr_has_entity_name = True
    _attr_name = "Refresh"
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client: AmpioClient) -> None:
        self.client = client
        self._attr_unique_id = f"{client.gateway_id}:refresh"

    @property
    def available(self) -> bool:
        return self.client.available

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.client.gateway_id}:gateway")},
            name="Ampio",
            manufacturer="Ampio",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.add_listener(self.async_write_ha_state))

    async def async_press(self) -> None:
        try:
            self.client.refresh()
        except AmpioError as err:
            raise HomeAssistantError(str(err)) from err
