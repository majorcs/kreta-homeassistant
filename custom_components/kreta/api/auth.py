"""Authentication helpers for the Kreta API."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .exceptions import InvalidAuthError

REQUEST_VERIFICATION_TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"'
)


def extract_request_verification_token(html: str) -> str:
    """Extract the request verification token from the login page HTML."""
    match = REQUEST_VERIFICATION_TOKEN_RE.search(html)
    if match is None:
        raise InvalidAuthError("Missing request verification token in login page")
    return match.group(1)


def extract_authorization_code(redirect_location: str) -> str:
    """Extract the authorization code from the callback redirect URL."""
    parsed = urlparse(redirect_location)
    code = parse_qs(parsed.query).get("code", [])
    if not code:
        raise InvalidAuthError("Missing authorization code in callback redirect")
    return code[0]
