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
from custom_components.kreta.button import KretaRefreshButton
from custom_components.kreta.button import async_setup_entry as async_setup_button_entry
from custom_components.kreta.calendar import async_setup_entry as async_setup_calendar_entry
from custom_components.kreta.calendar import KretaCalendarEntity
from custom_components.kreta.const import (
    ATTR_COMPACT_EVENTS_JSON,
    ATTR_EVENTS_JSON,
    ATTR_LAST_ERROR,
    ATTR_LAST_ERROR_TIME,
    ATTR_LAST_SUCCESS,
    ATTR_PROFILE,
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DOMAIN,
)
from custom_components.kreta.sensor import KretaCompactJsonSensor, KretaJsonSensor, KretaLastRefreshSensor, KretaUpdateStatusSensor
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
    compact_payload_json: str
    last_success: datetime


@dataclass
class DummyCoordinator:
    """Minimal coordinator stub."""

    data: DummyCoordinatorData
    last_update_success: bool = True
    last_error_message: str | None = None
    last_error_time: datetime | None = None


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
            compact_payload_json='{"days":{}}',
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


async def test_calendar_event_with_exam_appends_warning_to_summary() -> None:
    """Calendar events with exam info should have ⚠️ appended to the summary."""
    now = datetime.now(TZ)
    exam = AnnouncedTest(
        test_date=now.date(),
        announced_date=date(2026, 4, 25),
        subject_name="Matematika",
        teacher_name="Teszt Elek",
        lesson_index=1,
        theme="Egyenletek",
        mode="irasbeli",
    )
    event = MergedCalendarEvent(
        uid="math-exam",
        start=now,
        end=now + timedelta(minutes=45),
        summary="Matematika",
        description="Tantargy: Matematika\n\nBejelentett szamonkeres\nTema: Egyenletek\nMod: irasbeli",
        location="A1",
        lesson_index=1,
        subject_name="Matematika",
        exam=exam,
        source="lesson_with_exam",
    )

    cal_event = event.as_calendar_event()

    assert cal_event.summary == "Matematika ⚠️"
    assert cal_event.description is not None
    assert "Bejelentett szamonkeres" in cal_event.description
    assert "Egyenletek" in cal_event.description


async def test_calendar_event_without_exam_leaves_summary_unchanged() -> None:
    """Plain lesson calendar events should have no ⚠️ in the summary."""
    now = datetime.now(TZ)
    event = _event(now, "Matematika", source="lesson")

    cal_event = event.as_calendar_event()

    assert cal_event.summary == "Matematika"
    assert "⚠️" not in (cal_event.summary or "")


async def test_calendar_exam_only_event_appends_warning_to_summary() -> None:
    """Standalone exam-only events should also have ⚠️ appended to the summary."""
    now = datetime.now(TZ)
    event = _event(now, "Biologia", source="exam_only")

    cal_event = event.as_calendar_event()

    assert cal_event.summary == "Biologia ⚠️"


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


async def test_json_sensor_disabled_by_default() -> None:
    """JSON sensor must be disabled in the entity registry by default to suppress recorder warnings."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    entity = KretaJsonSensor(entry, runtime)
    assert entity.entity_registry_enabled_default is False


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


async def test_last_refresh_sensor_exposes_timestamp() -> None:
    """Last refresh sensor should return the coordinator's last_success datetime."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    entity = KretaLastRefreshSensor(entry, runtime)

    assert entity.native_value == runtime.coordinator.data.last_success
    assert entity.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_last_refresh_sensor_handles_missing_data() -> None:
    """Last refresh sensor should return None when coordinator has no data."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = KretaRuntimeData(client=None, coordinator=DummyCoordinator(data=None))  # type: ignore[arg-type]
    entity = KretaLastRefreshSensor(entry, runtime)

    assert entity.native_value is None


async def test_update_status_sensor_reports_ok_on_success() -> None:
    """Update status sensor should return 'ok' when last update succeeded."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    entity = KretaUpdateStatusSensor(entry, runtime)

    assert entity.native_value == "ok"
    attrs = entity.extra_state_attributes
    assert ATTR_LAST_SUCCESS in attrs
    assert "lessons_count" in attrs
    assert "tests_count" in attrs
    assert ATTR_LAST_ERROR not in attrs
    assert ATTR_LAST_ERROR_TIME not in attrs
    assert entity.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_update_status_sensor_reports_error_with_details() -> None:
    """Update status sensor should return 'error' and expose error details when last update failed."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    runtime.coordinator.last_update_success = False
    runtime.coordinator.last_error_message = "Connection refused"
    runtime.coordinator.last_error_time = now

    entity = KretaUpdateStatusSensor(entry, runtime)

    assert entity.native_value == "error"
    attrs = entity.extra_state_attributes
    assert attrs[ATTR_LAST_ERROR] == "Connection refused"
    assert attrs[ATTR_LAST_ERROR_TIME] == now.isoformat()


async def test_refresh_button_press_triggers_coordinator_refresh() -> None:
    """Pressing the refresh button should request a coordinator refresh."""
    from unittest.mock import AsyncMock

    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    runtime.coordinator.async_request_refresh = AsyncMock()
    entity = KretaRefreshButton(entry, runtime)

    await entity.async_press()

    runtime.coordinator.async_request_refresh.assert_awaited_once()
    assert entity.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_button_setup_adds_entity(hass) -> None:
    """Button setup should add one refresh button entity."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = KretaRuntimeData(client=None, coordinator=DummyCoordinator(data=None))  # type: ignore[arg-type]
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    added: list = []

    await async_setup_button_entry(hass, entry, added.extend)

    assert len(added) == 1
    assert isinstance(added[0], KretaRefreshButton)


async def test_sensor_setup_adds_four_entities(hass) -> None:
    """Sensor setup should register JSON, compact JSON, last-refresh, and update-status sensors."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    added: list = []

    await async_setup_sensor_entry(hass, entry, added.extend)

    assert len(added) == 4
    entity_types = {type(e) for e in added}
    assert KretaJsonSensor in entity_types
    assert KretaCompactJsonSensor in entity_types
    assert KretaLastRefreshSensor in entity_types
    assert KretaUpdateStatusSensor in entity_types


async def test_compact_json_sensor_exposes_days_attribute() -> None:
    """Compact JSON sensor should expose the compact_events_json attribute."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika", source="lesson_with_exam")])
    entity = KretaCompactJsonSensor(entry, runtime)

    assert entity.native_value == 1  # one unique school day
    assert entity.extra_state_attributes[ATTR_COMPACT_EVENTS_JSON] == '{"days":{}}'
    assert entity.device_info["identifiers"] == {(DOMAIN, entry.entry_id)}


async def test_compact_json_sensor_enabled_by_default() -> None:
    """Compact JSON sensor must be enabled by default (payload is small enough for HA recorder)."""
    now = datetime.now(TZ)
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = _runtime(entry, [_event(now, "Matematika")])
    entity = KretaCompactJsonSensor(entry, runtime)

    assert entity.entity_registry_enabled_default is True


async def test_compact_json_sensor_handles_missing_data() -> None:
    """Compact JSON sensor should return None state and empty attrs when coordinator has no data."""
    entry = MockConfigEntry(domain=DOMAIN, title="Student One (school01)", data={})
    runtime = KretaRuntimeData(client=None, coordinator=DummyCoordinator(data=None))  # type: ignore[arg-type]
    entity = KretaCompactJsonSensor(entry, runtime)

    assert entity.native_value is None
    assert entity.extra_state_attributes == {}

