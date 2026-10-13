"""Config flow coverage for the paths a user can actually hit."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ampio.const import CONF_PORT, CONF_WEBSOCKET, DOMAIN
from custom_components.ampio.protocol import AmpioAuthError, AmpioCompatibilityError, AmpioError

USER_INPUT = {
    CONF_HOST: "192.168.1.10",
    CONF_PORT: 1883,
    CONF_WEBSOCKET: False,
    CONF_USERNAME: "anna",
    CONF_PASSWORD: "secret",
}


async def test_user_creates_one_entry_per_gateway(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A successful login creates the entry, and the same gateway cannot be added twice."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ampio"
    assert result["result"].unique_id == "gateway-1"
    ampio_client.connect.assert_awaited()
    ampio_client.disconnect.assert_awaited()

    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    again = await hass.config_entries.flow.async_configure(again["flow_id"], USER_INPUT)
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "already_configured"


async def test_failed_login_returns_to_the_form(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A rejected password, an old server and a dead broker keep the form open for a retry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    ampio_client.connect.side_effect = AmpioAuthError("rejected")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    ampio_client.connect.side_effect = AmpioCompatibilityError("old")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "unsupported_server"}

    ampio_client.connect.side_effect = AmpioError("down")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}

    ampio_client.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_invalid_username_cannot_connect(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A username that cannot be an MQTT topic segment is rejected before connect."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_USERNAME: "an/na"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    ampio_client.connect.assert_not_awaited()


async def test_reauth_updates_the_password(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """Reauth checks the same gateway and stores the new password."""
    created = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    created = await hass.config_entries.flow.async_configure(created["flow_id"], USER_INPUT)
    entry = created["result"]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    ampio_client.gateway_id = "other-gateway"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new-secret"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_gateway"

    ampio_client.gateway_id = "gateway-1"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new-secret"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-secret"


async def test_reconfigure_keeps_the_same_gateway(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """A new address is accepted only when the server reports the same gateway id."""
    created = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    created = await hass.config_entries.flow.async_configure(created["flow_id"], USER_INPUT)
    entry = created["result"]

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.20", CONF_PORT: 9001, CONF_WEBSOCKET: True}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.1.20"
    assert entry.data[CONF_PORT] == 9001
    assert entry.data[CONF_WEBSOCKET] is True
