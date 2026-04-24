"""Constants for the Kreta integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "kreta"

CONF_KLIK_ID = "klik_id"
CONF_USER_ID = "user_id"
CONF_REFRESH_HOURS = "refresh_hours"
CONF_LOOKAHEAD_WEEKS = "lookahead_weeks"

DEFAULT_REFRESH_HOURS = 12
DEFAULT_LOOKAHEAD_WEEKS = 2

MIN_REFRESH_HOURS = 1
MAX_REFRESH_HOURS = 24
MIN_LOOKAHEAD_WEEKS = 1
MAX_LOOKAHEAD_WEEKS = 4

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_tokens"

ATTR_PROFILE = "profile"
ATTR_EVENTS = "events"
ATTR_EVENTS_JSON = "events_json"
ATTR_LESSONS = "lessons"
ATTR_TESTS = "tests"
ATTR_RANGE_START = "range_start"
ATTR_RANGE_END = "range_end"
ATTR_LAST_SUCCESS = "last_success"

DEFAULT_TIMEOUT_SECONDS = 30
