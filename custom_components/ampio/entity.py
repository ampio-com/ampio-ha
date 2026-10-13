"""Common Ampio entity lifecycle and dynamic catalog support."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .mapping import hardware_id, hardware_name
from .protocol import AmpioClient, AmpioError, AmpioTimeoutError

StatePredicate = Callable[[dict[str, Any]], bool]


class AmpioEntity(Entity):
    """An Ampio object, identified independently of name and login."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "object"

    def __init__(self, client: AmpioClient, object_id: int, feature: str) -> None:
        self.client = client
        self.object_id = object_id
        self.ampio_key = object_id
        self._attr_unique_id = f"{client.gateway_id}:{object_id}:{feature}"

    @property
    def device(self) -> dict[str, Any]:
        return self.client.catalog.get(self.object_id, {})

    @property
    def available(self) -> bool:
        return self.client.available and self.client.states_ready and self.object_id in self.client.catalog

    @property
    def name(self) -> str:
        """Object name from Designer. The device name is the Ampio module."""
        return str(self.device.get("opis_menu") or f"Obiekt {self.object_id}")

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Expose the Ampio server object number in the entity details."""
        return {"object_id": self.object_id}

    @property
    def device_identifier(self) -> tuple[str, str]:
        module_id = hardware_id(self.device)
        if module_id is None:
            return (DOMAIN, f"{self.client.gateway_id}:object:{self.object_id}")
        return (DOMAIN, f"{self.client.gateway_id}:device:{module_id}")

    @property
    def device_info(self) -> DeviceInfo:
        module_id = hardware_id(self.device)
        if module_id is None:
            device_name = self.name
        else:
            device_name = hardware_name(self.client.catalog, module_id)
        return DeviceInfo(
            identifiers={self.device_identifier},
            name=device_name,
            manufacturer="Ampio",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.add_listener(self._updated))

    def _updated(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()


async def async_send_command(client: AmpioClient, path: str, predicate: StatePredicate | None = None) -> None:
    """Publish a command and surface a refusal or missing confirmation in the UI."""
    try:
        await client.async_confirm(path, predicate)
    except AmpioTimeoutError as err:
        raise HomeAssistantError("Ampio did not confirm the command") from err
    except AmpioError as err:
        raise HomeAssistantError(str(err)) from err


def remove_empty_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop Ampio devices that no longer have entities, including the old per-object devices."""
    device_reg = dr.async_get(hass)
    registry = er.async_get(hass)
    for device in list(dr.async_entries_for_config_entry(device_reg, entry.entry_id)):
        if er.async_entries_for_device(registry, device.id, include_disabled_entities=True):
            continue
        device_reg.async_remove_device(device.id)


def setup_dynamic_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    *,
    platform: str,
    feature: str,
    source: Callable[[AmpioClient], dict[int, dict[str, Any]]],
    matches: Callable[[dict[str, Any], AmpioClient], bool],
    factory: Callable[[AmpioClient, int], Entity],
) -> None:
    """Reconcile this platform after each complete catalog section."""
    client: AmpioClient = entry.runtime_data
    active: dict[int, Entity] = {}

    async def _remove_entity(entity: Entity) -> None:
        await entity.async_remove(force_remove=True)
        remove_empty_devices(hass, entry)

    def reconcile() -> None:
        if not client.params_ready:
            return
        desired = {item_id for item_id, item in source(client).items() if matches(item, client)}

        def unique_id_for(item_id: int) -> str:
            if feature == "scene":
                return f"{client.gateway_id}:scene:{item_id}"
            return f"{client.gateway_id}:{item_id}:{feature}"

        removed = [item_id for item_id in active if item_id not in desired]
        for item_id in removed:
            hass.async_create_task(_remove_entity(active.pop(item_id)))
        registry = er.async_get(hass)
        expected_ids = {entity.unique_id for entity in active.values()}
        expected_ids.update(unique_id_for(item_id) for item_id in desired)
        for item in er.async_entries_for_config_entry(registry, entry.entry_id):
            if item.domain != platform or item.platform != DOMAIN or item.unique_id in expected_ids:
                continue
            if feature == "scene":
                if not item.unique_id.startswith(f"{client.gateway_id}:scene:"):
                    continue
            elif not item.unique_id.endswith(f":{feature}") or not item.unique_id.startswith(f"{client.gateway_id}:"):
                continue
            registry.async_remove(item.entity_id)
        remove_empty_devices(hass, entry)
        added = desired - active.keys()
        if not added:
            return
        created = [factory(client, item_id) for item_id in sorted(added)]
        async_add_entities(created)
        active.update({entity.ampio_key: entity for entity in created})

    reconcile()
    entry.async_on_unload(client.add_catalog_listener(reconcile))
