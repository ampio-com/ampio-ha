"""A stable relay is a switch and waits for the reported state."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.ampio.const import DOMAIN

from .test_config_flow import USER_INPUT

RELAY = {
    "id": 1,
    "typ_komponentu": "przekaznik",
    "funkcja": "1",
    "interpretacja": "1",
    "min": 0,
    "max": 1,
    "opis_menu": "Lampa",
}


async def test_switch_turn_on_sends_the_relay_command(hass: HomeAssistant, ampio_client: MagicMock) -> None:
    """Turning the switch on publishes the on value and does not assume success."""
    ampio_client.catalog[1] = RELAY
    ampio_client.states[1] = {"state": "0"}
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    entity_id = er.async_get(hass).async_get_entity_id(SWITCH_DOMAIN, DOMAIN, "gateway-1:1:switch")
    assert entity_id is not None
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True)
    ampio_client.async_confirm.assert_awaited()
    path = ampio_client.async_confirm.await_args.args[0]
    assert path == "/api/set/1/setValue/1"

    ampio_client.states[1] = {"state": "1"}
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True)
    assert ampio_client.async_confirm.await_args.args[0] == "/api/set/1/setValue/0"
