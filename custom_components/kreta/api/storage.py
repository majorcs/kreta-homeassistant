"""Persistent token storage for Kreta."""

from __future__ import annotations

from typing import Any, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import STORAGE_KEY, STORAGE_VERSION


class TokenStore(Protocol):
    """Protocol for refresh-token storage backends."""

    async def async_get_refresh_token(self) -> str | None:
        """Return the stored refresh token, if any."""

    async def async_set_refresh_token(self, refresh_token: str | None) -> None:
        """Persist the refresh token."""


class KretaTokenStore:
    """Home Assistant-backed token storage per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize storage."""
        self._entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_get_refresh_token(self) -> str | None:
        """Return the stored refresh token."""
        data = await self._store.async_load() or {}
        entry_data = data.get(self._entry_id, {})
        return entry_data.get("refresh_token")

    async def async_set_refresh_token(self, refresh_token: str | None) -> None:
        """Persist the refresh token."""
        data = await self._store.async_load() or {}
        if refresh_token is None:
            data.pop(self._entry_id, None)
        else:
            data[self._entry_id] = {"refresh_token": refresh_token}
        await self._store.async_save(data)


class MemoryTokenStore:
    """In-memory token storage for config-flow validation."""

    def __init__(self) -> None:
        """Initialize the memory token store."""
        self._refresh_token: str | None = None

    async def async_get_refresh_token(self) -> str | None:
        """Return the current refresh token."""
        return self._refresh_token

    async def async_set_refresh_token(self, refresh_token: str | None) -> None:
        """Set the current refresh token."""
        self._refresh_token = refresh_token
