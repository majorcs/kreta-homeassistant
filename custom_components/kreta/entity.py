"""Shared entity base for Kreta platforms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KretaRuntimeData
from .const import DOMAIN


class KretaEntity(CoordinatorEntity):
    """Base entity providing the shared Kreta device_info block."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the entity and store the owning config entry."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry

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
