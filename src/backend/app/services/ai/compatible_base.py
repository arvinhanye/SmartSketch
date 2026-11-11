"""Internal compatible_base responsibilities; public compatibility entry: app.services.ai.compatible."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit
from .client import ModelCallError, ModelConnectionError, ModelTimeoutError, Usage
from app.services.ai.compatible_protocol import (
    MAX_ERROR_BODY_BYTES,
    _Fail,
    _READ_SIZE,
    _TRANSPORT_ERRORS,
    _error_for_status,
    _loads,
    _malformed,
    _parse_retry_after,
    _parse_usage,
)
from app.services.ai.compatible_transport import (
    HttpResponse,
    HttpTransport,
    StdlibTransport,
)

# ---------------------------------------------------------------- shared HTTP plumbing


class _CompatibleHttpClient:
    """Key and URL checks, POST, deadline-bounded reads and HTTP error classification.

    Shared by the chat and embeddings clients so that both classify failures and guard
    the key identically. Subclasses name their endpoint with ``_path``.
    """

    _path: str = ""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: HttpTransport | None,
        default_timeout_seconds: float,
        max_response_bytes: int,
        clock: Callable[[], float],
    ) -> None:
        owner = type(self).__name__
        self._url = _endpoint_url(base_url, self._path, owner)
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        # Printable ASCII without spaces: anything else cannot go into an HTTP header safely,
        # and http.client would echo the key inside its UnicodeEncodeError.
        if not isinstance(api_key, str) or not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
            raise ValueError(f"{owner}: api_key must be non-empty printable ASCII without spaces")
        if (
            isinstance(default_timeout_seconds, bool)
            or not isinstance(default_timeout_seconds, int | float)
            or not math.isfinite(default_timeout_seconds)
            or default_timeout_seconds <= 0
        ):
            raise ValueError(f"{owner}: default_timeout_seconds must be a finite number > 0")
        if type(max_response_bytes) is not int or max_response_bytes < 1:
            raise ValueError(f"{owner}: max_response_bytes must be an int >= 1")
        self._api_key = api_key
        self._transport: HttpTransport = transport if transport is not None else StdlibTransport()
        self._default_timeout = float(default_timeout_seconds)
        self._max_bytes = max_response_bytes
        self._clock = clock

    def __repr__(self) -> str:
        return f"{type(self).__name__}(url={self._url!r})"

    def _usage_from(self, value: object) -> Usage | None:
        """How this endpoint reports usage (also read from error bodies)."""

        return _parse_usage(value)

    def _post(self, payload: dict[str, Any], model: str, timeout: float, *, accept: str) -> tuple[HttpResponse, float]:
        """Send one POST; returns the response and the absolute deadline."""

        deadline = self._clock() + timeout
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
        }
        try:
            response = self._transport.open(self._url, body, headers, timeout)
        except TimeoutError:
            raise _Fail(ModelTimeoutError(model)) from None
        except _TRANSPORT_ERRORS:
            raise _Fail(ModelConnectionError(model)) from None
        return response, deadline

    def _read(self, response: HttpResponse, deadline: float, model: str, *, on_break: type[ModelCallError]) -> bytes:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise _Fail(ModelTimeoutError(model))
        try:
            data = response.read(_READ_SIZE, remaining)
        except TimeoutError:
            raise _Fail(ModelTimeoutError(model)) from None
        except _TRANSPORT_ERRORS:
            raise _Fail(on_break(model)) from None
        if self._clock() >= deadline:
            raise _Fail(ModelTimeoutError(model))
        return data

    def _raise_for_status(self, response: HttpResponse, deadline: float, model: str) -> None:
        """Raise the classified error for any status that is not a 2xx."""

        status = response.status
        if 200 <= status <= 299:
            return
        if not 400 <= status <= 599:
            raise _Fail(_malformed(model, status))
        body = bytearray()
        try:
            while len(body) < MAX_ERROR_BODY_BYTES:
                data = self._read(response, deadline, model, on_break=ModelConnectionError)
                if not data:
                    break
                body.extend(data)
        except _Fail:
            body = bytearray()
        usage = None
        if len(body) <= MAX_ERROR_BODY_BYTES:
            try:
                parsed = _loads(bytes(body).decode("utf-8"))
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                usage = self._usage_from(parsed.get("usage"))
        retry_after = _parse_retry_after(response.header("Retry-After")) if status == 429 else None
        raise _Fail(_error_for_status(model, status, usage, retry_after))

    def _read_json(self, response: HttpResponse, deadline: float, model: str) -> tuple[dict[str, Any], int]:
        """Classify the status, read the whole (bounded) body and parse it as a JSON object.

        Always closes ``response``. Returns the object and the HTTP status.
        """

        try:
            self._raise_for_status(response, deadline, model)
            status = response.status
            body = bytearray()
            while True:
                data = self._read(response, deadline, model, on_break=ModelConnectionError)
                if not data:
                    break
                body.extend(data)
                if len(body) > self._max_bytes:
                    raise _Fail(_malformed(model, status))
        finally:
            response.close()
        try:
            parsed = _loads(bytes(body).decode("utf-8"))
        except ValueError:  # includes UnicodeDecodeError and JSONDecodeError
            parsed = None
        if not isinstance(parsed, dict):
            raise _Fail(_malformed(model, status))
        return parsed, status


def _endpoint_url(base_url: object, path: str, owner: str) -> str:
    error = ValueError(f"{owner}: base_url must be an http(s) URL without credentials, query or fragment")
    if not isinstance(base_url, str) or not base_url or any(c.isspace() or ord(c) < 32 for c in base_url):
        raise error
    try:
        parts = urlsplit(base_url)
        port = parts.port
    except ValueError:
        raise error from None
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or port == 0
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or base_url.endswith(("?", "#"))
    ):
        raise error
    return base_url.rstrip("/") + path
