"""The Kreta integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


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
