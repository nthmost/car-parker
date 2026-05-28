"""DataUpdateCoordinator that polls /api/status."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarParkerApiClient, CarParkerApiError
from .const import DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CarParkerCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, client: CarParkerApiClient):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.get_status()
        except CarParkerApiError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001 — surface as UpdateFailed
            raise UpdateFailed(f"Unexpected: {err}") from err
