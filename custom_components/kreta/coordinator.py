"""Data coordinator for Kreta."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.client import KretaApiClient
from .api.exceptions import CannotConnectError, InvalidAuthError, KretaApiError
from .api.models import AnnouncedTest, MergedCalendarEvent, StudentProfile
from .const import (
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DEFAULT_LOOKAHEAD_WEEKS,
    DEFAULT_REFRESH_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KretaCoordinatorData:
    """Normalized coordinator payload."""

    profile: StudentProfile
    events: list[MergedCalendarEvent]
    lessons_count: int
    tests_count: int
    range_start: datetime
    range_end: datetime
    payload_json: str
    last_success: datetime


def _start_of_current_week() -> date:
    """Return the Monday of the current week."""
    today = dt_util.now().date()
    return today - timedelta(days=today.weekday())


def _event_sort_key(event: MergedCalendarEvent) -> tuple[datetime, datetime, str]:
    """Sort merged events deterministically."""
    return (event.start, event.end, event.uid)


def merge_lessons_and_tests(
    lessons: list[MergedCalendarEvent],
    tests: list[AnnouncedTest],
) -> list[MergedCalendarEvent]:
    """Merge tests into lessons when a stable correlation exists."""
    merged: list[MergedCalendarEvent] = []
    used_test_indexes: set[int] = set()

    for lesson in lessons:
        matching_test: AnnouncedTest | None = None
        for index, announced_test in enumerate(tests):
            if index in used_test_indexes:
                continue
            if announced_test.test_date != lesson.start.date():
                continue
            if (
                announced_test.lesson_index is not None
                and lesson.lesson_index is not None
                and announced_test.lesson_index != lesson.lesson_index
            ):
                continue
            if (
                announced_test.subject_name
                and lesson.subject_name
                and announced_test.subject_name.casefold() != lesson.subject_name.casefold()
            ):
                continue
            matching_test = announced_test
            used_test_indexes.add(index)
            break

        if matching_test is None:
            merged.append(lesson)
            continue

        description_parts = [lesson.description]
        description_parts.append(
            "\n".join(
                part
                for part in (
                    "Bejelentett szamonkeres",
                    f"Tema: {matching_test.theme}" if matching_test.theme else None,
                    f"Mod: {matching_test.mode}" if matching_test.mode else None,
                    (
                        f"Rogzito tanar: {matching_test.teacher_name}"
                        if matching_test.teacher_name
                        else None
                    ),
                )
                if part
            )
        )
        merged.append(
            MergedCalendarEvent(
                uid=lesson.uid,
                start=lesson.start,
                end=lesson.end,
                summary=lesson.summary,
                description="\n\n".join(part for part in description_parts if part),
                location=lesson.location,
                lesson_index=lesson.lesson_index,
                subject_name=lesson.subject_name,
                exam=matching_test,
                source="lesson_with_exam",
            )
        )

    for index, announced_test in enumerate(tests):
        if index in used_test_indexes:
            continue
        start = dt_util.as_local(
            datetime.combine(
                announced_test.test_date,
                time(hour=0, minute=0, tzinfo=dt_util.DEFAULT_TIME_ZONE),
            )
        )
        end = start + timedelta(days=1)
        description = "\n".join(
            part
            for part in (
                "Onallo szamonkeres esemeny",
                f"Tema: {announced_test.theme}" if announced_test.theme else None,
                f"Mod: {announced_test.mode}" if announced_test.mode else None,
                (
                    f"Rogzito tanar: {announced_test.teacher_name}"
                    if announced_test.teacher_name
                    else None
                ),
            )
            if part
        )
        merged.append(
            MergedCalendarEvent(
                uid=f"exam-{announced_test.test_date.isoformat()}-{index}",
                start=start,
                end=end,
                summary=f"Szamonkeres - {announced_test.subject_name}",
                description=description,
                location=None,
                lesson_index=announced_test.lesson_index,
                subject_name=announced_test.subject_name,
                exam=announced_test,
                source="exam_only",
            )
        )

    merged.sort(key=_event_sort_key)
    return merged


class KretaDataUpdateCoordinator(DataUpdateCoordinator[KretaCoordinatorData]):
    """Coordinator for Kreta data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: KretaApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.config_entry = config_entry
        refresh_hours = config_entry.options.get(
            CONF_REFRESH_HOURS,
            config_entry.data.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS),
        )
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=timedelta(hours=refresh_hours),
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> KretaCoordinatorData:
        """Fetch and normalize Kreta data."""
        lookahead_weeks = self.config_entry.options.get(
            CONF_LOOKAHEAD_WEEKS,
            self.config_entry.data.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
        )

        week_start = _start_of_current_week()
        week_end = week_start + timedelta(weeks=lookahead_weeks) - timedelta(days=1)
        range_start = dt_util.as_local(
            datetime.combine(week_start, time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        )
        range_end = dt_util.as_local(
            datetime.combine(week_end, time.max, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        )

        _LOGGER.info(
            "Fetching Kreta data for %s (%s → %s, %d-week lookahead)",
            self.config_entry.data[CONF_USER_ID],
            week_start,
            week_end,
            lookahead_weeks,
        )

        try:
            profile = await self.client.async_get_student_profile()
            lessons = await self.client.async_get_lessons(week_start, week_end)
            tests = await self.client.async_get_announced_tests(week_start, week_end)
        except InvalidAuthError as err:
            raise ConfigEntryAuthFailed("Kreta authentication failed") from err
        except CannotConnectError as err:
            raise UpdateFailed(str(err)) from err
        except KretaApiError as err:
            raise UpdateFailed(str(err)) from err

        merged_events = merge_lessons_and_tests(lessons, tests)

        _LOGGER.info(
            "Kreta data refreshed: %d lessons, %d announced tests → %d calendar events",
            len(lessons),
            len(tests),
            len(merged_events),
        )
        payload = {
            "student": profile.as_dict(),
            "events": [event.as_dict() for event in merged_events],
            "generated_at": dt_util.utcnow().isoformat(),
            "range_start": range_start.isoformat(),
            "range_end": range_end.isoformat(),
            "counts": {"lessons": len(lessons), "tests": len(tests), "events": len(merged_events)},
            "source": {
                "entry_id": self.config_entry.entry_id,
                "klik_id": self.config_entry.data["klik_id"],
                "user_id": self.config_entry.data[CONF_USER_ID],
            },
        }

        return KretaCoordinatorData(
            profile=profile,
            events=merged_events,
            lessons_count=len(lessons),
            tests_count=len(tests),
            range_start=range_start,
            range_end=range_end,
            payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            last_success=dt_util.utcnow(),
        )
