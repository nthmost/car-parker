"""Config flow for Car Parker."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant import config_entries

from . import downloader
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CarParkerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
