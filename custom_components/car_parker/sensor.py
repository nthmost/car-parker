"""Sensors for Car Parker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CarParkerCoordinator


def _get_status(data: dict) -> str | None:
    return data.get("status")


def _get_urgency(data: dict) -> str | None:
    return data.get("urgency")


def _get_next_sweep(data: dict) -> datetime | None:
    sweep = data.get("next_sweeping") or {}
    iso = sweep.get("start_iso")
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _get_next_sweep_label(data: dict) -> str | None:
    sweep = data.get("next_sweeping") or {}
    return sweep.get("when_label")


def _get_location(data: dict) -> str | None:
    loc = data.get("location")
    if not loc:
        return None
    parts = [loc.get("street")]
    if loc.get("block_limits"):
        parts.append(loc["block_limits"])
    if loc.get("side") and loc["side"] != "Unknown":
        parts.append(f"{loc['side']} side")
    return ", ".join(p for p in parts if p)


def _get_time_limit(data: dict) -> str | None:
    tl = data.get("time_limit")
    if not tl:
        return None
    if tl.get("hrlimit"):
        h = tl["hrlimit"]
        h_str = str(int(h)) if h == int(h) else str(h)
        out = f"{h_str}-hour parking"
        if tl.get("from_time") and tl.get("to_time"):
            out += f" {tl['from_time']}–{tl['to_time']}"
        if tl.get("days"):
            out += f" ({tl['days']})"
        return out
    return tl.get("regulation") or "Parking restriction"


def _status_attrs(data: dict) -> dict[str, Any]:
    # The status sensor carries the whole payload as attributes so the
    # dashboard can pull stage/candidates/sides/etc. from a single place.
    keep = (
        "stage",
        "lat",
        "lng",
        "saved_at",
        "candidates",
        "chosen_block",
        "candidate_sides",
        "time_limit",
        "location",
        "next_sweeping",
    )
    return {k: data[k] for k in keep if k in data}


def _location_attrs(data: dict) -> dict[str, Any]:
    loc = data.get("location") or {}
    return {
        "street": loc.get("street"),
        "block_limits": loc.get("block_limits"),
        "side": loc.get("side"),
        "lat": data.get("lat"),
        "lng": data.get("lng"),
    }


def _next_sweep_attrs(data: dict) -> dict[str, Any]:
    sweep = data.get("next_sweeping") or {}
    return {
        "when_label": sweep.get("when_label"),
        "weekday": sweep.get("weekday"),
        "side": sweep.get("side"),
        "end_iso": sweep.get("end_iso"),
    }


SENSORS: tuple[
    tuple[SensorEntityDescription, Callable[[dict], Any], Callable[[dict], dict] | None],
    ...,
] = (
    (
        SensorEntityDescription(
            key="status",
            name="Car parker status",
            icon="mdi:car-info",
        ),
        _get_status,
        _status_attrs,
    ),
    (
        SensorEntityDescription(
            key="urgency",
            name="Car parker urgency",
            icon="mdi:gauge",
        ),
        _get_urgency,
        None,
    ),
    (
        SensorEntityDescription(
            key="next_sweep",
            name="Next street sweep",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:broom",
        ),
        _get_next_sweep,
        _next_sweep_attrs,
    ),
    (
        SensorEntityDescription(
            key="next_sweep_label",
            name="Next street sweep label",
            icon="mdi:calendar-clock",
        ),
        _get_next_sweep_label,
        None,
    ),
    (
        SensorEntityDescription(
            key="location",
            name="Parked location",
            icon="mdi:map-marker",
        ),
        _get_location,
        _location_attrs,
    ),
    (
        SensorEntityDescription(
            key="time_limit",
            name="Parking time limit",
            icon="mdi:timer-sand",
        ),
        _get_time_limit,
        None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CarParkerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CarParkerSensor(coordinator, entry, desc, fn, attrs_fn)
        for desc, fn, attrs_fn in SENSORS
    )


class CarParkerSensor(CoordinatorEntity[CarParkerCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CarParkerCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        value_fn: Callable[[dict], Any],
        attrs_fn: Callable[[dict], dict] | None,
    ):
        super().__init__(coordinator)
        self.entity_description = description
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self._value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._attrs_fn is None:
            return None
        return self._attrs_fn(self.coordinator.data or {})
