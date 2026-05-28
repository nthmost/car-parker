"""Car Parker integration — SF street-sweeping reminder."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CarParkerApiClient, CarParkerApiError
from .const import (
    ATTR_BLOCK,
    ATTR_ENTITY_ID,
    ATTR_LATITUDE,
    ATTR_LIMITS,
    ATTR_LONGITUDE,
    ATTR_SIDE,
    ATTR_STREET,
    ATTR_TEXT,
    CONF_BASE_URL,
    DOMAIN,
    SERVICE_CLEAR,
    SERVICE_CONFIRM_SIDE,
    SERVICE_PARK_HERE,
    SERVICE_PARK_MANUAL,
    SERVICE_PICK_BLOCK,
)
from .coordinator import CarParkerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

PARK_HERE_SCHEMA = vol.Schema(
    vol.Any(
        # either coords directly
        vol.Schema(
            {
                vol.Required(ATTR_LATITUDE): vol.Coerce(float),
                vol.Required(ATTR_LONGITUDE): vol.Coerce(float),
            }
        ),
        # or an entity to read coords from
        vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id}),
    )
)

PICK_BLOCK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_STREET): cv.string,
        vol.Optional(ATTR_LIMITS): cv.string,
    }
)

CONFIRM_SIDE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_SIDE): vol.In(["North", "South", "East", "West"])}
)

PARK_MANUAL_SCHEMA = vol.Schema(
    vol.Any(
        vol.Schema({vol.Required(ATTR_TEXT): cv.string}),
        vol.Schema(
            {
                vol.Required(ATTR_STREET): cv.string,
                vol.Optional(ATTR_BLOCK): cv.string,
                vol.Required(ATTR_SIDE): cv.string,
            }
        ),
    )
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = CarParkerApiClient(session, entry.data[CONF_BASE_URL])
    coordinator = CarParkerCoordinator(hass, client)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            _unregister_services(hass)
    return unload_ok


# ── Services ────────────────────────────────────────────────────────────────

def _any_coordinator(hass: HomeAssistant) -> CarParkerCoordinator | None:
    bucket = hass.data.get(DOMAIN, {})
    return next(iter(bucket.values()), None) if bucket else None


def _resolve_coords(
    hass: HomeAssistant, data: dict[str, Any]
) -> tuple[float, float] | None:
    if ATTR_LATITUDE in data and ATTR_LONGITUDE in data:
        return float(data[ATTR_LATITUDE]), float(data[ATTR_LONGITUDE])

    entity_id = data.get(ATTR_ENTITY_ID)
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        _LOGGER.warning("park_here: entity %s not found", entity_id)
        return None
    lat = state.attributes.get("latitude")
    lng = state.attributes.get("longitude")
    if lat is None or lng is None:
        _LOGGER.warning(
            "park_here: entity %s has no latitude/longitude attributes", entity_id
        )
        return None
    return float(lat), float(lng)


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_PARK_HERE):
        return  # already registered (multiple entries)

    async def _park_here(call: ServiceCall) -> None:
        coord = _any_coordinator(hass)
        if not coord:
            return
        coords = _resolve_coords(hass, dict(call.data))
        if not coords:
            raise vol.Invalid("park_here requires latitude/longitude or entity_id")
        try:
            await coord.client.park_tentative(*coords)
        except CarParkerApiError as err:
            _LOGGER.error("park_here failed: %s", err)
        await coord.async_refresh()

    async def _pick_block(call: ServiceCall) -> None:
        coord = _any_coordinator(hass)
        if not coord:
            return
        try:
            await coord.client.park_pick_block(
                street=call.data[ATTR_STREET],
                limits=call.data.get(ATTR_LIMITS),
            )
        except CarParkerApiError as err:
            _LOGGER.error("pick_block failed: %s", err)
        await coord.async_refresh()

    async def _confirm_side(call: ServiceCall) -> None:
        coord = _any_coordinator(hass)
        if not coord:
            return
        try:
            await coord.client.park_confirm(call.data[ATTR_SIDE])
        except CarParkerApiError as err:
            _LOGGER.error("confirm_side failed: %s", err)
        await coord.async_refresh()

    async def _park_manual(call: ServiceCall) -> None:
        coord = _any_coordinator(hass)
        if not coord:
            return
        data = dict(call.data)
        try:
            if ATTR_TEXT in data:
                await coord.client.park_text(data[ATTR_TEXT])
            else:
                await coord.client.park_structured(
                    street=data[ATTR_STREET],
                    block=data.get(ATTR_BLOCK),
                    side=data[ATTR_SIDE],
                )
        except CarParkerApiError as err:
            _LOGGER.error("park_manual failed: %s", err)
        await coord.async_refresh()

    async def _clear(call: ServiceCall) -> None:
        coord = _any_coordinator(hass)
        if not coord:
            return
        try:
            await coord.client.clear()
        except CarParkerApiError as err:
            _LOGGER.error("clear failed: %s", err)
        await coord.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_PARK_HERE, _park_here, schema=PARK_HERE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PICK_BLOCK, _pick_block, schema=PICK_BLOCK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CONFIRM_SIDE, _confirm_side, schema=CONFIRM_SIDE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PARK_MANUAL, _park_manual, schema=PARK_MANUAL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, _clear)


def _unregister_services(hass: HomeAssistant) -> None:
    for svc in (
        SERVICE_PARK_HERE,
        SERVICE_PICK_BLOCK,
        SERVICE_CONFIRM_SIDE,
        SERVICE_PARK_MANUAL,
        SERVICE_CLEAR,
    ):
        if hass.services.has_service(DOMAIN, svc):
            hass.services.async_remove(DOMAIN, svc)
