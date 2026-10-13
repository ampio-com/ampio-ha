"""UI configuration for Ampio."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import CONF_PORT, CONF_WEBSOCKET, DOMAIN
from .protocol import AmpioAuthError, AmpioClient, AmpioCompatibilityError, AmpioError


async def validate_input(hass: HomeAssistant, data: dict) -> str:
    """Verify credentials and return the immutable gateway identifier."""
    client = AmpioClient(
        data[CONF_HOST], data[CONF_PORT], data[CONF_USERNAME], data[CONF_PASSWORD],
        websocket=data[CONF_WEBSOCKET],
    )
    try:
        await client.connect()
        if client.gateway_id is None:
            raise AmpioCompatibilityError("Ampio server has no stable device_id")
        return client.gateway_id
    finally:
        await client.disconnect()


class AmpioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ampio."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        """Ask for the local gateway and Ampio account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                gateway_id = await validate_input(self.hass, user_input)
            except AmpioAuthError:
                errors["base"] = "invalid_auth"
            except AmpioCompatibilityError:
                errors["base"] = "unsupported_server"
            except (AmpioError, OSError, TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(gateway_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Ampio", data=user_input)

        return self.async_show_form(step_id="user", data_schema=self._connection_schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data: dict) -> config_entries.ConfigFlowResult:
        """Start a password refresh after Ampio rejects the saved credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        """Ask for the current password of the existing Ampio account."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            errors = await self._validate_same_gateway(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")),
            }),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )

    async def async_step_reconfigure(self, user_input: dict | None = None) -> config_entries.ConfigFlowResult:
        """Update the local address without creating a second gateway entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            errors = await self._validate_same_gateway(data)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT], CONF_WEBSOCKET: data[CONF_WEBSOCKET]},
                )
        suggested = user_input or {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: entry.data[CONF_PORT],
            CONF_WEBSOCKET: entry.data[CONF_WEBSOCKET],
        }
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=suggested[CONF_HOST]): str,
            vol.Required(CONF_PORT, default=suggested[CONF_PORT]): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_WEBSOCKET, default=suggested[CONF_WEBSOCKET]): bool,
        })
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def _validate_same_gateway(self, data: dict) -> dict[str, str]:
        """Return form errors, or an empty dict when the same gateway accepted the data."""
        try:
            gateway_id = await validate_input(self.hass, data)
        except AmpioAuthError:
            return {"base": "invalid_auth"}
        except AmpioCompatibilityError:
            return {"base": "unsupported_server"}
        except (AmpioError, OSError, TimeoutError, ValueError):
            return {"base": "cannot_connect"}
        await self.async_set_unique_id(gateway_id)
        self._abort_if_unique_id_mismatch(reason="wrong_gateway")
        return {}

    def _connection_schema(self, user_input: dict | None) -> vol.Schema:
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "") if user_input else ""): str,
            vol.Required(CONF_PORT, default=user_input.get(CONF_PORT, 1883) if user_input else 1883): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_WEBSOCKET, default=user_input.get(CONF_WEBSOCKET, False) if user_input else False): bool,
            vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "") if user_input else ""): str,
            vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")),
        })
        return schema
