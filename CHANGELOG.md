# Changelog

All notable changes to this project will be documented in this file.

## 2026.04.28.1

### Fixed

- **Midnight scheduled refresh no longer performs a full re-login when the access token expires.**
  Previously, `async_reauthenticate()` called `async_authenticate(force_login=True)`, which
  bypassed the stored refresh token entirely and fell straight through to the full
  interactive login flow. The `force_login` flag was unnecessary because the access token
  is already cleared before that call. The normal auth flow now correctly tries the stored
  refresh token first and only falls back to a full login if the refresh token is also rejected.

- **Pressing the Refresh button now always triggers an immediate data update.**
  The button previously called `async_request_refresh()`, which is debounced by Home Assistant
  and could be silently skipped if a natural refresh had occurred recently. It now calls
  `async_refresh()` for a guaranteed, non-debounced update.

### Added

- **INFO-level logging for each Kreta API call.**
  Each API interaction (student profile, lessons, announced tests) now emits INFO-level log
  messages showing when the request starts and how many items were returned. This makes it
  easy to trace what the integration is doing in production without enabling debug logging.
  Low-level HTTP request and response details remain at DEBUG level.

## 2026.04.27.1

### Fixed

- **Full re-login no longer silently wipes the stored refresh token.**
  When Kreta's IDP responded to a token refresh or full login request without
  including a new `refresh_token` field (valid in OAuth2 when token rotation is
  disabled), the code previously called `async_set_refresh_token(None)`, which
  deleted the stored token. On the next HA restart or 12-hour refresh cycle the
  token was gone, forcing an unnecessary full interactive login. The stored token
  is now preserved when the server omits a replacement. A `WARNING` is emitted if
  the full PKCE login itself returns no refresh token, since `offline_access` scope
  is always requested.

### Changed

- **Authentication log messages are now at `WARNING` level when a full login is
  triggered unexpectedly.**
  Previously, the reason for a full re-login was invisible in standard INFO-level
  logs. Two new `WARNING` messages explain why:
  - `No stored refresh token for <klik_id>, performing full login` — emitted when
    no token is found in storage (e.g. first run or after a wipe).
  - `Stored refresh token rejected for <klik_id>, falling back to full login` —
    emitted when the IDP rejects the stored token (was previously logged at DEBUG).

## 2026.04.26.4

### Fixed

- **Timetable JSON sensor no longer re-disables itself after the user enables it.**
  Previously, a migration helper ran on every config-entry reload and disabled the
  JSON sensor entity whenever its `disabled_by` field was `None`. Because Home
  Assistant sets `disabled_by` to `None` (not `"user"`) when a user enables a
  previously-disabled entity, the helper could not distinguish "enabled by the user"
  from "enabled by default", and silently forced the entity back to
  `disabled_by: "integration"` on every restart or reload.
  The migration helper has been removed; `_attr_entity_registry_enabled_default = False`
  already handles new installs correctly, and existing entities whose `disabled_by`
  state was already persisted in the registry are no longer touched.
- **Recorder attribute-size warning eliminated for enabled JSON sensor.**
  Added `_unrecorded_attributes` to `KretaJsonSensor` covering the three large
  attribute keys (`payload_json`, `events`, `profile`). The HA recorder now skips
  these keys, keeping the stored state well under the 16 384-byte limit without
  any `configuration.yaml` exclusion needed. The attributes remain fully accessible
  at runtime for automations and templates.

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
