"""OpenAI-compatible adapters (E03): ``CompatibleModelClient`` implements the E02
``ModelClient`` over Chat Completions, ``CompatibleEmbeddingClient`` the E02
``EmbeddingClient`` over Embeddings (ADR-017 决定 2). Both share one transport, one
error classification and one key/URL check.

One chat request → one ``POST {base_url}/chat/completions``. Retries, fallback switching,
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

Embeddings (ADR-017 决定 2; E07 keeps switching, validation and caching):

- One ``EmbeddingRequest`` → ``POST {base_url}/embeddings`` per batch of at most
  ``batch_size`` texts (``EMBEDDING_BATCH_SIZE``, which must not exceed the provider
  limit ``provider_max_batch_size``), each with ``model``, ``input``, ``dimensions`` and
  ``encoding_format = "float"``. Batches run one after another; any failure fails the
  whole request (no partial result). Each HTTP call gets its own timeout; with
  ``EmbeddingRequest.timeout_seconds`` (a QA chain deadline, ADR-082 决定 3) all batches
  share that budget instead.
- ``data[].index`` restores input order. The item count must equal the batch size, every
  index must be an int in range and unique, and every vector must have exactly
  ``dimensions`` finite numbers (E07's criterion); otherwise malformed_response.
- ``usage.prompt_tokens`` (else ``total_tokens``) summed over batches as input tokens,
  output 0; ``None`` as soon as one batch lacks usage. ``model_responded`` is the
  ``model`` field (``None`` if no batch had one); batches naming different models are
  malformed_response.

Nothing here logs. Errors are raised ``from None`` and carry only the model ID, status,
usage and ``Retry-After``: never the key, prompt text, model output, input texts,
vectors or response body.
"""

from __future__ import annotations

import http.client
import json
import math
import socket
import ssl
import threading
import time
from collections.abc import Callable, Generator, Iterator, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol
from urllib.parse import urlsplit
from .client import (
    FINISH_REASONS,
    EmbeddingRequest,
    EmbeddingResult,
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
    StreamReasoning,
    Usage,
)
# Keep legacy module attributes as explicit aliases, including existing internal consumers.
from app.services.ai.compatible_base import (
    _CompatibleHttpClient,
    _endpoint_url,
)
from app.services.ai.compatible_embedding import (
    CompatibleEmbeddingClient,
)
from app.services.ai.compatible_protocol import (
    CORE_PAYLOAD_FIELDS,
    DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH,
    DEFAULT_MAX_RESPONSE_BYTES,
    MAX_ERROR_BODY_BYTES,
    MAX_TOKENS_FIELDS,
    MESSAGE_OVERHEAD_TOKENS,
    REASONING_FIELDS,
    REQUEST_OVERHEAD_TOKENS,
    THINKING_DISABLED,
    _Fail,
    _READ_SIZE,
    _TRANSPORT_ERRORS,
    _error_for_status,
    _finish,
    _is_count,
    _loads,
    _malformed,
    _parse_embedding_usage,
    _parse_model,
    _parse_retry_after,
    _parse_usage,
    _plain_copy,
    _reasoning_chars,
    _vector_component,
    estimate_input_tokens,
    thinking_body,
)
from app.services.ai.compatible_transport import (
    AddressResolver,
    Connector,
    ExchangeDeadline,
    HttpResponse,
    HttpTransport,
    StdlibTransport,
    _StdlibResponse,
    _connect_within,
    _plain_connect,
    _shutdown,
    exchange,
    resolve_within,
    system_addresses,
)

if TYPE_CHECKING:
    from app.config import Settings

# ---------------------------------------------------------------- chat adapter


class CompatibleModelClient(_CompatibleHttpClient):
    """``ModelClient`` for one OpenAI-compatible provider (base URL + key); model per request."""

    _path = "/chat/completions"

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
        extra_body: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            base_url,
            api_key,
            transport=transport,
            default_timeout_seconds=default_timeout_seconds,
            max_response_bytes=max_response_bytes,
            clock=clock,
        )
        if max_tokens_field not in MAX_TOKENS_FIELDS:
            raise ValueError(f"CompatibleModelClient: max_tokens_field must be one of {sorted(MAX_TOKENS_FIELDS)}")
        self._max_tokens_field = max_tokens_field
        # ADR-090: extra request fields fixed at construction (a deep, plain copy); never override core fields
        self._extra_body = _plain_copy(extra_body or {})
        clash = sorted(set(self._extra_body) & CORE_PAYLOAD_FIELDS)
        if clash:
            raise ValueError(f"CompatibleModelClient: extra_body must not override {clash}")

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
        payload.update(_plain_copy(self._extra_body))
        return payload

    def _open(self, request: ModelRequest, *, stream: bool) -> tuple[HttpResponse, float]:
        """Send the request; returns the response and the absolute deadline."""

        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        timeout = request.timeout_seconds if request.timeout_seconds is not None else self._default_timeout
        return self._post(
            self.build_payload(request, stream=stream),
            request.model,
            timeout,
            accept="text/event-stream" if stream else "application/json",
        )

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
        parsed, status = self._read_json(response, deadline, model)
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
        reasoning = _reasoning_chars(message) if isinstance(message, dict) else 0
        return ModelResult(
            text=content,
            model_requested=model,
            model_responded=_parse_model(parsed.get("model")),
            usage=usage,
            finish_reason=finish_reason,
            reasoning_chars=reasoning or None,
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
            reasoning = 0
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
                        reasoning_chars=reasoning or None,
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
                    thought = _reasoning_chars(delta)
                    if thought:
                        # ADR-089: length only; the reasoning text never joins the answer
                        reasoning += thought
                        yield StreamReasoning(thought)
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


__all__ = [
    "DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "MAX_ERROR_BODY_BYTES",
    "MAX_TOKENS_FIELDS",
    "MESSAGE_OVERHEAD_TOKENS",
    "REQUEST_OVERHEAD_TOKENS",
    "CompatibleEmbeddingClient",
    "CompatibleModelClient",
    "HttpResponse",
    "HttpTransport",
    "StdlibTransport",
    "estimate_input_tokens",
]
