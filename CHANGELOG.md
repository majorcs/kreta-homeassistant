# Changelog

All notable changes to this project will be documented in this file.

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
