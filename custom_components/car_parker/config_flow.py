"""Config flow for Car Parker."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import downloader
from .const import (
    CONF_CAR_TRACKER,
    CONF_SOON_DAYS,
    CONF_URGENT_HOURS,
    DEFAULT_SOON_DAYS,
    DEFAULT_URGENT_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CarParkerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CarParkerOptionsFlow:
        return CarParkerOptionsFlow()

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        data_dir = Path(self.hass.config.config_dir) / "car_parker"
        sweep_file = data_dir / "street_sweeping_sf.json"
        errors: dict[str, str] = {}

        if user_input is not None:
            if not sweep_file.exists():
                try:
                    await downloader.download_all(self.hass, data_dir)
                except Exception as err:
                    _LOGGER.error("SFMTA data download failed: %s", err)
                    errors["base"] = "download_failed"

            if not errors:
                await self.async_set_unique_id("car_parker_sf")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Car Parker", data={})

        have_data = sweep_file.exists()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "data_status": (
                    "SFMTA data already present — no download needed."
                    if have_data
                    else "~35 MB of SFMTA street sweeping data will be downloaded from DataSF."
                )
            },
        )


class CarParkerOptionsFlow(config_entries.OptionsFlow):
    """Let the user tune the urgency thresholds from the HA UI."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema: dict = {
            vol.Required(
                CONF_URGENT_HOURS,
                default=options.get(CONF_URGENT_HOURS, DEFAULT_URGENT_HOURS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=48,
                    step=0.5,
                    unit_of_measurement="hours",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SOON_DAYS,
                default=options.get(CONF_SOON_DAYS, DEFAULT_SOON_DAYS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=7,
                    step=1,
                    unit_of_measurement="days",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            # Optional: a device_tracker for the car's own GPS. Leave empty if
            # you don't have one — the car-location features stay hidden.
            vol.Optional(
                CONF_CAR_TRACKER,
                description={"suggested_value": options.get(CONF_CAR_TRACKER)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="device_tracker")
            ),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
