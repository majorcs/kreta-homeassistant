# Current state

This document records the current implementation and publication state of the Kreta Home Assistant integration so work can be resumed quickly later.

## Summary

- The integration is implemented under `custom_components/kreta`.
- The repository is published at `git@github.com:majorcs/kreta-homeassistant.git`.
- Release `2026.04.24.1` is published and HACS-installable.
- CI is green (`test`, `hassfest`, `hacs` all passing on the latest run).
- The tracked work plan is up to date with all recorded todos completed.

## What is already done

1. Native Home Assistant custom integration scaffolded and implemented.
2. Async Kreta client added with login, token refresh, and persistent token storage.
3. UI config flow and options flow added with multi-entry support.
4. Coordinator and merge logic added for lessons and announced tests.
5. Calendar platform and JSON-oriented sensor platform added.
6. Hungarian README, architecture docs, ESPHome usage notes, branding, HACS metadata, and CI added.
7. Local Home Assistant launcher and dedicated manual test environment added.
8. Announced-test timezone rollover bug fixed and covered by regression tests.
9. Repository published, release created, and GitHub Actions failures resolved.
10. Binary sensors for school day and exam day (today and tomorrow) added.
11. Midnight forced refresh, Last Refresh sensor, Update Status sensor, and Refresh button added.

## Important repository notes

- `reference/` is intentionally excluded from publication.
- `scripts/manual_test_march_23.py` is intentionally excluded from publication.
- The published remote uses SSH, not HTTPS.
- The README already contains the corrected Hungarian accents.
- `main` is protected on GitHub and now requires pull requests with passing `test`, `hassfest`, and `hacs` checks.
- New features should be developed on feature branches and merged through PRs; no additional reviewer approval is required.

## Local manual environment

- Launcher script: `scripts/run-homeassistant.sh`
- Virtual environment: `.venv-ha/`
- Home Assistant config directory: `.homeassistant-dev/`
- PID file: `.homeassistant-dev/homeassistant.pid`
- Log file: `.homeassistant-dev/homeassistant.log`

The script manages start, stop, restart, and status for the local manual instance.

## Key implementation files

- `custom_components/kreta/__init__.py`
- `custom_components/kreta/config_flow.py`
- `custom_components/kreta/coordinator.py`
- `custom_components/kreta/calendar.py`
- `custom_components/kreta/sensor.py`
- `custom_components/kreta/api/client.py`
- `tests/components/kreta/test_api.py`
- `tests/components/kreta/test_config_flow.py`
- `tests/components/kreta/test_init.py`
- `.github/workflows/ci.yml`

## Recent continuity notes

- The announced test date bug came from parsing UTC timestamps as plain dates before converting to Hungary local time.
- The final CI fixes were test-only cleanup changes so mocked Home Assistant tests do not create real client sessions that leave shutdown threads behind.
- The latest workflow state is fully green, so there is no known open blocker at the moment.

## If work continues later

- Treat institute discovery as optional research only; the user can provide the school ID directly.
- Preserve the current publication exclusions unless the user explicitly changes that decision.
- If a new release is needed, bump all release/version metadata consistently and publish a new GitHub release/tag.
- If API behavior changes, re-check lesson/test merge behavior and timezone handling first.
