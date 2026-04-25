"""Async client for the Kreta API."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponse, ClientSession
from homeassistant.util import dt as dt_util

from ..const import DEFAULT_TIMEOUT_SECONDS
from .auth import extract_authorization_code, extract_request_verification_token
from .exceptions import ApiResponseError, CannotConnectError, InvalidAuthError, KretaApiError
from .models import AnnouncedTest, MergedCalendarEvent, StudentProfile
from .storage import TokenStore

_LOGGER = logging.getLogger(__name__)
KRETA_TIMEZONE = ZoneInfo("Europe/Budapest")
_ERROR_BODY_MAX_LENGTH = 200


def _summarize_error_body(body: str) -> str:
    """Return a concise summary of an HTTP error response body.

    HTML pages (e.g. maintenance splash screens) are collapsed to a short
    label so they don't flood the HA UI with raw markup.  Plain-text bodies
    are kept verbatim up to _ERROR_BODY_MAX_LENGTH characters.
    """
    stripped = body.lstrip("\ufeff").lstrip()
    if stripped.lower().startswith(("<!doctype", "<html")):
        return "(HTML response)"
    if len(body) <= _ERROR_BODY_MAX_LENGTH:
        return body
    return body[:_ERROR_BODY_MAX_LENGTH] + "…"

AUTHORIZE_PATH = (
    "/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize%2Fcallback%3Fprompt%3Dlogin"
    "%26nonce%3DwylCrqT4oN6PPgQn2yQB0euKei9nJeZ6_ffJ-VpSKZU%26response_type%3Dcode"
    "%26code_challenge_method%3DS256%26scope%3Dopenid%2520email%2520offline_access"
    "%2520kreta-ellenorzo-webapi.public%2520kreta-eugyintezes-webapi.public"
    "%2520kreta-fileservice-webapi.public%2520kreta-mobile-global-webapi.public"
    "%2520kreta-dkt-webapi.public%2520kreta-ier-webapi.public%26code_challenge"
    "%3DHByZRRnPGb-Ko_wTI7ibIba1HQ6lor0ws4bcgReuYSQ%26redirect_uri%3Dhttps%253A"
    "%252F%252Fmobil.e-kreta.hu%252Fellenorzo-student%252Fprod%252Foauthredirect"
    "%26client_id%3Dkreta-ellenorzo-student-mobile-ios%26state%3Dkreten_student_mobile"
    "%26suppressed_prompt%3Dlogin"
)
CALLBACK_QUERY = (
    "prompt=login&nonce=wylCrqT4oN6PPgQn2yQB0euKei9nJeZ6_ffJ-VpSKZU&response_type=code"
    "&code_challenge_method=S256&scope=openid%20email%20offline_access"
    "%20kreta-ellenorzo-webapi.public%20kreta-eugyintezes-webapi.public"
    "%20kreta-fileservice-webapi.public%20kreta-mobile-global-webapi.public"
    "%20kreta-dkt-webapi.public%20kreta-ier-webapi.public&code_challenge"
    "=HByZRRnPGb-Ko_wTI7ibIba1HQ6lor0ws4bcgReuYSQ&redirect_uri=https%3A%2F%2Fmobil.e-kreta.hu"
    "%2Fellenorzo-student%2Fprod%2Foauthredirect&client_id=kreta-ellenorzo-student-mobile-ios"
    "&state=kreten_student_mobile&suppressed_prompt=login"
)
LOGIN_RETURN_URL = (
    "/connect/authorize/callback?prompt=login&nonce=wylCrqT4oN6PPgQn2yQB0euKei9nJeZ6_ffJ-VpSKZU"
    "&response_type=code&code_challenge_method=S256&scope=openid%20email%20offline_access"
    "%20kreta-ellenorzo-webapi.public%20kreta-eugyintezes-webapi.public"
    "%20kreta-fileservice-webapi.public%20kreta-mobile-global-webapi.public"
    "%20kreta-dkt-webapi.public%20kreta-ier-webapi.public&code_challenge"
    "=HByZRRnPGb-Ko_wTI7ibIba1HQ6lor0ws4bcgReuYSQ&redirect_uri=https%3A%2F%2Fmobil.e-kreta.hu"
    "%2Fellenorzo-student%2Fprod%2Foauthredirect&client_id=kreta-ellenorzo-student-mobile-ios"
    "&state=kreten_student_mobile&suppressed_prompt=login"
)
TOKEN_URL = "https://idp.e-kreta.hu/connect/token"
AUTHORIZE_URL = f"https://idp.e-kreta.hu{AUTHORIZE_PATH}"
CALLBACK_URL = f"https://idp.e-kreta.hu/connect/authorize/callback?{CALLBACK_QUERY}"
LOGIN_URL = "https://idp.e-kreta.hu/account/login"
CLIENT_ID = "kreta-ellenorzo-student-mobile-ios"
CODE_VERIFIER = "DSpuqj_HhDX4wzQIbtn8lr8NLE5wEi1iVLMtMK0jY6c"


class KretaApiClient:
    """Kreta API client with refresh-token persistence."""

    def __init__(
        self,
        *,
        session: ClientSession,
        klik_id: str,
        user_id: str,
        password: str,
        token_store: TokenStore,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._klik_id = klik_id
        self._user_id = user_id
        self._password = password
        self._token_store = token_store
        self._access_token: str | None = None
        self._auth_lock = asyncio.Lock()

    @property
    def _api_base_url(self) -> str:
        """Return the Kreta API base URL for this institute."""
        return f"https://{self._klik_id}.e-kreta.hu/ellenorzo/v3"

    async def async_authenticate(self, force_login: bool = False) -> None:
        """Authenticate using refresh token first, then interactive login if needed."""
        async with self._auth_lock:
            if self._access_token and not force_login:
                return

            refresh_token = await self._token_store.async_get_refresh_token()
            if refresh_token and not force_login:
                _LOGGER.info("Authenticating with Kreta using stored refresh token")
                try:
                    await self._async_exchange_refresh_token(refresh_token)
                    _LOGGER.info("Kreta authentication successful (refresh token)")
                    return
                except InvalidAuthError:
                    _LOGGER.debug("Stored refresh token rejected, falling back to login")

            _LOGGER.info("Performing full Kreta login for %s", self._klik_id)
            await self._async_login()
            _LOGGER.info("Kreta authentication successful (full login)")

    async def async_reauthenticate(self) -> None:
        """Reauthenticate explicitly after an auth failure."""
        async with self._auth_lock:
            self._access_token = None
        await self.async_authenticate(force_login=True)

    async def async_get_student_profile(self) -> StudentProfile:
        """Fetch the pupil profile."""
        payload = await self._async_get_json("Sajat/TanuloAdatlap")
        birth_date = payload.get("SzuletesiDatum")
        return StudentProfile(
            student_name=payload.get("Nev"),
            birth_name=payload.get("SzuletesiNev"),
            birth_place=payload.get("SzuletesiHely"),
            mother_name=payload.get("AnyjaNeve"),
            phone_number=payload.get("Telefonszam"),
            email=payload.get("EmailCim"),
            school_name=payload.get("Intezmeny", {}).get("TeljesNev"),
            birth_date=birth_date.split("T", 1)[0] if birth_date else None,
        )

    async def async_get_lessons(
        self, start_date: date, end_date: date
    ) -> list[MergedCalendarEvent]:
        """Fetch timetable entries and normalize them to lesson events."""
        payload = await self._async_get_json(
            "Sajat/OrarendElemek",
            params={"datumTol": start_date.isoformat(), "datumIg": end_date.isoformat()},
        )
        lessons: list[MergedCalendarEvent] = []
        for item in payload:
            lesson_type = item.get("Tipus", {}).get("Nev")
            if lesson_type not in {"TanitasiOra", "OrarendiOra"}:
                continue
            start = self._parse_datetime(item["KezdetIdopont"])
            end = self._parse_datetime(item["VegIdopont"])
            subject = item.get("Nev") or item.get("Tantargy", {}).get("Nev") or "Ora"
            room = item.get("TeremNeve")
            lesson_index = item.get("Oraszam")
            description = "\n".join(
                part
                for part in (
                    f"Tantargy: {subject}",
                    f"Terem: {room}" if room else None,
                    f"Oraszam: {lesson_index}" if lesson_index is not None else None,
                )
                if part
            )
            lessons.append(
                MergedCalendarEvent(
                    uid=f"lesson-{start.isoformat()}-{lesson_index or 0}-{subject.casefold()}",
                    start=start,
                    end=end,
                    summary=subject,
                    description=description,
                    location=room,
                    lesson_index=lesson_index,
                    subject_name=subject,
                    exam=None,
                    source="lesson",
                )
            )
        lessons.sort(key=lambda lesson: (lesson.start, lesson.lesson_index or 0, lesson.uid))
        return lessons

    async def async_get_announced_tests(
        self, start_date: date, end_date: date
    ) -> list[AnnouncedTest]:
        """Fetch announced tests, splitting into month-sized chunks when needed."""
        tests: list[AnnouncedTest] = []
        chunk_start = start_date
        while chunk_start <= end_date:
            month_later = (chunk_start.replace(day=1) + timedelta(days=32)).replace(day=1)
            chunk_end = min(month_later - timedelta(days=1), end_date)
            payload = await self._async_get_json(
                "Sajat/BejelentettSzamonkeresek",
                params={
                    "datumTol": chunk_start.isoformat(),
                    "datumIg": chunk_end.isoformat(),
                },
            )
            for item in payload:
                announced_date = item.get("BejelentesDatuma")
                tests.append(
                    AnnouncedTest(
                        test_date=self._parse_local_date(item["Datum"]),
                        announced_date=(
                            self._parse_local_date(announced_date)
                            if announced_date
                            else None
                        ),
                        subject_name=item.get("TantargyNeve") or "Ismeretlen tantargy",
                        teacher_name=item.get("RogzitoTanarNeve"),
                        lesson_index=item.get("OrarendiOraOraszama"),
                        theme=item.get("Temaja"),
                        mode=item.get("Modja", {}).get("Leiras"),
                    )
                )
            chunk_start = chunk_end + timedelta(days=1)
        tests.sort(key=lambda item: (item.test_date, item.lesson_index or 0, item.subject_name))
        return tests

    async def _async_get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Issue an authenticated GET request and return JSON."""
        response = await self._async_request("get", f"{self._api_base_url}/{path}", params=params)
        try:
            return await response.json()
        except (ClientError, ValueError) as err:
            raise ApiResponseError(f"Invalid JSON received from {path}") from err

    async def _async_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        retry_on_auth_error: bool = True,
        require_auth: bool = True,
    ) -> ClientResponse:
        """Make an HTTP request with auth handling."""
        if require_auth:
            await self.async_authenticate()
        request_headers = dict(headers or {})
        if require_auth and self._access_token is not None:
            request_headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            response = await self._session.request(
                method,
                url,
                params=params,
                data=data,
                headers=request_headers,
                allow_redirects=allow_redirects,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except ClientError as err:
            raise CannotConnectError(f"Could not reach Kreta endpoint {url}") from err

        if response.status in {401, 403}:
            response.release()
            if retry_on_auth_error:
                await self.async_reauthenticate()
                return await self._async_request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    allow_redirects=allow_redirects,
                    retry_on_auth_error=False,
                    require_auth=require_auth,
                )
            raise InvalidAuthError(f"Kreta request rejected for {url}")

        if response.status >= 400:
            body = await response.text()
            _LOGGER.debug("Full error response body for %s: %s", url, body)
            raise KretaApiError(
                f"Kreta request failed ({response.status}) for {url}: {_summarize_error_body(body)}"
            )
        return response

    async def _async_exchange_refresh_token(self, refresh_token: str) -> None:
        """Refresh the access token from a stored refresh token."""
        try:
            response = await self._session.post(
                TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "institute_code": self._klik_id,
                    "client_id": CLIENT_ID,
                    "grant_type": "refresh_token",
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except ClientError as err:
            raise CannotConnectError("Could not refresh the Kreta access token") from err

        if response.status in {400, 401, 403}:
            raise InvalidAuthError("Stored refresh token is no longer valid")
        if response.status >= 400:
            body = await response.text()
            _LOGGER.debug("Full error response body for token exchange: %s", body)
            raise KretaApiError(
                f"Refresh-token exchange failed ({response.status}): {_summarize_error_body(body)}"
            )

        payload = await response.json()
        if "access_token" not in payload:
            raise InvalidAuthError("Refresh-token exchange did not return an access token")
        self._access_token = payload["access_token"]
        await self._token_store.async_set_refresh_token(payload.get("refresh_token"))

    async def _async_login(self) -> None:
        """Perform the interactive login flow to obtain a new refresh token."""
        try:
            login_page = await self._session.get(AUTHORIZE_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
            login_page.raise_for_status()
            verification_token = extract_request_verification_token(await login_page.text())

            response = await self._session.post(
                LOGIN_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "ReturnUrl": LOGIN_RETURN_URL,
                    "IsTemporaryLogin": False,
                    "UserName": self._user_id,
                    "Password": self._password,
                    "InstituteCode": self._klik_id,
                    "loginType": "InstituteLogin",
                    "__RequestVerificationToken": verification_token,
                },
                allow_redirects=False,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if response.status >= 400:
                raise InvalidAuthError(f"Login form submission failed with {response.status}")

            callback = await self._session.get(
                CALLBACK_URL,
                allow_redirects=False,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if callback.status not in {302, 303}:
                raise InvalidAuthError(
                    f"Authorization callback did not redirect, got {callback.status}"
                )

            location = callback.headers.get("location")
            if location is None:
                raise InvalidAuthError("Authorization callback did not return a redirect URL")

            code = extract_authorization_code(location)
            token_response = await self._session.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "code_verifier": CODE_VERIFIER,
                    "redirect_uri": "https://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect",
                    "client_id": CLIENT_ID,
                    "grant_type": "authorization_code",
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if token_response.status >= 400:
                raise InvalidAuthError(
                    f"Authorization-code exchange failed with {token_response.status}"
                )
        except ClientError as err:
            raise CannotConnectError("Could not complete Kreta login flow") from err

        payload = await token_response.json()
        if "access_token" not in payload:
            raise InvalidAuthError("Login response did not include an access token")
        self._access_token = payload["access_token"]
        await self._token_store.async_set_refresh_token(payload.get("refresh_token"))

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """Parse a Kreta datetime string into a local timezone-aware datetime."""
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt_util.as_local(parsed)

    @staticmethod
    def _parse_local_date(value: str) -> date:
        """Parse a Kreta timestamp into the corresponding Hungary-local date."""
        if "T" not in value:
            return date.fromisoformat(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(KRETA_TIMEZONE).date()
