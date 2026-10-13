"""Setup and unload use the config entry, not a module global."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.ampio.const import DOMAIN
from custom_components.ampio.protocol import AmpioAuthError, AmpioError

from .test_config_flow import USER_INPUT


async def _create_entry(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    return result["result"].entry_id


async def test_setup_and_unload(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A loaded entry connects once and disconnects on unload."""
    entry_id = await _create_entry(hass)
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry is not None
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is ampio_client

    assert await hass.config_entries.async_unload(entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    ampio_client.disconnect.assert_awaited()


async def test_auth_failure_during_setup_is_a_reauth(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A password rejected at startup does not retry forever."""
    entry_id = await _create_entry(hass)
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry is not None
    await hass.config_entries.async_unload(entry_id)
    ampio_client.connect.side_effect = AmpioAuthError("rejected")

    assert await hass.config_entries.async_setup(entry_id) is False
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_connection_failure_during_setup_retries(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A broker that is down leaves the entry ready to try again."""
    entry_id = await _create_entry(hass)
    entry = hass.config_entries.async_get_entry(entry_id)
    assert entry is not None
    await hass.config_entries.async_unload(entry_id)
    ampio_client.connect.side_effect = AmpioError("down")

    assert await hass.config_entries.async_setup(entry_id) is False
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.data[CONF_PASSWORD] == "secret"
