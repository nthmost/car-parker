"""Binary sensors for Car Parker."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LOCATION_MISMATCH_THRESHOLD_M,
    STALE_TRACKER_THRESHOLD_MIN,
    STATUS_PARKED,
    STATUS_PENDING,
    URGENCY_NOW,
    URGENCY_URGENT,
)
from .coordinator import CarParkerCoordinator


def _is_parked(data: dict) -> bool:
    return data.get("status") == STATUS_PARKED


def _needs_side(data: dict) -> bool:
    return data.get("status") == STATUS_PENDING


def _move_car_now(data: dict) -> bool:
    return data.get("urgency") in (URGENCY_URGENT, URGENCY_NOW)


def _away_from_parked_spot(data: dict) -> bool:
    distance = (data.get("car_tracker") or {}).get("distance_from_parked_m")
    return distance is not None and distance > LOCATION_MISMATCH_THRESHOLD_M


def _tracker_stale(data: dict) -> bool:
    age_min = (data.get("car_tracker") or {}).get("age_min")
    return age_min is not None and age_min > STALE_TRACKER_THRESHOLD_MIN


SENSORS: tuple[tuple[BinarySensorEntityDescription, Callable[[dict], bool]], ...] = (
    (
        BinarySensorEntityDescription(
            key="parked",
            name="Car parked",
            icon="mdi:car",
        ),
        _is_parked,
    ),
    (
        BinarySensorEntityDescription(
            key="needs_side_confirmation",
            name="Car parker needs side confirmation",
            icon="mdi:help-circle-outline",
        ),
        _needs_side,
    ),
    (
        BinarySensorEntityDescription(
            key="move_car_now",
            name="Move car now",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon="mdi:alert",
        ),
        _move_car_now,
    ),
    (
        BinarySensorEntityDescription(
            key="car_away_from_parked_spot",
            name="Car away from parked spot",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon="mdi:map-marker-alert",
        ),
        _away_from_parked_spot,
    ),
    (
        BinarySensorEntityDescription(
            key="car_tracker_stale",
            name="Car tracker stale",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon="mdi:map-marker-off",
        ),
        _tracker_stale,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarParkerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CarParkerBinarySensor(coordinator, entry, desc, fn) for desc, fn in SENSORS
    )


class CarParkerBinarySensor(CoordinatorEntity[CarParkerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CarParkerCoordinator,
        entry: ConfigEntry,
        description: BinarySensorEntityDescription,
        is_on_fn: Callable[[dict], bool],
    ):
        super().__init__(coordinator)
        self.entity_description = description
        self._is_on_fn = is_on_fn
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        return self._is_on_fn(self.coordinator.data or {})
