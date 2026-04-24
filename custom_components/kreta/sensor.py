"""Sensor platform for Kreta."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KretaRuntimeData
from .const import (
    ATTR_EVENTS,
    ATTR_EVENTS_JSON,
    ATTR_LAST_SUCCESS,
    ATTR_PROFILE,
    ATTR_RANGE_END,
    ATTR_RANGE_START,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kreta sensor entities."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KretaJsonSensor(entry, runtime_data)])


class KretaJsonSensor(CoordinatorEntity, SensorEntity):
    """A sensor exposing Kreta data for machine processing."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:code-json"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry
        self._runtime_data = runtime_data
        self._attr_unique_id = f"{entry.entry_id}_json"
        self._attr_name = "Timetable JSON"

    @property
    def device_info(self) -> DeviceInfo:
        """Return shared device info."""
        profile = self.coordinator.data.profile if self.coordinator.data else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer="Unofficial Kreta Integration",
            model="Pupil account",
            name=profile.student_name if profile and profile.student_name else self._entry.title,
            suggested_area="Education",
        )

    @property
    def native_value(self) -> str | None:
        """Return a stable short state value.

        Home Assistant state values are length-limited, so the full JSON payload
        is exposed in attributes while the state tracks the last refresh time.
        """
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.last_success.isoformat()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the structured timetable payload."""
        if self.coordinator.data is None:
            return {}
        return {
            ATTR_PROFILE: self.coordinator.data.profile.as_dict(),
            ATTR_EVENTS: [event.as_dict() for event in self.coordinator.data.events],
            ATTR_EVENTS_JSON: self.coordinator.data.payload_json,
            ATTR_RANGE_START: self.coordinator.data.range_start.isoformat(),
            ATTR_RANGE_END: self.coordinator.data.range_end.isoformat(),
            ATTR_LAST_SUCCESS: self.coordinator.data.last_success.isoformat(),
            "lessons_count": self.coordinator.data.lessons_count,
            "tests_count": self.coordinator.data.tests_count,
        }
