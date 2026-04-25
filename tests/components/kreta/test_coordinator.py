"""Tests for Kreta coordinator helpers."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kreta.api.exceptions import CannotConnectError, InvalidAuthError, KretaApiError
from custom_components.kreta.api.models import AnnouncedTest, MergedCalendarEvent
from custom_components.kreta.coordinator import KretaDataUpdateCoordinator, merge_lessons_and_tests
from custom_components.kreta.const import (
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DOMAIN,
)


TZ = ZoneInfo("Europe/Budapest")


def _lesson(
    uid: str,
    summary: str,
    start: datetime,
    end: datetime,
    lesson_index: int,
) -> MergedCalendarEvent:
    return MergedCalendarEvent(
        uid=uid,
        start=start,
        end=end,
        summary=summary,
        description=summary,
        location="A1",
        lesson_index=lesson_index,
        subject_name=summary,
        exam=None,
        source="lesson",
    )


def test_merge_lessons_and_tests_merges_matching_exam() -> None:
    """Matching tests should enrich the lesson event."""
    lesson = _lesson(
        "math-1",
        "Matematika",
        datetime(2026, 4, 27, 8, 0, tzinfo=TZ),
        datetime(2026, 4, 27, 8, 45, tzinfo=TZ),
        1,
    )
    test = AnnouncedTest(
        test_date=date(2026, 4, 27),
        announced_date=date(2026, 4, 25),
        subject_name="Matematika",
        teacher_name="Teszt Elek",
        lesson_index=1,
        theme="Egyenletek",
        mode="irasbeli",
    )

    merged = merge_lessons_and_tests([lesson], [test])

    assert len(merged) == 1
    assert merged[0].exam == test
    assert merged[0].source == "lesson_with_exam"
    assert "Bejelentett szamonkeres" in (merged[0].description or "")


def test_merge_lessons_and_tests_creates_standalone_exam() -> None:
    """Unmatched tests should become standalone calendar events."""
    lesson = _lesson(
        "history-1",
        "Tortenelem",
        datetime(2026, 4, 27, 10, 0, tzinfo=TZ),
        datetime(2026, 4, 27, 10, 45, tzinfo=TZ),
        3,
    )
    test = AnnouncedTest(
        test_date=date(2026, 4, 28),
        announced_date=date(2026, 4, 25),
        subject_name="Biologia",
        teacher_name=None,
        lesson_index=None,
        theme="Sejtek",
        mode=None,
    )

    merged = merge_lessons_and_tests([lesson], [test])

    assert len(merged) == 2
    assert any(event.source == "exam_only" for event in merged)


def test_merge_lessons_and_tests_skips_non_matching_subject_and_index() -> None:
    """Non-matching lesson index or subject should not merge."""
    lesson = _lesson(
        "history-1",
        "Tortenelem",
        datetime(2026, 4, 27, 10, 0, tzinfo=TZ),
        datetime(2026, 4, 27, 10, 45, tzinfo=TZ),
        3,
    )
    tests = [
        AnnouncedTest(
            test_date=date(2026, 4, 27),
            announced_date=date(2026, 4, 25),
            subject_name="Tortenelem",
            teacher_name=None,
            lesson_index=4,
            theme="Tema",
            mode=None,
        ),
        AnnouncedTest(
            test_date=date(2026, 4, 27),
            announced_date=date(2026, 4, 25),
            subject_name="Biologia",
            teacher_name=None,
            lesson_index=3,
            theme="Tema",
            mode=None,
        ),
    ]

    merged = merge_lessons_and_tests([lesson], tests)

    assert len(merged) == 3
    assert [event.source for event in merged].count("exam_only") == 2


async def test_coordinator_update_data_success(hass) -> None:
    """Coordinator should build a normalized payload."""
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
    )
    client = type("Client", (), {})()
    client.async_get_student_profile = AsyncMock(
        return_value=type("Profile", (), {"as_dict": lambda self: {"student_name": "Student One"}})()
    )
    client.async_get_lessons = AsyncMock(return_value=[_lesson("math-1", "Matematika", datetime(2026, 4, 27, 8, 0, tzinfo=TZ), datetime(2026, 4, 27, 8, 45, tzinfo=TZ), 1)])
    client.async_get_announced_tests = AsyncMock(return_value=[])
    coordinator = KretaDataUpdateCoordinator(hass, entry, client)

    data = await coordinator._async_update_data()

    assert data.profile.as_dict()["student_name"] == "Student One"
    assert data.lessons_count == 1
    assert "counts" in data.payload_json


@pytest.mark.parametrize(
    ("side_effect", "expected_exception"),
    [
        (InvalidAuthError, ConfigEntryAuthFailed),
        (CannotConnectError, UpdateFailed),
        (KretaApiError, UpdateFailed),
    ],
)
async def test_coordinator_update_data_error_mapping(hass, side_effect, expected_exception) -> None:
    """Coordinator should map API errors to Home Assistant exceptions."""
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
    )
    client = type("Client", (), {})()
    client.async_get_student_profile = AsyncMock(side_effect=side_effect("boom"))
    client.async_get_lessons = AsyncMock()
    client.async_get_announced_tests = AsyncMock()
    coordinator = KretaDataUpdateCoordinator(hass, entry, client)

    with pytest.raises(expected_exception):
        await coordinator._async_update_data()


async def test_kreta_api_error_on_periodic_refresh_keeps_data(hass) -> None:
    """KretaApiError during a periodic refresh should preserve existing coordinator data.

    This is a regression test: the original code raised ConfigEntryNotReady for
    KretaApiError, which caused HA to unload the config entry during periodic refresh.
    The correct exception is UpdateFailed, which keeps the last-known data and retries
    at the next interval.
    """
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
    )
    lesson = _lesson(
        "math-1",
        "Matematika",
        datetime(2026, 4, 27, 8, 0, tzinfo=TZ),
        datetime(2026, 4, 27, 8, 45, tzinfo=TZ),
        1,
    )
    profile = type("Profile", (), {"as_dict": lambda self: {"student_name": "Student One"}})()
    client = type("Client", (), {})()
    client.async_get_student_profile = AsyncMock(return_value=profile)
    client.async_get_lessons = AsyncMock(return_value=[lesson])
    client.async_get_announced_tests = AsyncMock(return_value=[])
    coordinator = KretaDataUpdateCoordinator(hass, entry, client)

    previous_data = await coordinator._async_update_data()
    coordinator.data = previous_data

    client.async_get_student_profile = AsyncMock(side_effect=KretaApiError("503"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator.data is previous_data
