"""Tests for Kreta entities and storage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kreta import KretaRuntimeData, async_setup, async_unload_entry
from custom_components.kreta.api.models import AnnouncedTest, MergedCalendarEvent, StudentProfile
from custom_components.kreta.api.storage import KretaTokenStore
from custom_components.kreta.binary_sensor import KretaDayBinarySensor
from custom_components.kreta.binary_sensor import async_setup_entry as async_setup_binary_sensor_entry
from custom_components.kreta.calendar import async_setup_entry as async_setup_calendar_entry
from custom_components.kreta.calendar import KretaCalendarEntity
from custom_components.kreta.const import (
    ATTR_EVENTS_JSON,
    ATTR_PROFILE,
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DOMAIN,
)
from custom_components.kreta.sensor import KretaJsonSensor
from custom_components.kreta.sensor import async_setup_entry as async_setup_sensor_entry


TZ = ZoneInfo("Europe/Budapest")


@dataclass
class DummyCoordinatorData:
    """Coordinator data for entity tests."""

    profile: StudentProfile
    events: list[MergedCalendarEvent]
    lessons_count: int
    tests_count: int
    range_start: datetime
    range_end: datetime
    payload_json: str
    last_success: datetime


@dataclass
class DummyCoordinator:
    """Minimal coordinator stub."""

    data: DummyCoordinatorData


def _event(start: datetime, summary: str, source: str = "lesson") -> MergedCalendarEvent:
    return MergedCalendarEvent(
        uid=f"{summary}-{start.isoformat()}",
        start=start,
        end=start + timedelta(minutes=45),
        summary=summary,
        description=summary,
        location="A1",
        lesson_index=1,
        subject_name=summary,
        exam=AnnouncedTest(
            test_date=start.date(),
            announced_date=date(2026, 4, 25),
            subject_name=summary,
            teacher_name="Teszt Elek",
            lesson_index=1,
            theme="Tema",
            mode="irasbeli",
        )
        if source in {"lesson_with_exam", "exam_only"}
        else None,
        source=source,
    )


def _runtime(entry: MockConfigEntry, events: list[MergedCalendarEvent]) -> KretaRuntimeData:
    del entry
    profile = StudentProfile(
        student_name="Student One",
        birth_name=None,
        birth_place=None,
        mother_name=None,
        phone_number=None,
        email=None,
        school_name="School",
        birth_date=None,
    )
    coordinator = DummyCoordinator(
        DummyCoordinatorData(
            profile=profile,
            events=events,
            lessons_count=2,
            tests_count=1,
            range_start=events[0].start,
            range_end=events[-1].end,
            payload_json='{"events":2}',
            last_success=events[0].start,
        )
    )
    return KretaRuntimeData(client=None, coordinator=coordinator)  # type: ignore[arg-type]


async def test_token_store_round_trip(hass) -> None:
    """Refresh tokens should persist in Home Assistant storage."""
    store = KretaTokenStore(hass, "entry-1")

    await store.async_set_refresh_token("refresh-1")
    assert await store.async_get_refresh_token() == "refresh-1"

    await store.async_set_refresh_token(None)
    assert await store.async_get_refresh_token() is None


async def test_async_setup_initializes_domain(hass) -> None:
    """Integration setup should initialize the domain mapping."""
    assert await async_setup(hass, {})
    assert DOMAIN in hass.data


async def test_async_unload_entry_removes_runtime_data(hass) -> None:
    """Unloading an entry should drop runtime data after platform unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Student One (school01)",
        data={
            CONF_KLIK_ID: "school01",
            CONF_USER_ID: "student01",
            "password": "secret",
            CONF_REFRESH_HOURS: 12,
            CONF_LOOKAHEAD_WEEKS: 2,
        },
        state=ConfigEntryState.LOADED,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = object()

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        new=AsyncMock(return_value=True),
    ):
        assert await async_unload_entry(hass, entry)

    assert entry.entry_id not in hass.data[DOMAIN]


async def test_calendar_entity_exposes_events_and_attributes(hass) -> None:
    """Calendar entities should expose the next matching Kreta events."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(
        entry,
        [_event(now - timedelta(minutes=5), "Matematika"), _event(now + timedelta(hours=1), "Tortenelem")],
    )
    entity = KretaCalendarEntity(entry, runtime)

    current = entity.event
    future_events = await entity.async_get_events(hass, now - timedelta(hours=1), now + timedelta(hours=3))

    assert current is not None
    assert current.summary == "Matematika"
    assert len(future_events) == 2
    assert entity.extra_state_attributes["student"]["student_name"] == "Student One"
    assert entity.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_calendar_entity_handles_missing_data_and_setup(hass) -> None:
    """Calendar setup should add entities and empty coordinators should be safe."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = KretaRuntimeData(client=None, coordinator=DummyCoordinator(data=None))  # type: ignore[arg-type]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    added: list = []

    await async_setup_calendar_entry(hass, entry, added.extend)

    entity = added[0]
    assert entity.event is None
    assert await entity.async_get_events(hass, datetime.now(TZ), datetime.now(TZ)) == []
    assert entity.extra_state_attributes == {}


async def test_sensor_entity_exposes_json_attributes() -> None:
    """JSON sensor should expose the payload in attributes."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika", source="lesson_with_exam")])
    entity = KretaJsonSensor(entry, runtime)

    assert entity.native_value == runtime.coordinator.data.last_success.isoformat()
    assert entity.extra_state_attributes[ATTR_PROFILE]["student_name"] == "Student One"
    assert entity.extra_state_attributes[ATTR_EVENTS_JSON] == '{"events":2}'
    assert entity.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_sensor_entity_handles_missing_data_and_setup(hass) -> None:
    """Sensor setup should add entities and empty coordinators should be safe."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = KretaRuntimeData(client=None, coordinator=DummyCoordinator(data=None))  # type: ignore[arg-type]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    added: list = []

    await async_setup_sensor_entry(hass, entry, added.extend)

    entity = added[0]
    assert entity.native_value is None
    assert entity.extra_state_attributes == {}


async def test_binary_sensor_entities_reflect_today_and_tomorrow(hass) -> None:
    """Binary sensors should expose school-day and exam-day status."""
    now = datetime(2026, 4, 24, 7, 30, tzinfo=TZ)
    tomorrow = now + timedelta(days=1)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(
        entry,
        [
            _event(now.replace(hour=8, minute=0), "Matematika"),
            _event(now.replace(hour=10, minute=0), "Tortenelem", source="lesson_with_exam"),
            _event(tomorrow.replace(hour=9, minute=0), "Biologia"),
            _event(tomorrow.replace(hour=13, minute=0), "Kemia", source="exam_only"),
        ],
    )

    with patch("custom_components.kreta.binary_sensor.dt_util.now", return_value=now):
        school_today = KretaDayBinarySensor(entry, runtime, "school_day", "Is School Day")
        school_tomorrow = KretaDayBinarySensor(
            entry,
            runtime,
            "school_day_tomorrow",
            "Is School Day Tomorrow",
            day_offset=1,
        )
        exam_today = KretaDayBinarySensor(entry, runtime, "exam_day", "Is Exam Day", event_kind="exam")
        exam_tomorrow = KretaDayBinarySensor(
            entry,
            runtime,
            "exam_day_tomorrow",
            "Is Exam Day Tomorrow",
            day_offset=1,
            event_kind="exam",
        )

        assert school_today.is_on is True
        assert school_tomorrow.is_on is True
        assert exam_today.is_on is True
        assert exam_tomorrow.is_on is True
        assert school_today.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_binary_sensor_entities_handle_missing_data_and_setup(hass) -> None:
    """Binary sensor setup should add entities and empty coordinators should be safe."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = KretaRuntimeData(client=None, coordinator=DummyCoordinator(data=None))  # type: ignore[arg-type]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    added: list = []

    await async_setup_binary_sensor_entry(hass, entry, added.extend)

    assert len(added) == 4
    assert all(entity.is_on is None for entity in added)
