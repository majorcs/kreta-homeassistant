"""Tests for Kreta API helpers and client behavior."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import ClientError

from custom_components.kreta.api.auth import (
    extract_authorization_code,
    extract_request_verification_token,
)
from custom_components.kreta.api.client import KretaApiClient, _summarize_error_body
from custom_components.kreta.api.exceptions import (
    ApiResponseError,
    CannotConnectError,
    InvalidAuthError,
    KretaApiError,
)
from custom_components.kreta.api.models import MergedCalendarEvent, StudentProfile
from custom_components.kreta.api.storage import MemoryTokenStore


class FakeResponse:
    """Minimal fake aiohttp response."""

    def __init__(
        self,
        *,
        status: int = 200,
        json_data=None,
        text_data: str = "",
        headers: dict[str, str] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.headers = headers or {}
        self._raise_error = raise_error
        self.released = False

    async def json(self):
        """Return JSON or raise."""
        if self._raise_error:
            raise self._raise_error
        return self._json_data

    async def text(self) -> str:
        """Return response text."""
        return self._text_data

    def raise_for_status(self) -> None:
        """Fake raise_for_status."""
        if self.status >= 400:
            raise ClientError(f"status={self.status}")

    def release(self) -> None:
        """Mark response as released."""
        self.released = True


def _client() -> KretaApiClient:
    """Build a client with a mocked session."""
    session = AsyncMock()
    return KretaApiClient(
        session=session,
        klik_id="school01",
        user_id="student01",
        password="secret",
        token_store=MemoryTokenStore(),
    )


def test_extract_request_verification_token() -> None:
    """The login page parser should extract the hidden request token."""
    html = '<input name="__RequestVerificationToken" type="hidden" value="abc123">'
    assert extract_request_verification_token(html) == "abc123"


def test_extract_request_verification_token_missing() -> None:
    """Missing request tokens should raise invalid auth."""
    with pytest.raises(InvalidAuthError):
        extract_request_verification_token("<html></html>")


def test_extract_authorization_code() -> None:
    """The callback parser should extract the code parameter."""
    assert (
        extract_authorization_code("https://example.test/callback?code=xyz&state=test")
        == "xyz"
    )


def test_extract_authorization_code_missing() -> None:
    """Missing callback codes should raise invalid auth."""
    with pytest.raises(InvalidAuthError):
        extract_authorization_code("https://example.test/callback?state=test")


async def test_async_authenticate_uses_stored_refresh_token() -> None:
    """Stored refresh tokens should be preferred over full login."""
    client = _client()
    client._token_store.async_get_refresh_token = AsyncMock(return_value="refresh-token")
    client._async_exchange_refresh_token = AsyncMock()
    client._async_login = AsyncMock()

    await client.async_authenticate()

    client._async_exchange_refresh_token.assert_awaited_once_with("refresh-token")
    client._async_login.assert_not_awaited()


async def test_async_authenticate_falls_back_to_login_when_refresh_fails() -> None:
    """A rejected refresh token should trigger a full login and log a warning."""
    client = _client()
    client._token_store.async_get_refresh_token = AsyncMock(return_value="refresh-token")
    client._async_exchange_refresh_token = AsyncMock(side_effect=InvalidAuthError)
    client._async_login = AsyncMock()

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        await client.async_authenticate()

    client._async_login.assert_awaited_once()
    mock_logger.warning.assert_any_call(
        "Stored refresh token rejected for %s, falling back to full login",
        client._klik_id,
    )


async def test_async_authenticate_no_refresh_token_logs_warning() -> None:
    """Missing stored refresh token should trigger a full login and log a warning."""
    client = _client()
    client._token_store.async_get_refresh_token = AsyncMock(return_value=None)
    client._async_login = AsyncMock()

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        await client.async_authenticate()

    client._async_login.assert_awaited_once()
    mock_logger.warning.assert_any_call(
        "No stored refresh token for %s, performing full login",
        client._klik_id,
    )


async def test_async_authenticate_returns_early_with_access_token() -> None:
    """Existing access tokens should skip further auth work."""
    client = _client()
    client._access_token = "access"
    client._async_login = AsyncMock()

    await client.async_authenticate()

    client._async_login.assert_not_awaited()


async def test_async_reauthenticate_clears_token_and_uses_refresh_token() -> None:
    """Reauthentication should clear the cached access token and try the refresh token first."""
    client = _client()
    client._access_token = "stale-token"
    client.async_authenticate = AsyncMock()

    await client.async_reauthenticate()

    assert client._access_token is None
    client.async_authenticate.assert_awaited_once_with()


async def test_async_reauthenticate_does_not_skip_refresh_token() -> None:
    """After a 401, reauthentication should use the stored refresh token, not full login."""
    client = _client()
    client._access_token = "stale-token"
    client._token_store.async_get_refresh_token = AsyncMock(return_value="stored-refresh")
    client._async_exchange_refresh_token = AsyncMock()
    client._async_login = AsyncMock()

    await client.async_reauthenticate()

    client._async_exchange_refresh_token.assert_awaited_once_with("stored-refresh")
    client._async_login.assert_not_awaited()


async def test_async_get_student_profile() -> None:
    """Student profiles should be normalized from Kreta payloads."""
    client = _client()
    client._async_get_json = AsyncMock(
        return_value={
            "Nev": "Student One",
            "SzuletesiNev": "Birth Name",
            "SzuletesiHely": "Budapest",
            "AnyjaNeve": "Parent",
            "Telefonszam": "123",
            "EmailCim": "student@example.com",
            "SzuletesiDatum": "2010-09-01T00:00:00Z",
            "Intezmeny": {"TeljesNev": "School"},
        }
    )

    profile = await client.async_get_student_profile()

    assert profile == StudentProfile(
        student_name="Student One",
        birth_name="Birth Name",
        birth_place="Budapest",
        mother_name="Parent",
        phone_number="123",
        email="student@example.com",
        school_name="School",
        birth_date="2010-09-01",
    )


async def test_async_get_lessons_filters_and_sorts() -> None:
    """Only lesson entries should be exposed as timetable events."""
    client = _client()
    client._async_get_json = AsyncMock(
        return_value=[
            {
                "Tipus": {"Nev": "TanitasiOra"},
                "KezdetIdopont": "2026-04-27T09:00:00Z",
                "VegIdopont": "2026-04-27T09:45:00Z",
                "Nev": "Matematika",
                "TeremNeve": "A1",
                "Oraszam": 2,
            },
            {
                "Tipus": {"Nev": "Szünet"},
                "KezdetIdopont": "2026-04-27T10:00:00Z",
                "VegIdopont": "2026-04-27T10:15:00Z",
            },
            {
                "Tipus": {"Nev": "OrarendiOra"},
                "KezdetIdopont": "2026-04-27T08:00:00Z",
                "VegIdopont": "2026-04-27T08:45:00Z",
                "Nev": "Tortenelem",
                "TeremNeve": "B2",
                "Oraszam": 1,
            },
        ]
    )

    lessons = await client.async_get_lessons(date(2026, 4, 27), date(2026, 4, 27))

    assert len(lessons) == 2
    assert [lesson.summary for lesson in lessons] == ["Tortenelem", "Matematika"]
    assert all(isinstance(lesson, MergedCalendarEvent) for lesson in lessons)


async def test_async_get_announced_tests_splits_months() -> None:
    """Longer test ranges should be queried in monthly chunks."""
    client = _client()
    client._async_get_json = AsyncMock(
        side_effect=[
            [
                {
                    "Datum": "2026-04-30T00:00:00Z",
                    "BejelentesDatuma": "2026-04-28T00:00:00Z",
                    "TantargyNeve": "Matematika",
                    "RogzitoTanarNeve": "Teszt Elek",
                    "OrarendiOraOraszama": 2,
                    "Temaja": "Egyenletek",
                    "Modja": {"Leiras": "irasbeli"},
                }
            ],
            [
                {
                    "Datum": "2026-05-02T00:00:00Z",
                    "BejelentesDatuma": None,
                    "TantargyNeve": "Biologia",
                    "RogzitoTanarNeve": None,
                    "OrarendiOraOraszama": None,
                    "Temaja": None,
                    "Modja": {"Leiras": None},
                }
            ],
        ]
    )

    tests = await client.async_get_announced_tests(date(2026, 4, 30), date(2026, 5, 2))

    assert len(tests) == 2
    assert client._async_get_json.await_count == 2
    assert tests[0].subject_name == "Matematika"
    assert tests[1].subject_name == "Biologia"


def test_parse_local_date_converts_utc_rollover_to_local_day() -> None:
    """UTC late-night timestamps should map to the next local calendar day."""
    client = _client()

    assert client._parse_local_date("2026-03-22T23:00:00Z") == date(2026, 3, 23)
    assert client._parse_local_date("2026-03-18T07:07:44Z") == date(2026, 3, 18)
    assert client._parse_local_date("2026-03-23") == date(2026, 3, 23)


async def test_async_get_json_raises_on_invalid_json() -> None:
    """Invalid JSON responses should raise an API response error."""
    client = _client()
    client._async_request = AsyncMock(return_value=FakeResponse(raise_error=ValueError("bad json")))

    with pytest.raises(ApiResponseError):
        await client._async_get_json("Sajat/TanuloAdatlap")


async def test_async_request_reauthenticates_once_on_401() -> None:
    """401 responses should trigger a single reauthentication and retry."""
    client = _client()
    client._access_token = "old-token"
    client.async_authenticate = AsyncMock()
    client.async_reauthenticate = AsyncMock()
    client._session.request = AsyncMock(
        side_effect=[
            FakeResponse(status=401),
            FakeResponse(status=200, json_data={"ok": True}),
        ]
    )

    response = await client._async_request("get", "https://example.test", params={"a": 1})

    assert response.status == 200
    assert client.async_reauthenticate.await_count == 1


async def test_async_request_raises_invalid_auth_after_second_auth_failure() -> None:
    """Repeated auth failures should raise InvalidAuthError."""
    client = _client()
    client.async_authenticate = AsyncMock()
    client.async_reauthenticate = AsyncMock()
    client._session.request = AsyncMock(return_value=FakeResponse(status=403))

    with pytest.raises(InvalidAuthError):
        await client._async_request(
            "get",
            "https://example.test",
            retry_on_auth_error=False,
        )


async def test_async_request_raises_api_error_on_http_failure() -> None:
    """Non-auth HTTP failures should raise a generic API error."""
    client = _client()
    client.async_authenticate = AsyncMock()
    client._session.request = AsyncMock(
        return_value=FakeResponse(status=500, text_data="server error")
    )

    with pytest.raises(KretaApiError):
        await client._async_request("get", "https://example.test")


async def test_async_request_without_auth_skips_authentication() -> None:
    """Unauthenticated requests should skip access-token handling."""
    client = _client()
    client.async_authenticate = AsyncMock()
    client._session.request = AsyncMock(return_value=FakeResponse(status=200))

    await client._async_request("get", "https://example.test", require_auth=False)

    client.async_authenticate.assert_not_awaited()


async def test_async_request_raises_cannot_connect() -> None:
    """Transport failures should be surfaced as connectivity errors."""
    client = _client()
    client.async_authenticate = AsyncMock()
    client._session.request = AsyncMock(side_effect=ClientError("boom"))

    with pytest.raises(CannotConnectError):
        await client._async_request("get", "https://example.test")


async def test_async_exchange_refresh_token_success_and_invalid() -> None:
    """Refresh-token exchange should persist new tokens and reject invalid ones."""
    client = _client()
    client._session.post = AsyncMock(
        return_value=FakeResponse(
            status=200,
            json_data={"access_token": "access", "refresh_token": "new-refresh"},
        )
    )

    await client._async_exchange_refresh_token("refresh-token")

    assert client._access_token == "access"
    assert await client._token_store.async_get_refresh_token() == "new-refresh"

    client._session.post = AsyncMock(return_value=FakeResponse(status=400))
    with pytest.raises(InvalidAuthError):
        await client._async_exchange_refresh_token("refresh-token")

    client._session.post = AsyncMock(
        return_value=FakeResponse(status=500, text_data="server error")
    )
    with pytest.raises(KretaApiError):
        await client._async_exchange_refresh_token("refresh-token")

    client._session.post = AsyncMock(return_value=FakeResponse(status=200, json_data={}))
    with pytest.raises(InvalidAuthError):
        await client._async_exchange_refresh_token("refresh-token")


async def test_async_exchange_refresh_token_preserves_stored_token_when_no_new_one() -> None:
    """If the server omits refresh_token in its response, the stored token must not be wiped."""
    client = _client()
    await client._token_store.async_set_refresh_token("existing-refresh")
    client._session.post = AsyncMock(
        return_value=FakeResponse(status=200, json_data={"access_token": "access"})
    )

    await client._async_exchange_refresh_token("existing-refresh")

    assert client._access_token == "access"
    assert await client._token_store.async_get_refresh_token() == "existing-refresh"


async def test_async_exchange_refresh_token_raises_on_transport_error() -> None:
    """Refresh-token transport failures should raise CannotConnectError."""
    client = _client()
    client._session.post = AsyncMock(side_effect=ClientError("boom"))

    with pytest.raises(CannotConnectError):
        await client._async_exchange_refresh_token("refresh-token")


async def test_async_login_success() -> None:
    """The interactive login flow should store new tokens."""
    client = _client()
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
            ),
            FakeResponse(
                status=302,
                headers={"location": "https://example.test/callback?code=auth-code"},
            ),
        ]
    )
    client._session.post = AsyncMock(
        side_effect=[
            FakeResponse(status=200),
            FakeResponse(
                status=200,
                json_data={"access_token": "access", "refresh_token": "refresh"},
            ),
        ]
    )

    await client._async_login()

    assert client._access_token == "access"
    assert await client._token_store.async_get_refresh_token() == "refresh"


async def test_async_login_preserves_stored_token_and_warns_when_no_refresh_token() -> None:
    """If full login response omits refresh_token, warn and keep any existing stored token."""
    client = _client()
    await client._token_store.async_set_refresh_token("existing-refresh")
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
            ),
            FakeResponse(
                status=302,
                headers={"location": "https://example.test/callback?code=auth-code"},
            ),
        ]
    )
    client._session.post = AsyncMock(
        side_effect=[
            FakeResponse(status=200),
            FakeResponse(status=200, json_data={"access_token": "access"}),
        ]
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        await client._async_login()

    assert client._access_token == "access"
    assert await client._token_store.async_get_refresh_token() == "existing-refresh"
    mock_logger.warning.assert_any_call(
        "Full login for %s did not return a refresh token; "
        "stored token (if any) is preserved",
        client._klik_id,
    )


async def test_async_login_requires_redirect_location() -> None:
    """The login flow should fail clearly if the callback lacks a redirect."""
    client = _client()
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
            ),
            FakeResponse(status=302, headers={}),
        ]
    )
    client._session.post = AsyncMock(side_effect=[FakeResponse(status=200), FakeResponse(status=200)])

    with pytest.raises(InvalidAuthError):
        await client._async_login()


async def test_async_login_raises_on_login_form_failure() -> None:
    """A failed login form submit should raise InvalidAuthError."""
    client = _client()
    client._session.get = AsyncMock(
        return_value=FakeResponse(
            status=200,
            text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
        )
    )
    client._session.post = AsyncMock(return_value=FakeResponse(status=401))

    with pytest.raises(InvalidAuthError):
        await client._async_login()


async def test_async_login_raises_when_callback_does_not_redirect() -> None:
    """A non-redirect callback should raise InvalidAuthError."""
    client = _client()
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
            ),
            FakeResponse(status=200),
        ]
    )
    client._session.post = AsyncMock(side_effect=[FakeResponse(status=200), FakeResponse(status=200)])

    with pytest.raises(InvalidAuthError):
        await client._async_login()


async def test_async_login_raises_when_token_exchange_fails() -> None:
    """A failed authorization-code exchange should raise InvalidAuthError."""
    client = _client()
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
            ),
            FakeResponse(
                status=302,
                headers={"location": "https://example.test/callback?code=auth-code"},
            ),
        ]
    )
    client._session.post = AsyncMock(side_effect=[FakeResponse(status=200), FakeResponse(status=401)])

    with pytest.raises(InvalidAuthError):
        await client._async_login()


async def test_async_login_raises_on_transport_error() -> None:
    """Transport failures in login should raise CannotConnectError."""
    client = _client()
    client._session.get = AsyncMock(side_effect=ClientError("boom"))

    with pytest.raises(CannotConnectError):
        await client._async_login()


async def test_async_login_requires_access_token_in_payload() -> None:
    """A successful token response must still include an access token."""
    client = _client()
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="abc123">',
            ),
            FakeResponse(
                status=302,
                headers={"location": "https://example.test/callback?code=auth-code"},
            ),
        ]
    )
    client._session.post = AsyncMock(side_effect=[FakeResponse(status=200), FakeResponse(status=200, json_data={})])

    with pytest.raises(InvalidAuthError):
        await client._async_login()


async def test_parse_datetime_returns_localized_datetime() -> None:
    """Kreta timestamps should be parsed into timezone-aware datetimes."""
    client = _client()

    parsed = client._parse_datetime("2026-04-27T08:00:00Z")

    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# _summarize_error_body
# ---------------------------------------------------------------------------


def test_summarize_error_body_collapses_html_doctype() -> None:
    """HTML pages starting with <!DOCTYPE should be summarised."""
    assert _summarize_error_body("<!DOCTYPE html><html><body>maintenance</body></html>") == "(HTML response)"


def test_summarize_error_body_collapses_html_tag() -> None:
    """HTML pages starting with <html should be summarised."""
    assert _summarize_error_body("<html><body>error</body></html>") == "(HTML response)"


def test_summarize_error_body_collapses_html_with_bom() -> None:
    """BOM prefix before HTML should still be detected as HTML."""
    body = "\ufeff<!DOCTYPE html><html></html>"
    assert _summarize_error_body(body) == "(HTML response)"


def test_summarize_error_body_keeps_short_plain_text() -> None:
    """Short plain-text bodies should be kept verbatim."""
    assert _summarize_error_body("service unavailable") == "service unavailable"


def test_summarize_error_body_truncates_long_plain_text() -> None:
    """Plain-text bodies longer than the limit should be truncated with ellipsis."""
    long_body = "x" * 300
    result = _summarize_error_body(long_body)
    assert result.endswith("…")
    assert len(result) < 300


async def test_async_request_html_error_body_is_summarised() -> None:
    """An HTML error response body must not appear verbatim in the exception message."""
    client = _client()
    client.async_authenticate = AsyncMock()
    client._session.request = AsyncMock(
        return_value=FakeResponse(
            status=503,
            text_data="<!DOCTYPE html><html><body>maintenance</body></html>",
        )
    )

    with pytest.raises(KretaApiError, match=r"\(HTML response\)"):
        await client._async_request("get", "https://example.test")


async def test_exchange_refresh_token_html_error_body_is_summarised() -> None:
    """HTML body in refresh-token 503 must not appear verbatim in the exception."""
    client = _client()
    client._session.post = AsyncMock(
        return_value=FakeResponse(
            status=503,
            text_data="<!DOCTYPE html><html><body>maintenance</body></html>",
        )
    )

    with pytest.raises(KretaApiError, match=r"\(HTML response\)"):
        await client._async_exchange_refresh_token("some-refresh-token")


# ---------------------------------------------------------------------------
# diagnostics — sanitization helpers
# ---------------------------------------------------------------------------

from custom_components.kreta.api.diagnostics import (
    AuthDiagnosticsTrace,
    sanitize_form_data,
    sanitize_redirect_url,
    sanitize_response_body,
)


def test_sanitize_form_data_redacts_sensitive_keys() -> None:
    """Sensitive request fields must be redacted; others pass through unchanged."""
    data = {
        "Password": "hunter2",
        "UserName": "student01",
        "InstituteCode": "school01",
        "refresh_token": "rt-secret",
        "__RequestVerificationToken": "csrf-secret",
        "code": "auth-code-secret",
        "code_verifier": "verifier-secret",
        "grant_type": "refresh_token",
    }
    result = sanitize_form_data(data)

    assert result["Password"] == "***"
    assert result["refresh_token"] == "***"
    assert result["__RequestVerificationToken"] == "***"
    assert result["code"] == "***"
    assert result["code_verifier"] == "***"
    assert result["UserName"] == "student01"
    assert result["InstituteCode"] == "school01"
    assert result["grant_type"] == "refresh_token"


def test_sanitize_form_data_case_insensitive() -> None:
    """Redaction must work regardless of field-name capitalisation."""
    result = sanitize_form_data({"PASSWORD": "secret", "REFRESH_TOKEN": "rt"})
    assert result["PASSWORD"] == "***"
    assert result["REFRESH_TOKEN"] == "***"


def test_sanitize_response_body_redacts_token_fields() -> None:
    """JSON responses must have access_token, refresh_token and id_token redacted."""
    import json

    body = json.dumps({
        "access_token": "at-secret",
        "refresh_token": "rt-secret",
        "id_token": "it-secret",
        "expires_in": 3600,
        "token_type": "Bearer",
    })
    result = sanitize_response_body(body)
    parsed = json.loads(result)

    assert parsed["access_token"] == "***"
    assert parsed["refresh_token"] == "***"
    assert parsed["id_token"] == "***"
    assert parsed["expires_in"] == 3600
    assert parsed["token_type"] == "Bearer"


def test_sanitize_response_body_collapses_html() -> None:
    """HTML bodies must be collapsed to a short label."""
    assert sanitize_response_body("<!DOCTYPE html><html></html>") == "(HTML response)"
    assert sanitize_response_body("<html><body>err</body></html>") == "(HTML response)"


def test_sanitize_response_body_truncates_long_plain_text() -> None:
    """Plain-text bodies beyond the limit must be truncated."""
    long_body = "x" * 600
    result = sanitize_response_body(long_body)
    assert result.endswith("…")
    assert len(result) < 600


def test_sanitize_redirect_url_redacts_code_and_nonce() -> None:
    """Authorization code and nonce must be redacted from redirect URLs."""
    url = (
        "https://mobil.e-kreta.hu/oauthredirect"
        "?code=supersecretcode&state=kreten_student_mobile"
    )
    result = sanitize_redirect_url(url)
    assert "supersecretcode" not in result
    assert "code=***" in result
    assert "state=kreten_student_mobile" in result


def test_sanitize_redirect_url_passthrough_when_no_sensitive_params() -> None:
    """URLs with no sensitive params must be returned unchanged."""
    url = "https://example.test/callback?state=ok"
    assert sanitize_redirect_url(url) == url


# ---------------------------------------------------------------------------
# diagnostics — AuthDiagnosticsTrace formatting
# ---------------------------------------------------------------------------


def test_auth_trace_formats_all_fields() -> None:
    """log_failure output must include all recorded step fields."""
    import logging

    trace = AuthDiagnosticsTrace()
    trace.record_exchange(
        label="POST token (refresh)",
        method="POST",
        url="https://idp.example.test/connect/token",
        request_data={"grant_type": "refresh_token", "refresh_token": "rt-secret"},
        response_status=400,
        response_body='{"error": "invalid_grant"}',
    )

    logged_lines: list[str] = []

    class _CapLogger(logging.Logger):
        def warning(self, msg, *args, **kwargs):
            logged_lines.append(msg % args if args else msg)

    trace.log_failure(_CapLogger("test"), "school01")

    output = "\n".join(logged_lines)
    assert "Auth failure HTTP trace for school01" in output
    assert "POST token (refresh)" in output
    assert "POST" in output
    assert "https://idp.example.test/connect/token" in output
    assert "HTTP 400" in output
    assert "invalid_grant" in output
    # Secret must NOT appear
    assert "rt-secret" not in output


def test_auth_trace_records_network_error() -> None:
    """Network errors must appear in the trace output."""
    import logging

    trace = AuthDiagnosticsTrace()
    trace.record_exchange(
        label="POST token (refresh)",
        method="POST",
        url="https://idp.example.test/connect/token",
        network_error="Connection refused",
    )

    logged_lines: list[str] = []

    class _CapLogger(logging.Logger):
        def warning(self, msg, *args, **kwargs):
            logged_lines.append(msg % args if args else msg)

    trace.log_failure(_CapLogger("test"), "school01")
    output = "\n".join(logged_lines)
    assert "Connection refused" in output


# ---------------------------------------------------------------------------
# diagnostics — refresh token exchange
# ---------------------------------------------------------------------------


async def test_exchange_refresh_token_logs_trace_on_rejection() -> None:
    """A 401 rejection must emit a WARNING with the full HTTP trace."""
    client = _client()
    client._session.post = AsyncMock(
        return_value=FakeResponse(status=401, text_data='{"error":"invalid_grant"}')
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(InvalidAuthError):
            await client._async_exchange_refresh_token("my-refresh-token")

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert "POST" in logged_msg
    assert "HTTP 401" in logged_msg
    assert "invalid_grant" in logged_msg
    # Secrets must NOT appear in the logged output
    assert "my-refresh-token" not in logged_msg


async def test_exchange_refresh_token_logs_trace_on_network_error() -> None:
    """A transport failure must emit a WARNING trace with the error message."""
    client = _client()
    client._session.post = AsyncMock(side_effect=ClientError("connection refused"))

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(CannotConnectError):
            await client._async_exchange_refresh_token("my-refresh-token")

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert "connection refused" in logged_msg
    assert "my-refresh-token" not in logged_msg


async def test_exchange_refresh_token_no_trace_on_success() -> None:
    """A successful token exchange must NOT emit a diagnostic WARNING."""
    client = _client()
    client._session.post = AsyncMock(
        return_value=FakeResponse(
            status=200,
            json_data={"access_token": "access", "refresh_token": "new-refresh"},
        )
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        await client._async_exchange_refresh_token("old-refresh")

    for call in mock_logger.warning.call_args_list:
        assert "Auth failure HTTP trace" not in str(call)


# ---------------------------------------------------------------------------
# diagnostics — full login flow
# ---------------------------------------------------------------------------


def _login_ok_get_side_effects() -> list:
    """Return the standard two successful GET responses for _async_login."""
    return [
        FakeResponse(
            status=200,
            text_data='<input name="__RequestVerificationToken" type="hidden" value="csrf">',
        ),
        FakeResponse(
            status=302,
            headers={"location": "https://mobil.e-kreta.hu/oauthredirect?code=auth-code"},
        ),
    ]


async def test_login_logs_trace_on_authorize_page_failure() -> None:
    """A failing authorize GET must emit a WARNING trace."""
    client = _client()
    client._session.get = AsyncMock(
        return_value=FakeResponse(status=503, text_data="maintenance")
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(InvalidAuthError):
            await client._async_login()

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert "HTTP 503" in logged_msg
    assert client._password not in logged_msg


async def test_login_logs_trace_on_login_form_failure() -> None:
    """A failing login form POST must emit a WARNING trace."""
    client = _client()
    client._session.get = AsyncMock(
        return_value=FakeResponse(
            status=200,
            text_data='<input name="__RequestVerificationToken" type="hidden" value="csrf">',
        )
    )
    client._session.post = AsyncMock(
        return_value=FakeResponse(status=401, text_data='{"error":"invalid_credentials"}')
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(InvalidAuthError):
            await client._async_login()

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert "HTTP 401" in logged_msg
    assert "invalid_credentials" in logged_msg
    assert client._password not in logged_msg
    assert "csrf" not in logged_msg


async def test_login_logs_trace_on_callback_not_redirecting() -> None:
    """A non-redirect callback response must emit a WARNING trace."""
    client = _client()
    client._session.get = AsyncMock(
        side_effect=[
            FakeResponse(
                status=200,
                text_data='<input name="__RequestVerificationToken" type="hidden" value="csrf">',
            ),
            FakeResponse(status=200, text_data="not a redirect"),
        ]
    )
    client._session.post = AsyncMock(return_value=FakeResponse(status=200))

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(InvalidAuthError):
            await client._async_login()

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert client._password not in logged_msg


async def test_login_logs_trace_on_token_exchange_failure() -> None:
    """A failed authorization-code token exchange must emit a WARNING trace."""
    client = _client()
    client._session.get = AsyncMock(side_effect=_login_ok_get_side_effects())
    client._session.post = AsyncMock(
        side_effect=[
            FakeResponse(status=200),
            FakeResponse(status=400, text_data='{"error":"invalid_code"}'),
        ]
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(InvalidAuthError):
            await client._async_login()

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert "HTTP 400" in logged_msg
    assert "invalid_code" in logged_msg
    # Auth code and password must not appear in the trace
    assert "auth-code" not in logged_msg
    assert client._password not in logged_msg


async def test_login_logs_trace_on_network_error() -> None:
    """A transport error during login must emit a WARNING trace."""
    client = _client()
    client._session.get = AsyncMock(side_effect=ClientError("timeout"))

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        with pytest.raises(CannotConnectError):
            await client._async_login()

    assert mock_logger.warning.called
    logged_msg = mock_logger.warning.call_args[0][1]
    assert "Auth failure HTTP trace" in logged_msg
    assert "timeout" in logged_msg


async def test_login_no_trace_on_success() -> None:
    """A successful login flow must NOT emit a diagnostic WARNING trace."""
    client = _client()
    client._session.get = AsyncMock(side_effect=_login_ok_get_side_effects())
    client._session.post = AsyncMock(
        side_effect=[
            FakeResponse(status=200),
            FakeResponse(
                status=200,
                json_data={"access_token": "at", "refresh_token": "rt"},
            ),
        ]
    )

    with patch("custom_components.kreta.api.client._LOGGER") as mock_logger:
        await client._async_login()

    for call in mock_logger.warning.call_args_list:
        assert "Auth failure HTTP trace" not in str(call)
