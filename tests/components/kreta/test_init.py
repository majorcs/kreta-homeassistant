"""Tests for Kreta setup."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kreta import async_reload_entry, _async_disable_json_sensor_for_existing_install
from custom_components.kreta.const import (
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DOMAIN,
)


TZ = ZoneInfo("Europe/Budapest")


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Config entry setup should initialize coordinator and forward platforms."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Student One (school01)",
        data={
            CONF_KLIK_ID: "school01",
            CONF_USER_ID: "student01",
            CONF_PASSWORD: "secret",
            CONF_REFRESH_HOURS: 12,
            CONF_LOOKAHEAD_WEEKS: 2,
        },
    )
    entry.add_to_hass(hass)

    async def _first_refresh(self) -> None:
        self.data = SimpleNamespace(
            profile=SimpleNamespace(student_name="Student One")
        )

    with patch(
        "custom_components.kreta.async_get_clientsession",
        return_value=object(),
    ), patch(
        "custom_components.kreta.coordinator.KretaDataUpdateCoordinator.async_config_entry_first_refresh",
        new=_first_refresh,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_update_entry",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)


async def test_midnight_refresh_callback_triggers_coordinator(hass: HomeAssistant) -> None:
    """Midnight time-change callback should call coordinator.async_request_refresh."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Student One (school01)",
        data={
            CONF_KLIK_ID: "school01",
            CONF_USER_ID: "student01",
            CONF_PASSWORD: "secret",
            CONF_REFRESH_HOURS: 12,
            CONF_LOOKAHEAD_WEEKS: 2,
        },
    )
    entry.add_to_hass(hass)

    async def _first_refresh(self) -> None:
        self.data = SimpleNamespace(
            profile=SimpleNamespace(student_name="Student One")
        )

    captured_callbacks: list = []

    def _capture_time_change(hass_arg, callback, **kwargs):
        captured_callbacks.append(callback)
        return lambda: None  # unsubscribe no-op

    with patch(
        "custom_components.kreta.async_get_clientsession",
        return_value=object(),
    ), patch(
        "custom_components.kreta.coordinator.KretaDataUpdateCoordinator.async_config_entry_first_refresh",
        new=_first_refresh,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_update_entry",
        new=AsyncMock(return_value=None),
    ), patch(
        "custom_components.kreta.async_track_time_change",
        side_effect=_capture_time_change,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert len(captured_callbacks) == 1
    runtime = hass.data[DOMAIN][entry.entry_id]
    runtime.coordinator.async_request_refresh = AsyncMock()

    await captured_callbacks[0](datetime(2026, 4, 28, 0, 0, 30, tzinfo=TZ))

    runtime.coordinator.async_request_refresh.assert_awaited_once()


async def test_reload_entry(hass: HomeAssistant) -> None:
    """Reload helper should delegate to Home Assistant."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new=AsyncMock(return_value=True),
    ) as reload_mock:
        await async_reload_entry(hass, entry)

    reload_mock.assert_awaited_once_with(entry.entry_id)


async def test_disable_json_sensor_migration_disables_enabled_entity(hass: HomeAssistant) -> None:
    """One-time migration should disable JSON sensor that was previously enabled by default."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_registry import RegistryEntryDisabler

    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    entry.add_to_hass(hass)

    # Simulate entity that was previously registered as enabled (no disabled_by)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_json",
        config_entry=entry,
        suggested_object_id="student_one_timetable_json",
    )
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_json")
    assert registry.async_get(entity_id).disabled_by is None

    _async_disable_json_sensor_for_existing_install(hass, entry)

    assert registry.async_get(entity_id).disabled_by == RegistryEntryDisabler.INTEGRATION


async def test_disable_json_sensor_migration_skips_user_disabled_entity(hass: HomeAssistant) -> None:
    """One-time migration must not touch entities the user has explicitly disabled."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.entity_registry import RegistryEntryDisabler

    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_json",
        config_entry=entry,
        suggested_object_id="student_one_timetable_json",
        disabled_by=RegistryEntryDisabler.USER,
    )
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_json")

    _async_disable_json_sensor_for_existing_install(hass, entry)

    # Must remain USER-disabled, not changed to INTEGRATION
    assert registry.async_get(entity_id).disabled_by == RegistryEntryDisabler.USER


async def test_disable_json_sensor_migration_no_op_when_entity_absent(hass: HomeAssistant) -> None:
    """Migration must silently no-op when the JSON sensor is not registered at all."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    entry.add_to_hass(hass)
    # No entity registered — should not raise
    _async_disable_json_sensor_for_existing_install(hass, entry)
