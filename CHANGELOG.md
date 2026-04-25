# Changelog

All notable changes to this project will be documented in this file.

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
