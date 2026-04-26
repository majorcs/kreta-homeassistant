"""The Kreta integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api.client import KretaApiClient
from .api.storage import KretaTokenStore
from .const import DOMAIN, PLATFORMS
from .coordinator import KretaDataUpdateCoordinator

type KretaConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KretaRuntimeData:
    """Runtime data for a config entry."""

    client: KretaApiClient
    coordinator: KretaDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the Kreta integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> bool:
    """Set up Kreta from a config entry."""
    _LOGGER.info(
        "Setting up Kreta entry for %s / %s",
        entry.data["klik_id"],
        entry.data["user_id"],
    )
    session = async_get_clientsession(hass)
    token_store = KretaTokenStore(hass, entry.entry_id)
    client = KretaApiClient(
        session=session,
        klik_id=entry.data["klik_id"],
        user_id=entry.data["user_id"],
        password=entry.data["password"],
        token_store=token_store,
    )
    coordinator = KretaDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    if coordinator.data is not None and coordinator.data.profile.student_name:
        expected_title = (
            f"{coordinator.data.profile.student_name} ({entry.data['klik_id']})"
        )
        if entry.title != expected_title:
            hass.config_entries.async_update_entry(entry, title=expected_title)

    _LOGGER.info(
        "Kreta entry ready for %s (%s)",
        coordinator.data.profile.student_name if coordinator.data else "unknown",
        entry.data["klik_id"],
    )

    hass.data[DOMAIN][entry.entry_id] = KretaRuntimeData(
        client=client,
        coordinator=coordinator,
    )

    async def _midnight_refresh(_now: datetime) -> None:
        """Trigger a coordinator refresh after midnight to capture the new day's data."""
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(hass, _midnight_refresh, hour=0, minute=0, second=30)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_disable_json_sensor_for_existing_install(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


def _async_disable_json_sensor_for_existing_install(
    hass: HomeAssistant, entry: KretaConfigEntry
) -> None:
    """Disable the JSON sensor in the entity registry if it was previously enabled by default.

    Introduced in 2026.04.26.2: the JSON sensor is disabled by default
    (_attr_entity_registry_enabled_default = False) to prevent recorder
    warnings caused by the large attribute payload.  For installations that
    pre-date this change the entity is already in the entity registry as
    enabled; this one-time migration disables it via the INTEGRATION disabler
    so the recorder stops trying to store it.
    Users who intentionally want the entity can re-enable it through the HA UI
    (that sets disabled_by to USER, which this code does not touch).
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_json")
    if entity_id is None:
        return
    reg_entry = registry.async_get(entity_id)
    if reg_entry is None or reg_entry.disabled_by is not None:
        # Already disabled (by any source) — leave it alone.
        return
    _LOGGER.debug(
        "Disabling JSON sensor %s to prevent recorder attribute-size warnings",
        entity_id,
    )
    registry.async_update_entity(
        entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
    )


async def async_unload_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Kreta entry for %s", entry.data.get("klik_id", entry.entry_id))
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
