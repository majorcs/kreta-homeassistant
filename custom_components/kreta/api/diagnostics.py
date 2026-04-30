"""Auth-flow HTTP communication diagnostics for post-mortem investigation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse


_REDACTED = "***"

# Form fields whose values must never appear in diagnostic logs.
_SENSITIVE_REQUEST_FIELDS = frozenset({
    "password",
    "refresh_token",
    "code",
    "code_verifier",
    "__requestverificationtoken",
})

# JSON response keys whose values must never appear in diagnostic logs.
_SENSITIVE_RESPONSE_FIELDS = frozenset({"access_token", "refresh_token", "id_token"})

# URL query parameters that carry secret values.
_SENSITIVE_URL_PARAMS = frozenset({"code", "code_verifier", "nonce"})

_MAX_BODY_LENGTH = 500


def sanitize_form_data(data: dict[str, Any]) -> dict[str, str]:
    """Return a copy of form data with sensitive fields redacted.

    Matching is case-insensitive so ``Password`` and ``password`` are both
    caught.
    """
    return {
        k: _REDACTED if k.lower() in _SENSITIVE_REQUEST_FIELDS else str(v)
        for k, v in data.items()
    }


def sanitize_response_body(body: str) -> str:
    """Return a sanitized and truncated version of an HTTP response body.

    HTML pages are collapsed to a short label.  JSON bodies have known secret
    fields redacted.  All other content is truncated to ``_MAX_BODY_LENGTH``
    characters.
    """
    stripped = body.lstrip("\ufeff").lstrip()
    if stripped.lower().startswith(("<!doctype", "<html")):
        return "(HTML response)"
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            sanitized = {
                k: _REDACTED if k in _SENSITIVE_RESPONSE_FIELDS else v
                for k, v in obj.items()
            }
            return json.dumps(sanitized)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    if len(body) > _MAX_BODY_LENGTH:
        return body[:_MAX_BODY_LENGTH] + "…"
    return body


def sanitize_redirect_url(url: str) -> str:
    """Replace known secret query parameters in a redirect URL with ``***``."""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        params = parse_qs(parsed.query, keep_blank_values=True)
        sanitized_params = {
            k: [_REDACTED] if k in _SENSITIVE_URL_PARAMS else v
            for k, v in params.items()
        }
        new_query = urlencode(sanitized_params, doseq=True, quote_via=lambda *a: quote(a[0], safe="*"))
        return parsed._replace(query=new_query).geturl()
    except Exception:  # noqa: BLE001
        return "(sanitization error)"


@dataclass
class _TraceStep:
    label: str
    method: str
    url: str
    sanitized_request_data: dict[str, str] | None
    response_status: int | None
    response_body: str | None
    redirect_location: str | None
    network_error: str | None


class AuthDiagnosticsTrace:
    """Accumulates HTTP steps during an auth flow for post-mortem logging.

    Call :meth:`record_exchange` after each HTTP step.  If the overall auth
    attempt fails, call :meth:`log_failure` to emit a single ``WARNING`` log
    entry with all recorded steps.  On success the trace is silently discarded.
    """

    def __init__(self) -> None:
        """Initialize an empty trace."""
        self._steps: list[_TraceStep] = []

    def record_exchange(
        self,
        *,
        label: str,
        method: str,
        url: str,
        request_data: dict[str, Any] | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        redirect_location: str | None = None,
        network_error: str | None = None,
    ) -> None:
        """Record one HTTP request/response step.

        Sensitive values in *request_data*, *response_body*, and
        *redirect_location* are sanitized before storage.
        """
        self._steps.append(
            _TraceStep(
                label=label,
                method=method,
                url=url,
                sanitized_request_data=(
                    sanitize_form_data(request_data) if request_data else None
                ),
                response_status=response_status,
                response_body=(
                    sanitize_response_body(response_body) if response_body else None
                ),
                redirect_location=(
                    sanitize_redirect_url(redirect_location)
                    if redirect_location
                    else None
                ),
                network_error=network_error,
            )
        )

    def log_failure(self, logger: logging.Logger, context: str) -> None:
        """Emit a single WARNING log entry with all recorded steps."""
        lines = [f"Auth failure HTTP trace for {context}:"]
        for i, step in enumerate(self._steps, 1):
            lines.append(f"  [{i}] {step.label}")
            lines.append(f"      → {step.method.upper()} {step.url}")
            if step.sanitized_request_data:
                for k, v in step.sanitized_request_data.items():
                    lines.append(f"        {k}: {v}")
            if step.response_status is not None:
                lines.append(f"      ← HTTP {step.response_status}")
            if step.redirect_location:
                lines.append(f"        Location: {step.redirect_location}")
            if step.response_body:
                lines.append(f"        {step.response_body}")
            if step.network_error:
                lines.append(f"      ✗ Network error: {step.network_error}")
        logger.warning("%s", "\n".join(lines))
