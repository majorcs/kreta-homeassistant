"""Button platform for Kreta."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KretaRuntimeData
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kreta button entities."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KretaRefreshButton(entry, runtime_data)])


class KretaRefreshButton(CoordinatorEntity, ButtonEntity):
    """A button that triggers an immediate data refresh."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:refresh"
    _attr_name = "Refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the button."""
        super().__init__(runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_refresh"

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

    async def async_press(self) -> None:
        """Trigger an immediate coordinator refresh."""
        await self.coordinator.async_request_refresh()
