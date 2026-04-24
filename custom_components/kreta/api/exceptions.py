"""Exceptions for the Kreta client."""

from __future__ import annotations


class KretaApiError(Exception):
    """Base Kreta API exception."""


class CannotConnectError(KretaApiError):
    """Raised when the API cannot be reached."""


class InvalidAuthError(KretaApiError):
    """Raised when authentication fails."""


class ApiResponseError(KretaApiError):
    """Raised when the API returns an unexpected response."""
