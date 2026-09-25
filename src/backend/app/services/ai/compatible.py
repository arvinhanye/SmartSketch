"""OpenAI-compatible Chat Completions adapter (E03) implementing the E02 ``ModelClient``.

One request → one ``POST {base_url}/chat/completions``. Retries, fallback switching,
circuit breaking, budgets and ``model_calls`` bookkeeping belong to E04, which wraps
this adapter (docs/integrations.md「模型接入规则（A07）」).

Protocol (OpenAI Chat Completions, as published in ``openai/openai-openapi``; see
docs/handoffs/claude-e03.md for sources and provider differences):

- Body: ``model``, ``messages`` (``role``/``content``), the output ceiling as
  ``max_tokens`` (or ``max_completion_tokens``, per constructor), ``stream``;
  ``response_format = {"type": "json_object"}`` in JSON mode; streaming requests add
  ``stream_options = {"include_usage": true}`` (ADR-011 修订 3). No sampling parameters
  are sent: none are specified (E02 handoff, open item 3).
- Response: ``choices[0].message.content`` and ``finish_reason``, ``model`` and
  ``usage.prompt_tokens`` / ``usage.completion_tokens``. Missing or unparseable usage
  is ``None`` (E04 then bills the estimate), never a failure.
- Stream: server-sent events, ``data: <chunk JSON>`` per event, ending with
  ``data: [DONE]``. Content comes from ``choices[0].delta.content``; usage from the last
  chunk that carries a parseable ``usage`` (OpenAI sends it in a final chunk with empty
  ``choices``).

Error mapping onto the E02 classes (docs/integrations.md「调用记录」第 5 条):

- ``408`` → timeout; ``429`` → rate_limited (``Retry-After`` delta-seconds kept);
  ``401``/``403`` → auth; other ``4xx`` → invalid_request; ``5xx`` → server. The
  ``400/401/403/404/413/422/429`` set is ``rejected_before_generation`` by construction.
  Usage in an error body is attached to the error.
- Client-side timeout (socket timeout or the request's overall deadline) → timeout.
- Connection problems before a complete non-stream response → connection.
- After a stream has opened with ``200``: end of body before ``[DONE]``, a reset or an
  ``error`` event → stream_interrupted (timeouts stay timeout).
- Anything that cannot be parsed at the protocol level (not JSON, wrong structure, a
  ``finish_reason`` other than ``stop``/``length``, ``1xx``/``2xx`` other than a
  parseable ``200``/``3xx``, oversized body) → malformed_response with the HTTP status.

Nothing here logs. Errors are raised ``from None`` and carry only the model ID, status,
usage and ``Retry-After``: never the key, prompt text, model output or response body.
"""

from __future__ import annotations

import http.client
import json
import math
import socket
import ssl
import time
from collections.abc import Callable, Generator, Iterator, Mapping
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol
from urllib.parse import urlsplit

from .client import (
    FINISH_REASONS,
    FinishReason,
    ModelAuthError,
    ModelCallError,
    ModelConnectionError,
    ModelInvalidRequestError,
    ModelMalformedResponseError,
    ModelRateLimitedError,
    ModelRequest,
    ModelResult,
    ModelServerError,
    ModelStreamInterruptedError,
    ModelTimeoutError,
    StreamDelta,
    StreamDone,
    StreamEvent,
    Usage,
)

if TYPE_CHECKING:
    from app.config import Settings

# ---------------------------------------------------------------- input estimate

# docs/integrations.md「调用记录」第 4 条: E03 picks a local method that may only err high.
# Byte-level BPE tokenizers (OpenAI, DeepSeek, Qwen) never emit more tokens than the
# UTF-8 bytes they cover, so bytes bound each content from above. The overheads cover
# chat-template tokens around each message (role markers, separators) and the reply
# priming; they are deliberately generous. Hidden provider-side system prompts are not
# covered (docs/handoffs/claude-e03.md, 需实测).
MESSAGE_OVERHEAD_TOKENS: Final = 16
REQUEST_OVERHEAD_TOKENS: Final = 32


def estimate_input_tokens(request: ModelRequest) -> int:
    """Upper-bound estimate of the prompt tokens of ``request`` (for the ``model_calls`` pre-write)."""

    if not isinstance(request, ModelRequest):
        raise TypeError("request must be a ModelRequest")
    total = REQUEST_OVERHEAD_TOKENS
    for message in request.messages:
        total += len(message.content.encode("utf-8")) + len(message.role) + MESSAGE_OVERHEAD_TOKENS
    return total


# ---------------------------------------------------------------- transport


class HttpResponse(Protocol):
    """An open HTTP response. ``read`` returns ``b""`` at end of body."""

    status: int

    def header(self, name: str) -> str | None: ...

    def read(self, amount: int, timeout: float) -> bytes: ...

    def close(self) -> None: ...


class HttpTransport(Protocol):
    """Sends one POST and returns once the status line and headers have arrived.

    Implementations raise ``TimeoutError`` (``socket.timeout``) on timeouts and
    ``OSError`` or ``http.client.HTTPException`` on connection problems, both from
    ``open`` and from ``HttpResponse.read``.
    """

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResponse: ...


class _StdlibResponse:
    def __init__(self, connection: http.client.HTTPConnection, sock: socket.socket | None,
                 response: http.client.HTTPResponse) -> None:
        self._connection = connection
        self._sock = sock
        self._response = response
        self.status = response.status

    def header(self, name: str) -> str | None:
        return self._response.getheader(name)

    def read(self, amount: int, timeout: float) -> bytes:
        if self._sock is not None:
            self._sock.settimeout(max(timeout, 0.001))
        return self._response.read1(amount)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()


class StdlibTransport:
    """Default transport on ``http.client`` (no third-party runtime dependency)."""

    def __init__(self, ssl_context: ssl.SSLContext | None = None) -> None:
        self._ssl_context = ssl_context

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        parts = urlsplit(url)
        host = parts.hostname or ""
        connection: http.client.HTTPConnection
        if parts.scheme == "https":
            context = self._ssl_context or ssl.create_default_context()
            connection = http.client.HTTPSConnection(host, parts.port, timeout=timeout, context=context)
        else:
            connection = http.client.HTTPConnection(host, parts.port, timeout=timeout)
        try:
            connection.request("POST", parts.path or "/", body=body, headers=dict(headers))
            sock = connection.sock
            response = connection.getresponse()
        except BaseException:
            connection.close()
            raise
        return _StdlibResponse(connection, sock, response)


# ---------------------------------------------------------------- parsing helpers

_TRANSPORT_ERRORS = (OSError, http.client.HTTPException)
_READ_SIZE: Final = 64 * 1024
MAX_ERROR_BODY_BYTES: Final = 64 * 1024
DEFAULT_MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
MAX_TOKENS_FIELDS: Final = frozenset({"max_tokens", "max_completion_tokens"})


def _is_count(value: object) -> bool:
    return type(value) is int and value >= 0


def _parse_usage(value: object) -> Usage | None:
    if not isinstance(value, dict):
        return None
    prompt = value.get("prompt_tokens")
    completion = value.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    if not _is_count(prompt) or not _is_count(completion):  # also rejects bool
        return None
    return Usage(prompt, completion)


def _parse_model(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _parse_retry_after(value: str | None) -> float | None:
    """Delta-seconds only; an HTTP-date is ignored (docs/handoffs/claude-e03.md)."""

    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _loads(data: bytes | str) -> Any:
    def reject_constant(name: str) -> Any:
        raise ValueError(name)

    return json.loads(data, parse_constant=reject_constant)


def _error_for_status(model: str, status: int, usage: Usage | None, retry_after: float | None) -> ModelCallError:
    if status == 408:
        return ModelTimeoutError(model, status_code=status, usage=usage)
    if status == 429:
        return ModelRateLimitedError(model, status_code=status, usage=usage, retry_after_seconds=retry_after)
    if status in (401, 403):
        return ModelAuthError(model, status_code=status, usage=usage)
    if 400 <= status <= 499:
        return ModelInvalidRequestError(model, status_code=status, usage=usage)
    if 500 <= status <= 599:
        return ModelServerError(model, status_code=status, usage=usage)
    return _malformed(model, status, usage)


def _malformed(model: str, status: int | None, usage: Usage | None = None) -> ModelMalformedResponseError:
    if status is not None and not 100 <= status <= 599:
        status = None
    return ModelMalformedResponseError(model, status_code=status, usage=usage)


class _Fail(Exception):
    """Internal carrier so that the public error is raised outside every ``except`` block."""

    def __init__(self, error: ModelCallError) -> None:
        self.error = error


def _finish(value: object) -> FinishReason | None:
    return value if isinstance(value, str) and value in FINISH_REASONS else None  # type: ignore[return-value]


# ---------------------------------------------------------------- adapter


class CompatibleModelClient:
    """``ModelClient`` for one OpenAI-compatible provider (base URL + key); model per request."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: HttpTransport | None = None,
        default_timeout_seconds: float = 60.0,
        max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens",
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = _chat_url(base_url)
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        # Printable ASCII without spaces: anything else cannot go into an HTTP header safely,
        # and http.client would echo the key inside its UnicodeEncodeError.
        if not isinstance(api_key, str) or not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
            raise ValueError("CompatibleModelClient: api_key must be non-empty printable ASCII without spaces")
        if (
            isinstance(default_timeout_seconds, bool)
            or not isinstance(default_timeout_seconds, int | float)
            or not math.isfinite(default_timeout_seconds)
            or default_timeout_seconds <= 0
        ):
            raise ValueError("CompatibleModelClient: default_timeout_seconds must be a finite number > 0")
        if max_tokens_field not in MAX_TOKENS_FIELDS:
            raise ValueError(f"CompatibleModelClient: max_tokens_field must be one of {sorted(MAX_TOKENS_FIELDS)}")
        if type(max_response_bytes) is not int or max_response_bytes < 1:
            raise ValueError("CompatibleModelClient: max_response_bytes must be an int >= 1")
        self._api_key = api_key
        self._transport: HttpTransport = transport if transport is not None else StdlibTransport()
        self._default_timeout = float(default_timeout_seconds)
        self._max_tokens_field = max_tokens_field
        self._max_bytes = max_response_bytes
        self._clock = clock

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        role: Literal["primary", "fallback"] = "primary",
        transport: HttpTransport | None = None,
    ) -> CompatibleModelClient:
        """Primary or fallback provider from ``LLM_*`` settings; timeout = ``LLM_REQUEST_TIMEOUT_SECONDS``."""

        if role == "primary":
            url_name, key_name = "LLM_BASE_URL", "LLM_API_KEY"
        elif role == "fallback":
            url_name, key_name = "LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_API_KEY"
        else:
            raise ValueError("CompatibleModelClient: role must be 'primary' or 'fallback'")
        base_url = getattr(settings, url_name)
        api_key = getattr(settings, key_name).get_secret_value()
        if not base_url.strip() or not api_key.strip():
            raise ValueError(f"CompatibleModelClient: {url_name} and {key_name} are required for role {role!r}")
        return cls(base_url, api_key, transport=transport,
                   default_timeout_seconds=settings.LLM_REQUEST_TIMEOUT_SECONDS)

    def __repr__(self) -> str:
        return f"CompatibleModelClient(url={self._url!r})"

    # -- request

    def build_payload(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": message.role, "content": message.content} for message in request.messages],
            self._max_tokens_field: request.max_output_tokens,
            "stream": stream,
        }
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _open(self, request: ModelRequest, *, stream: bool) -> tuple[HttpResponse, float]:
        """Send the request; returns the response and the absolute deadline."""

        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        timeout = request.timeout_seconds if request.timeout_seconds is not None else self._default_timeout
        deadline = self._clock() + timeout
        body = json.dumps(self.build_payload(request, stream=stream), ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        try:
            response = self._transport.open(self._url, body, headers, timeout)
        except TimeoutError:
            raise _Fail(ModelTimeoutError(request.model)) from None
        except _TRANSPORT_ERRORS:
            raise _Fail(ModelConnectionError(request.model)) from None
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
                usage = _parse_usage(parsed.get("usage"))
        retry_after = _parse_retry_after(response.header("Retry-After")) if status == 429 else None
        raise _Fail(_error_for_status(model, status, usage, retry_after))

    # -- ModelClient

    def complete(self, request: ModelRequest) -> ModelResult:
        try:
            return self._complete(request)
        except _Fail as fail:
            error = fail.error
        raise error from None

    def _complete(self, request: ModelRequest) -> ModelResult:
        model = request.model if isinstance(request, ModelRequest) else ""
        response, deadline = self._open(request, stream=False)
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
        usage = _parse_usage(parsed.get("usage"))
        if parsed.get("error") is not None:
            raise _Fail(_malformed(model, status, usage))
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise _Fail(_malformed(model, status, usage))
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        finish_reason = _finish(choices[0].get("finish_reason"))
        if not isinstance(content, str) or finish_reason is None:
            raise _Fail(_malformed(model, status, usage))
        return ModelResult(
            text=content,
            model_requested=model,
            model_responded=_parse_model(parsed.get("model")),
            usage=usage,
            finish_reason=finish_reason,
        )

    def stream(self, request: ModelRequest) -> Generator[StreamEvent, None, None]:
        """Lazy: nothing is sent until the first ``next()``; ``close()`` releases the connection."""

        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        return self._stream(request)

    def _stream(self, request: ModelRequest) -> Generator[StreamEvent, None, None]:
        events = self._stream_events(request)
        while True:
            try:
                event = next(events)
            except StopIteration:
                return
            except _Fail as fail:
                error = fail.error
                break
            try:
                yield event
            except GeneratorExit:
                events.close()
                raise
        raise error from None

    def _stream_events(self, request: ModelRequest) -> Generator[StreamEvent, None, None]:
        model = request.model
        response, deadline = self._open(request, stream=True)
        try:
            self._raise_for_status(response, deadline, model)
            status = response.status
            content_type = (response.header("Content-Type") or "").strip().lower()
            if not content_type.startswith("text/event-stream"):
                raise _Fail(_malformed(model, status))
            parts: list[str] = []
            usage: Usage | None = None
            responded: str | None = None
            finish_reason: str | None = None
            for data in self._sse_data(response, deadline, model, status):
                if data == "[DONE]":
                    reason = _finish(finish_reason)
                    if reason is None:
                        raise _Fail(_malformed(model, status, usage))
                    result = ModelResult(
                        text="".join(parts),
                        model_requested=model,
                        model_responded=responded,
                        usage=usage,
                        finish_reason=reason,
                    )
                    response.close()  # release before handing over the last event
                    yield StreamDone(result)
                    return
                try:
                    chunk = _loads(data)
                except ValueError:
                    chunk = None
                if not isinstance(chunk, dict):
                    raise _Fail(_malformed(model, status, usage))
                chunk_usage = _parse_usage(chunk.get("usage"))
                if chunk_usage is not None:
                    usage = chunk_usage
                if chunk.get("error") is not None:
                    raise _Fail(ModelStreamInterruptedError(model, usage=usage))
                chunk_model = _parse_model(chunk.get("model"))
                if chunk_model is not None:
                    responded = chunk_model
                choices = chunk.get("choices", [])
                if not isinstance(choices, list):
                    raise _Fail(_malformed(model, status, usage))
                for choice in choices:
                    if not isinstance(choice, dict):
                        raise _Fail(_malformed(model, status, usage))
                    if choice.get("index", 0) != 0:
                        continue
                    delta = choice.get("delta", {})
                    if delta is None:
                        delta = {}
                    if not isinstance(delta, dict):
                        raise _Fail(_malformed(model, status, usage))
                    content = delta.get("content")
                    if content is not None and not isinstance(content, str):
                        raise _Fail(_malformed(model, status, usage))
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]
                    if content:
                        parts.append(content)
                        yield StreamDelta(content)
            raise _Fail(ModelStreamInterruptedError(model, usage=usage))
        finally:
            response.close()

    def _sse_data(self, response: HttpResponse, deadline: float, model: str, status: int) -> Iterator[str]:
        """Yield the ``data`` payload of each server-sent event; stops at end of body."""

        buffer = b""
        total = 0
        data_lines: list[str] = []
        at_end = False
        while not at_end:
            chunk = self._read(response, deadline, model, on_break=ModelStreamInterruptedError)
            if chunk:
                total += len(chunk)
                if total > self._max_bytes:
                    raise _Fail(_malformed(model, status))
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
            else:  # end of body: a last line without newline still counts
                at_end = True
                lines, buffer = ([buffer] if buffer else []), b""
            for raw in lines:
                try:
                    line = raw.rstrip(b"\r").decode("utf-8")
                except UnicodeDecodeError:
                    raise _Fail(_malformed(model, status)) from None
                if not line:
                    if data_lines:
                        yield "\n".join(data_lines)
                        data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                field, _, value = line.partition(":")
                if field == "data":
                    data_lines.append(value[1:] if value.startswith(" ") else value)
        if data_lines and data_lines == ["[DONE]"]:
            yield "[DONE]"


def _chat_url(base_url: object) -> str:
    error = ValueError("CompatibleModelClient: base_url must be an http(s) URL without credentials, query or fragment")
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
    return base_url.rstrip("/") + "/chat/completions"


__all__ = [
    "DEFAULT_MAX_RESPONSE_BYTES",
    "MAX_ERROR_BODY_BYTES",
    "MAX_TOKENS_FIELDS",
    "MESSAGE_OVERHEAD_TOKENS",
    "REQUEST_OVERHEAD_TOKENS",
    "CompatibleModelClient",
    "HttpResponse",
    "HttpTransport",
    "StdlibTransport",
    "estimate_input_tokens",
]
