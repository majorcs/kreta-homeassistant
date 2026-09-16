"""Sensor platform for Kreta."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KretaRuntimeData
from .const import (
    ATTR_COMPACT_EVENTS_JSON,
    ATTR_EVENTS,
    ATTR_EVENTS_JSON,
    ATTR_GRADES_JSON,
    ATTR_HOMEWORK_JSON,
    ATTR_LAST_ERROR,
    ATTR_LAST_ERROR_TIME,
    ATTR_LAST_SUCCESS,
    ATTR_PROFILE,
    ATTR_RANGE_END,
    ATTR_RANGE_START,
    ATTR_SCHOOL_YEAR_JSON,
    DOMAIN,
)
from .entity import KretaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kreta sensor entities."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        KretaJsonSensor(entry, runtime_data),
        KretaCompactJsonSensor(entry, runtime_data),
        KretaLastRefreshSensor(entry, runtime_data),
        KretaUpdateStatusSensor(entry, runtime_data),
        KretaGradesJsonSensor(entry, runtime_data),
        KretaNewGradesSensor(entry, runtime_data),
        KretaHomeworkJsonSensor(entry, runtime_data),
        KretaUpcomingHomeworkSensor(entry, runtime_data),
        KretaSchoolYearJsonSensor(entry, runtime_data),
        KretaNextSchoolEventSensor(entry, runtime_data),
    ])


class KretaJsonSensor(KretaEntity, SensorEntity):
    """A sensor exposing Kreta data for machine processing.

    Disabled by default to avoid enabling it for users who don't need it.
    Large attributes (profile, events list, full JSON payload) are excluded
    from the recorder via _unrecorded_attributes so they are available at
    runtime for automations and templates without hitting the 16 KB storage
    limit.
    """

    _attr_icon = "mdi:code-json"
    _attr_entity_registry_enabled_default = False
    _unrecorded_attributes = frozenset({ATTR_EVENTS_JSON, ATTR_EVENTS, ATTR_PROFILE})

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_json"
        self._attr_name = "Timetable JSON"

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


class KretaCompactJsonSensor(KretaEntity, SensorEntity):
    """A sensor exposing a compact daily Kreta timetable for space-constrained consumers.

    Enabled by default because the payload (~4 KB) is small enough to avoid HA
    recorder issues.  The format groups lessons by date and strips verbose fields
    to keep the payload lean (e.g. for ESP32-based displays).
    """

    _attr_icon = "mdi:code-json"
    _attr_native_unit_of_measurement = "days"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_compact_json"
        self._attr_name = "Compact Timetable JSON"

    @property
    def native_value(self) -> int | None:
        """Return the number of school days covered by the compact payload."""
        if self.coordinator.data is None:
            return None
        return len({event.start.date() for event in self.coordinator.data.events})

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the compact timetable payload."""
        if self.coordinator.data is None:
            return {}
        return {
            ATTR_COMPACT_EVENTS_JSON: self.coordinator.data.compact_payload_json,
        }


class KretaLastRefreshSensor(KretaEntity, SensorEntity):
    """A sensor reporting the last successful refresh timestamp."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_last_refresh"
        self._attr_name = "Last Refresh"

    @property
    def native_value(self) -> datetime | None:
        """Return the last successful refresh as a datetime."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.last_success


class KretaUpdateStatusSensor(KretaEntity, SensorEntity):
    """A sensor reporting the status of the last data update."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "error"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:sync-alert"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_update_status"
        self._attr_name = "Update Status"

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


class KretaGradesJsonSensor(KretaEntity, SensorEntity):
    """A sensor exposing recorded grades for machine processing.

    Disabled by default, matching the existing Timetable JSON sensor pattern.
    """

    _attr_icon = "mdi:school"
    _attr_entity_registry_enabled_default = False
    _unrecorded_attributes = frozenset({ATTR_GRADES_JSON})

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_grades_json"
        self._attr_name = "Grades JSON"

    @property
    def native_value(self) -> int | None:
        """Return the number of grades in the fetched window."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.grades)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the structured grades payload."""
        if self.coordinator.data is None:
            return {}
        return {ATTR_GRADES_JSON: self.coordinator.data.grades_json}


class KretaNewGradesSensor(KretaEntity, SensorEntity):
    """A sensor reporting the number of grades in the fetched window."""

    _attr_icon = "mdi:school"
    _attr_native_unit_of_measurement = "grades"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_new_grades"
        self._attr_name = "New Grades"

    @property
    def native_value(self) -> int | None:
        """Return the number of grades in the fetched window."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.grades)


class KretaHomeworkJsonSensor(KretaEntity, SensorEntity):
    """A sensor exposing homework for machine processing.

    Disabled by default, matching the existing Timetable JSON sensor pattern.
    """

    _attr_icon = "mdi:notebook-edit"
    _attr_entity_registry_enabled_default = False
    _unrecorded_attributes = frozenset({ATTR_HOMEWORK_JSON})

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_homework_json"
        self._attr_name = "Homework JSON"

    @property
    def native_value(self) -> int | None:
        """Return the number of homework items in the fetched window."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.homework)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the structured homework payload."""
        if self.coordinator.data is None:
            return {}
        return {ATTR_HOMEWORK_JSON: self.coordinator.data.homework_json}


class KretaUpcomingHomeworkSensor(KretaEntity, SensorEntity):
    """A sensor reporting the number of homework items in the fetched window."""

    _attr_icon = "mdi:notebook-edit"
    _attr_native_unit_of_measurement = "items"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_upcoming_homework"
        self._attr_name = "Upcoming Homework"

    @property
    def native_value(self) -> int | None:
        """Return the number of homework items in the fetched window."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.homework)


class KretaSchoolYearJsonSensor(KretaEntity, SensorEntity):
    """A sensor exposing the whole school-year calendar for machine processing.

    Disabled by default, matching the existing Timetable JSON sensor pattern.
    """

    _attr_icon = "mdi:calendar-star"
    _attr_entity_registry_enabled_default = False
    _unrecorded_attributes = frozenset({ATTR_SCHOOL_YEAR_JSON})

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_school_year_json"
        self._attr_name = "School Year Calendar JSON"

    @property
    def native_value(self) -> int | None:
        """Return the number of school-year calendar entries."""
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data.school_year_calendar)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the structured school-year calendar payload."""
        if self.coordinator.data is None:
            return {}
        return {ATTR_SCHOOL_YEAR_JSON: self.coordinator.data.school_year_json}


class KretaNextSchoolEventSensor(KretaEntity, SensorEntity):
    """A sensor reporting the next upcoming school-year calendar entry."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-star"

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_next_school_event"
        self._attr_name = "Next School Year Event"

    def _next_milestone(self):
        """Return the earliest school-year calendar entry on or after today."""
        if self.coordinator.data is None:
            return None
        today = dt_util.now().date()
        upcoming = [
            milestone
            for milestone in self.coordinator.data.school_year_calendar
            if milestone.event_date >= today
        ]
        return upcoming[0] if upcoming else None

    @property
    def native_value(self) -> date | None:
        """Return the date of the next school-year calendar entry."""
        milestone = self._next_milestone()
        return milestone.event_date if milestone else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the type code and description of the next school-year calendar entry."""
        milestone = self._next_milestone()
        if milestone is None:
            return {}
        return {"day_type": milestone.day_type, "description": milestone.description}
