"""Home Assistant harness for the Ampio custom component."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ampio instead of a core integration."""
    return


@pytest.fixture
def ampio_client() -> Generator[MagicMock]:
    """One fake gateway client for the config flow and for entry setup."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.async_confirm = AsyncMock()
    client.gateway_id = "gateway-1"
    client.available = True
    client.states_ready = True
    client.params_ready = True
    client.catalog = {}
    client.params = {}
    client.hardware = {}
    client.scenes = {}
    client.conditions = {}
    client.irrigations = {}
    client.states = {}
    client.add_listener = MagicMock(return_value=lambda: None)
    client.add_catalog_listener = MagicMock(return_value=lambda: None)
    client.add_auth_listener = MagicMock(return_value=lambda: None)

    def build(*args: object, **_kwargs: object) -> MagicMock:
        username = args[2] if len(args) > 2 else ""
        if isinstance(username, str) and any(character in username for character in "/+#"):
            raise ValueError("Invalid Ampio username for MQTT topics")
        return client

    with (
        patch("custom_components.ampio.config_flow.AmpioClient", side_effect=build),
        patch("custom_components.ampio.AmpioClient", side_effect=build),
    ):
        yield client
