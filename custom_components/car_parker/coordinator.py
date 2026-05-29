"""Local DataUpdateCoordinator — loads SFMTA data in-process."""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_POLL_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from .parking import ParkingManager
    from .parking_geo import TimeLimitLookup, SweepingGeoLookup

_LOGGER = logging.getLogger(__name__)


class CarParkerCoordinator(DataUpdateCoordinator[dict]):
    manager: ParkingManager
    tl_lookup: TimeLimitLookup
    geo_lookup: SweepingGeoLookup

    def __init__(self, hass: HomeAssistant, data_dir: Path) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self._data_dir = data_dir

    async def async_setup(self) -> None:
        """Load data files into memory (blocking I/O — runs in executor)."""
        def _load():
            from .parking import StreetSweepingLookup, ParkingManager
            from .parking_geo import TimeLimitLookup, SweepingGeoLookup
            lookup = StreetSweepingLookup(self._data_dir / "street_sweeping_sf.json")
            manager = ParkingManager(lookup, self._data_dir / "parking_state.json")
            tl = TimeLimitLookup(self._data_dir / "parking_regulations_sf.geojson")
            geo = SweepingGeoLookup(self._data_dir / "street_sweeping_sf.json")
            return manager, tl, geo

        try:
            self.manager, self.tl_lookup, self.geo_lookup = (
                await self.hass.async_add_executor_job(_load)
            )
        except FileNotFoundError as err:
            raise ConfigEntryNotReady(f"SFMTA data files missing: {err}") from err

    async def reload(self) -> None:
        """Reload data files after a sync_data call."""
        await self.async_setup()

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self.manager.get_status)
        except Exception as err:
            raise UpdateFailed(f"Unexpected: {err}") from err
