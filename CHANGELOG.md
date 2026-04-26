# Changelog

All notable changes to this project will be documented in this file.

## 2026.04.26.3

### Added

- **Compact Timetable JSON sensor** (`sensor.<name>_compact_timetable_json`): a new sensor enabled by default that exposes the timetable as a compact, daily-grouped JSON payload (~4 KB vs ~16 KB for the full JSON sensor). Events are grouped under a `days` dict keyed by `YYYY-MM-DD`; each entry contains only `start` (HH:MM), `end` (HH:MM), `summary`, `idx` (lesson index), and `exam` (boolean). The sensor state shows the **number of school days** covered by the payload, making it easy to read at a glance in the HA UI and suitable for space-constrained consumers such as ESP32-based displays.

## 2026.04.26.2

### Changed

- **Timetable JSON sensor disabled by default**: the `sensor.<name>_timetable_json` entity is now disabled in the entity registry by default. Because the attribute payload routinely exceeds the HA recorder's 16 384-byte limit, keeping the entity enabled caused a recurring warning in the HA log. Users who need the JSON data in automations can re-enable the entity in the HA UI; they may also want to add a recorder exclusion in `configuration.yaml`.

## 2026.04.26.1

### Added

- **Midnight forced refresh**: the coordinator now schedules an automatic refresh every day at 00:00:30 local time so that day-scoped sensor data (school day, exam day) is always current after midnight, regardless of the configured periodic interval.
- **Last Refresh sensor** (`sensor.<name>_last_refresh`): a `TIMESTAMP` diagnostic sensor that reports the exact datetime of the last successful data fetch.
- **Update Status sensor** (`sensor.<name>_update_status`): an `ENUM` diagnostic sensor with states `ok` / `error`. On failure, its attributes include `last_error` (the error message), `last_error_time` (when it occurred), and — when previous data is available — `last_success`, `range_start`, `range_end`, `lessons_count`, and `tests_count`. Error state is automatically cleared on the next successful refresh.
- **Refresh button** (`button.<name>_refresh`): a diagnostic button entity that triggers an immediate coordinator refresh on press.

## 2026.04.25.2

### Changed

- API error response bodies that contain HTML (e.g. maintenance pages) are now shown as `(HTML response)` in the HA UI instead of dumping the full HTML markup. Plain-text error bodies are truncated to 200 characters. The full response body is still available at DEBUG log level.
- Added INFO-level log entries at key lifecycle points (entry setup, each refresh cycle start/end with event counts, authentication path) to make production monitoring easier without enabling debug logging.

## 2026.04.25.1

### Fixed

- Sensors and calendar no longer disappear after a failed periodic refresh (e.g., when the school's Kreta server is offline overnight). A transient API error (`KretaApiError`, such as 503 Service Unavailable) now raises `UpdateFailed` instead of `ConfigEntryNotReady`, so the coordinator keeps the last-known data and retries at the next scheduled interval

## 2026.04.24.3

### Changed

- Calendar event titles now include a ⚠️ warning sign when the event has an associated exam, making exam days immediately visible in Home Assistant's calendar view

## 2026.04.24.2

Follow-up release after the first public publication.

### Added

- binary sensors for school day and exam day status for today and tomorrow
- local continuity notes in `docs/current-state.md`

### Changed

- GitHub workflow now uses a protected `main` branch with feature-branch PRs and required CI checks

## 2026.04.24.1

Initial public release.

### Added

- native Home Assistant custom integration for Kreta
- Web UI config flow with multi-account support
- persistent refresh-token handling with controlled reauthentication
- calendar platform for timetable events with announced test merging
- JSON-oriented sensor payload for downstream consumers such as ESPHome
- HACS metadata and brand assets
- Hungarian end-user documentation
- architecture documentation
- automated tests, hassfest workflow, HACS validation, and coverage gating
