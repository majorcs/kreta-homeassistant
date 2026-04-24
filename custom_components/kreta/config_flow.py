"""Config flow for Kreta."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import KretaApiClient
from .api.exceptions import CannotConnectError, InvalidAuthError, KretaApiError
from .api.storage import MemoryTokenStore
from .const import (
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_REFRESH_HOURS,
    CONF_USER_ID,
    DEFAULT_LOOKAHEAD_WEEKS,
    DEFAULT_REFRESH_HOURS,
    DOMAIN,
    MAX_LOOKAHEAD_WEEKS,
    MAX_REFRESH_HOURS,
    MIN_LOOKAHEAD_WEEKS,
    MIN_REFRESH_HOURS,
)


def _build_user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Build the user step schema."""
    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_KLIK_ID, default=user_input.get(CONF_KLIK_ID, "")): str,
            vol.Required(CONF_USER_ID, default=user_input.get(CONF_USER_ID, "")): str,
            vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")): str,
            vol.Required(
                CONF_REFRESH_HOURS,
                default=user_input.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_REFRESH_HOURS, max=MAX_REFRESH_HOURS)),
            vol.Required(
                CONF_LOOKAHEAD_WEEKS,
                default=user_input.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_LOOKAHEAD_WEEKS, max=MAX_LOOKAHEAD_WEEKS),
            ),
        }
    )


def _build_options_schema(config_entry: config_entries.ConfigEntry) -> vol.Schema:
    """Build the options schema."""
    options = config_entry.options
    return vol.Schema(
        {
            vol.Required(
                CONF_REFRESH_HOURS,
                default=options.get(CONF_REFRESH_HOURS, config_entry.data[CONF_REFRESH_HOURS]),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_REFRESH_HOURS, max=MAX_REFRESH_HOURS)),
            vol.Required(
                CONF_LOOKAHEAD_WEEKS,
                default=options.get(
                    CONF_LOOKAHEAD_WEEKS,
                    config_entry.data[CONF_LOOKAHEAD_WEEKS],
                ),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_LOOKAHEAD_WEEKS, max=MAX_LOOKAHEAD_WEEKS),
            ),
        }
    )


async def async_validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = KretaApiClient(
        session=session,
        klik_id=user_input[CONF_KLIK_ID],
        user_id=user_input[CONF_USER_ID],
        password=user_input[CONF_PASSWORD],
        token_store=MemoryTokenStore(),
    )
    await client.async_authenticate(force_login=True)
    profile = await client.async_get_student_profile()
    return {
        "title": f"{profile.student_name or user_input[CONF_USER_ID]} ({user_input[CONF_KLIK_ID]})",
        "student_name": profile.student_name or user_input[CONF_USER_ID],
    }


class KretaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kreta."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_KLIK_ID].strip().lower()}:{user_input[CONF_USER_ID].strip().lower()}"
            )
            self._abort_if_unique_id_configured()

            try:
                info = await async_validate_input(self.hass, user_input)
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except KretaApiError:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "KretaOptionsFlowHandler":
        """Return the options flow."""
        return KretaOptionsFlowHandler(config_entry)


class KretaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Kreta options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(self._config_entry),
        )
