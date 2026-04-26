"""Typed models for Kreta responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.calendar import CalendarEvent


@dataclass(slots=True)
class StudentProfile:
    """Basic student profile information."""

    student_name: str | None
    birth_name: str | None
    birth_place: str | None
    mother_name: str | None
    phone_number: str | None
    email: str | None
    school_name: str | None
    birth_date: str | None

    def as_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable mapping."""
        return asdict(self)


@dataclass(slots=True)
class AnnouncedTest:
    """A normalized announced test entry."""

    test_date: date
    announced_date: date | None
    subject_name: str
    teacher_name: str | None
    lesson_index: int | None
    theme: str | None
    mode: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        data = asdict(self)
        data["test_date"] = self.test_date.isoformat()
        data["announced_date"] = (
            self.announced_date.isoformat() if self.announced_date is not None else None
        )
        return data


@dataclass(slots=True)
class MergedCalendarEvent:
    """A normalized calendar event exposed to Home Assistant."""

    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str | None
    location: str | None
    lesson_index: int | None
    subject_name: str | None
    exam: AnnouncedTest | None
    source: str

    def as_calendar_event(self) -> CalendarEvent:
        """Convert to a Home Assistant calendar event."""
        return CalendarEvent(
            start=self.start,
            end=self.end,
            summary=f"{self.summary} ⚠️" if self.exam else self.summary,
            description=self.description,
            location=self.location,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "uid": self.uid,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "summary": self.summary,
            "description": self.description,
            "location": self.location,
            "lesson_index": self.lesson_index,
            "subject_name": self.subject_name,
            "exam": self.exam.as_dict() if self.exam else None,
            "source": self.source,
        }

    def as_compact_dict(self) -> dict[str, Any]:
        """Return a compact JSON-serializable mapping for space-constrained consumers.

        Drops uid, description, location, subject_name and source; abbreviates
        lesson_index to idx; collapses start/end to HH:MM time strings; and
        reduces exam to a simple boolean.
        """
        return {
            "start": self.start.strftime("%H:%M"),
            "end": self.end.strftime("%H:%M"),
            "summary": self.summary,
            "idx": self.lesson_index,
            "exam": self.exam is not None,
        }
