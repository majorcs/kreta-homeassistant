"""Tests for the Kreta config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kreta.api.exceptions import InvalidAuthError
from custom_components.kreta.config_flow import async_validate_input
from custom_components.kreta.const import (
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """A valid config flow should create an entry."""
    user_input = {
        CONF_KLIK_ID: "school01",
        CONF_USER_ID: "student01",
        CONF_PASSWORD: "secret",
        CONF_REFRESH_HOURS: 12,
        CONF_LOOKAHEAD_WEEKS: 2,
    }

    with patch(
        "custom_components.kreta.config_flow.async_validate_input",
        AsyncMock(return_value={"title": "Student One (school01)", "student_name": "Student One"}),
    ), patch(
        "custom_components.kreta.async_setup_entry",
        AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=user_input,
        )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Student One (school01)"


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Invalid credentials should stay on the form with an auth error."""
    with patch(
        "custom_components.kreta.config_flow.async_validate_input",
        AsyncMock(side_effect=InvalidAuthError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_KLIK_ID: "school01",
                CONF_USER_ID: "student01",
                CONF_PASSWORD: "secret",
                CONF_REFRESH_HOURS: 12,
                CONF_LOOKAHEAD_WEEKS: 2,
            },
        )

    assert result2["type"] is FlowResultType.FORM
    assert result2["errors"]["base"] == "invalid_auth"


async def test_validate_input_returns_profile_title(hass: HomeAssistant) -> None:
    """Input validation should derive a title from the returned student profile."""
    fake_profile = type("Profile", (), {"student_name": "Student One"})()

    with patch(
        "custom_components.kreta.config_flow.async_get_clientsession",
        return_value=object(),
    ), patch("custom_components.kreta.config_flow.KretaApiClient") as client_cls:
        client = client_cls.return_value
        client.async_authenticate = AsyncMock()
        client.async_get_student_profile = AsyncMock(return_value=fake_profile)

        result = await async_validate_input(
            hass,
            {
                CONF_KLIK_ID: "school01",
                CONF_USER_ID: "student01",
                CONF_PASSWORD: "secret",
            },
        )

    assert result["title"] == "Student One (school01)"


async def test_options_flow_updates_values(hass: HomeAssistant) -> None:
    """Options flow should persist updated refresh settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Student One (school01)",
        data={
            CONF_KLIK_ID: "school01",
            CONF_USER_ID: "student01",
            CONF_PASSWORD: "secret",
            CONF_REFRESH_HOURS: 12,
            CONF_LOOKAHEAD_WEEKS: 2,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_REFRESH_HOURS: 6, CONF_LOOKAHEAD_WEEKS: 4},
    )

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {CONF_REFRESH_HOURS: 6, CONF_LOOKAHEAD_WEEKS: 4}
