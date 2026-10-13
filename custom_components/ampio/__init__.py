"""Home Assistant integration for local Ampio servers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady

from .const import CONF_PORT, CONF_WEBSOCKET, PLATFORMS
from .entity import remove_empty_devices
from .protocol import AmpioAuthError, AmpioClient, AmpioCompatibilityError, AmpioError


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Connect to Ampio and set up entities."""
    client = AmpioClient(
        entry.data["host"],
        entry.data[CONF_PORT],
        entry.data["username"],
        entry.data["password"],
        websocket=entry.data[CONF_WEBSOCKET],
    )
    try:
        await client.connect()
    except AmpioAuthError as err:
        raise ConfigEntryAuthFailed("Ampio rejected the configured credentials") from err
    except AmpioCompatibilityError as err:
        raise ConfigEntryError(str(err)) from err
    except (AmpioError, OSError, TimeoutError) as err:
        raise ConfigEntryNotReady("Cannot connect to Ampio") from err
    entry.runtime_data = client
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        remove_empty_devices(hass, entry)
    except Exception:
        await client.disconnect()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop platforms and close the MQTT connection."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.disconnect()
    return True
