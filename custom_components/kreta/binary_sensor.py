"""Binary sensor platform for Kreta."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Kreta binary sensors."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            KretaDayBinarySensor(entry, runtime_data, "school_day", "Is School Day"),
            KretaDayBinarySensor(
                entry,
                runtime_data,
                "school_day_tomorrow",
                "Is School Day Tomorrow",
                day_offset=1,
            ),
            KretaDayBinarySensor(
                entry,
                runtime_data,
                "exam_day",
                "Is Exam Day",
                event_kind="exam",
            ),
            KretaDayBinarySensor(
                entry,
                runtime_data,
                "exam_day_tomorrow",
                "Is Exam Day Tomorrow",
                day_offset=1,
                event_kind="exam",
            ),
        ]
    )


class KretaDayBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor derived from timetable and exam events."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        runtime_data: KretaRuntimeData,
        key: str,
        name: str,
        *,
        day_offset: int = 0,
        event_kind: str = "lesson",
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._day_offset = day_offset
        self._event_kind = event_kind
        self._attr_icon = "mdi:school" if event_kind == "lesson" else "mdi:clipboard-text"

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
    def is_on(self) -> bool | None:
        """Return whether the target condition is true for the selected day."""
        if self.coordinator.data is None:
            return None

        target_date = dt_util.now().date() + timedelta(days=self._day_offset)
        return any(
            self._event_matches(event, target_date) for event in self.coordinator.data.events
        )

    def _event_matches(self, event: MergedCalendarEvent, target_date: date) -> bool:
        """Return whether an event contributes to the sensor state."""
        if self._event_kind == "lesson":
            return event.source != "exam_only" and event.start.date() == target_date

        return event.exam is not None and event.exam.test_date == target_date
