"""Calendar platform for Kreta."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import KretaRuntimeData
from .api.models import MergedCalendarEvent
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kreta calendar entities from a config entry."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KretaCalendarEntity(entry, runtime_data)])


class KretaCalendarEntity(CoordinatorEntity, CalendarEntity):
    """Representation of Kreta events as a calendar."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the calendar entity."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry
        self._runtime_data = runtime_data
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_name = "Timetable"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the pupil/account."""
        profile = self.coordinator.data.profile if self.coordinator.data else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer="Unofficial Kreta Integration",
            model="Pupil account",
            name=profile.student_name if profile and profile.student_name else self._entry.title,
            suggested_area="Education",
            configuration_url="https://github.com/major/kreta-homeassistant",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        if self.coordinator.data is None:
            return None

        now = dt_util.now()
        active_event: MergedCalendarEvent | None = None
        next_event: MergedCalendarEvent | None = None

        for event in self.coordinator.data.events:
            if event.start <= now <= event.end:
                active_event = event
                break
            if event.start >= now:
                next_event = event
                break

        selected = active_event or next_event
        if selected is None:
            return None
        return selected.as_calendar_event()

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events in the configured range."""
        del hass
        if self.coordinator.data is None:
            return []
        return [
            event.as_calendar_event()
            for event in self.coordinator.data.events
            if event.end > start_date and event.start < end_date
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "student": self.coordinator.data.profile.as_dict(),
            "lessons_count": self.coordinator.data.lessons_count,
            "tests_count": self.coordinator.data.tests_count,
            "range_start": self.coordinator.data.range_start.isoformat(),
            "range_end": self.coordinator.data.range_end.isoformat(),
        }
