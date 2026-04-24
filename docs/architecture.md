# Kreta Home Assistant Architecture

## Purpose

This document defines the initial architecture for a native Home Assistant custom integration for Kreta. It is the implementation baseline for repository structure, data flow, authentication handling, entities, testing, and packaging.

## Goals

- Build a native Home Assistant integration with UI-based configuration only.
- Support multiple independent config entries, one per pupil/account.
- Persist Kreta refresh tokens across restarts.
- Provide timetable data as Home Assistant calendar events.
- Merge announced tests into the matching lesson event when possible.
- Expose a machine-friendly JSON text sensor for external consumers such as ESPHome.
- Package the project so it can be distributed through HACS.

## Out of scope for the initial version

- Automatic institute discovery. Users will enter the school ID manually.
- Grades and homework.
- A separately published PyPI package for the Kreta client.

## Reference inputs

The current design is based on:

- `kreta-homeassistant-prompt.md`
- the prototype code in `reference/`

The prototype confirms the current authentication shape, token refresh requirement, and the initial endpoint set for pupil profile, timetable, school-year data, and announced tests.

## Planned repository structure

```text
.
|-- README.md
|-- docs/
|   `-- architecture.md
|-- hacs.json
|-- custom_components/
|   `-- kreta/
|       |-- __init__.py
|       |-- manifest.json
|       |-- const.py
|       |-- config_flow.py
|       |-- coordinator.py
|       |-- calendar.py
|       |-- sensor.py
|       |-- strings.json
|       |-- translations/
|       |   |-- en.json
|       |   `-- hu.json
|       `-- api/
|           |-- __init__.py
|           |-- auth.py
|           |-- client.py
|           |-- exceptions.py
|           |-- models.py
|           `-- storage.py
|-- tests/
|   `-- components/
|       `-- kreta/
|-- .github/
|   `-- workflows/
|       `-- ci.yml
`-- .gitignore
```

The reusable Kreta API logic will remain inside this repository as an internal package under `custom_components/kreta/api/`. That keeps the network/auth layer separate from Home Assistant platform code without introducing a second distribution artifact in the first release.

## Integration surfaces

### Config entry metadata

Each config entry represents one pupil/account and stores:

- KLIK ID
- user ID
- password
- refresh interval in hours
- calendar lookahead in weeks

Home Assistant's config entry storage will be used for credentials and options. Each entry operates independently so a household can configure multiple children.

### Calendar platform

The calendar platform is the primary surface for timetable data.

Expected behavior:

- lessons are created from timetable entries
- announced tests are merged into matching lessons when correlation is possible
- unmatched tests become standalone calendar events

### JSON text sensor

A text sensor exposes the normalized timetable and exam payload in JSON form. The sensor is intended for downstream consumers that need structured data more easily than calendar entity scraping.

## Data model

The integration will normalize remote data into internal models before exposing it to Home Assistant.

Core model groups:

- pupil metadata
- lesson events
- announced test events
- merged calendar events

Normalized models are preferred over passing raw Kreta payloads into entity code. This keeps parsing logic isolated and makes tests more stable.

## Authentication and token strategy

## High-level flow

1. Create an authenticated session using the Kreta login flow.
2. Persist the returned refresh token in Home Assistant-managed storage.
3. Keep access tokens in memory only.
4. Refresh access when needed using the latest persisted refresh token.
5. Update stored refresh tokens whenever the API returns a new one.

## Storage

Refresh tokens must survive Home Assistant restarts. They will not be stored in ad-hoc flat files. Instead, the integration will use Home Assistant persistent storage keyed by config entry ID.

Planned storage boundaries:

- config entry data/options: credentials and user-configured settings
- integration storage: refresh token and token-related runtime metadata

## Auth error handling

Authentication failures are the most sensitive part of the design because repeated failures can create avoidable load or account lockout risk.

Planned behavior:

1. Detect explicit auth-related failures from HTTP status or payload shape.
2. Attempt one controlled re-login using the stored credentials.
3. Persist the new refresh token if re-login succeeds.
4. Retry the original request once.
5. If re-login fails, surface the entry as failed and stop aggressive retries.

The implementation should use Home Assistant's config-entry error signaling so the integration fails clearly instead of silently spinning on bad credentials.

## Runtime coordination

A coordinator-centric design will manage data refresh for each config entry.

Coordinator responsibilities:

- schedule refreshes according to the configured interval
- determine the lesson/test date range from the configured week window
- fetch pupil metadata and calendar-relevant datasets
- trigger token refresh or controlled re-login when needed
- publish normalized data to platforms

This keeps entities thin and ensures auth logic is not duplicated across platforms.

## Lesson and exam merge rules

Announced tests should be attached to lesson events when a stable correlation exists.

Initial matching strategy:

- same calendar date
- same lesson index, when available
- same or equivalent subject name, when available

If no stable match is available, the announced test becomes a separate calendar event. The JSON sensor will expose the merged result so downstream consumers see the same interpretation as the calendar platform.

## Home Assistant implementation boundaries

### `__init__.py`

- config entry setup/unload
- shared client/coordinator lifecycle

### `config_flow.py`

- initial setup through the UI
- options flow for refresh interval and lookahead window
- credential validation with guarded network calls

### `coordinator.py`

- refresh scheduling
- API fetch orchestration
- normalized state assembly

### `calendar.py`

- lesson and exam calendar entities
- event translation from normalized models

### `sensor.py`

- JSON text sensor
- pupil/account metadata exposure when appropriate

### `api/*`

- auth flow
- endpoint wrappers
- typed models
- exception taxonomy
- persistent token storage helpers

## Testing strategy

The project should follow Home Assistant custom integration testing practices.

### Unit tests

- auth flow and token refresh behavior
- endpoint response parsing
- lesson/test merge logic
- storage behavior
- error classification

### Integration-style tests

- config flow happy path
- invalid credentials path
- multi-entry setup
- options updates
- platform setup and unload
- auth failure recovery and failed-entry handling

### Test data

Remote responses should be captured once, sanitized, and committed as fixtures or mocked payloads. Tests must not depend on live Kreta services.

### CI requirements

- hassfest
- Home Assistant integration tests
- coverage threshold of 90% or higher

## HACS and release considerations

- The repository will include HACS metadata.
- Releases must follow the format `YYYY.MM.DD.SEQ`.
- User-facing documentation remains in Hungarian.
- AI/planning artifacts and local-only files must not be included in published repository content.

## Security and privacy

- Never commit sample credentials, refresh tokens, or captured secrets.
- Sanitize recorded fixtures before storing them in the repository.
- Avoid broad exception swallowing around authentication or transport logic.
- Keep password display masked in the UI and rely on Home Assistant credential handling.

## Open items for implementation

- Final endpoint inventory beyond the currently required timetable, tests, and pupil profile data.
- Exact Home Assistant failure signaling for persistent auth failure after one guarded retry.
- Final JSON payload schema for the text sensor.
- Branding asset delivery path for the stylized `K` icon required by the project brief.
