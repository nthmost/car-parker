"""Config flow for Car Parker."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CarParkerApiClient, CarParkerApiError
from .const import CONF_BASE_URL, DEFAULT_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str}
)


class CarParkerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            session = async_get_clientsession(self.hass)
            client = CarParkerApiClient(session, base_url)
            try:
                await client.get_status()
            except (CarParkerApiError, aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.warning("Cannot reach car-parker API: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"car_parker:{base_url}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Car Parker",
                    data={CONF_BASE_URL: base_url},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )
