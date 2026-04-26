"""Sensor platform for Kreta."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KretaRuntimeData
from .const import (
    ATTR_EVENTS,
    ATTR_EVENTS_JSON,
    ATTR_LAST_ERROR,
    ATTR_LAST_ERROR_TIME,
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
    async_add_entities([
        KretaJsonSensor(entry, runtime_data),
        KretaLastRefreshSensor(entry, runtime_data),
        KretaUpdateStatusSensor(entry, runtime_data),
    ])


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


class KretaLastRefreshSensor(CoordinatorEntity, SensorEntity):
    """A sensor reporting the last successful refresh timestamp."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_last_refresh"
        self._attr_name = "Last Refresh"

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
    def native_value(self) -> datetime | None:
        """Return the last successful refresh as a datetime."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.last_success


class KretaUpdateStatusSensor(CoordinatorEntity, SensorEntity):
    """A sensor reporting the status of the last data update."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "error"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:sync-alert"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update_status"
        self._attr_name = "Update Status"

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
    def native_value(self) -> str:
        """Return 'ok' or 'error' based on last update outcome."""
        return "ok" if self.coordinator.last_update_success else "error"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details about the last update attempt."""
        attrs: dict[str, Any] = {}
        if self.coordinator.data is not None:
            attrs[ATTR_LAST_SUCCESS] = self.coordinator.data.last_success.isoformat()
            attrs[ATTR_RANGE_START] = self.coordinator.data.range_start.isoformat()
            attrs[ATTR_RANGE_END] = self.coordinator.data.range_end.isoformat()
            attrs["lessons_count"] = self.coordinator.data.lessons_count
            attrs["tests_count"] = self.coordinator.data.tests_count
        if self.coordinator.last_error_message is not None:
            attrs[ATTR_LAST_ERROR] = self.coordinator.last_error_message
        if self.coordinator.last_error_time is not None:
            attrs[ATTR_LAST_ERROR_TIME] = self.coordinator.last_error_time.isoformat()
        return attrs
