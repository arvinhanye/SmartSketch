"""E03: OpenAI-compatible Chat Completions and Embeddings adapters over an injectable HTTP transport.

Rules checked here come from docs/integrations.md「模型接入规则（A07）」and ADR-011 修订 2/3:
every request declares its output ceiling, input tokens are estimated locally (biased
high only), streaming requests ask for usage (``stream_options.include_usage``), HTTP
failures map onto the E02 error classes (including the pre-generation rejection set),
and no key, prompt text or model output ends up in reprs, errors or logs. The embeddings
client (ADR-017 决定 2) posts ``dimensions`` and ``encoding_format``, splits by
``EMBEDDING_BATCH_SIZE``, restores input order by ``index`` and checks every vector length.

No test touches the network: scripted transports stand in for the provider, and the
default stdlib transport is exercised only against a loopback server on 127.0.0.1.
"""

from __future__ import annotations

import http.client
import http.server
import json
import logging
import socket
import threading
import time
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from app.config import Settings, load_settings
from app.services.ai.client import (
    REJECTED_BEFORE_GENERATION_STATUSES,
    EmbeddingClient,
    EmbeddingRequest,
    ErrorClass,
    Message,
    ModelAuthError,
    ModelCallError,
    ModelClient,
    ModelConnectionError,
    ModelInvalidRequestError,
    ModelMalformedResponseError,
    ModelOutputError,
    ModelRateLimitedError,
    ModelRequest,
    ModelServerError,
    ModelStreamInterruptedError,
    ModelTimeoutError,
    StreamDelta,
    StreamDone,
    Usage,
)
from app.services.ai.compatible import (
    DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH,
    MESSAGE_OVERHEAD_TOKENS,
    REQUEST_OVERHEAD_TOKENS,
    CompatibleEmbeddingClient,
    CompatibleModelClient,
    StdlibTransport,
    estimate_input_tokens,
)
from app.services.ai.embeddings import EmbeddingAdapter, EmbeddingBatchError, EmbeddingCache

API_KEY = "sk-test-SECRET-4c1d9e"
PROMPT = "学生问题-不应出现在日志-7f3a"
OUTPUT = "模型正文-不应出现在日志-b2e8"
BASE_URL = "https://llm.example.test/v1"
MODEL = "model-x-2026-01"


# ---------------------------------------------------------------- scripted transport


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class ScriptedResponse:
    """A provider response delivered in pieces; ``steps`` items are bytes or exceptions."""

    def __init__(
        self,
        status: int = 200,
        body: bytes | None = None,
        *,
        steps: list[bytes | BaseException] | None = None,
        headers: Mapping[str, str] | None = None,
        clock: FakeClock | None = None,
        seconds_per_read: float = 0.0,
    ) -> None:
        self.status = status
        self._steps: list[bytes | BaseException] = list(steps) if steps is not None else [body or b""]
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._clock = clock
        self._seconds_per_read = seconds_per_read
        self.read_timeouts: list[float] = []
        self.closed = False

    def header(self, name: str) -> str | None:
        return self._headers.get(name.lower())

    def read(self, amount: int, timeout: float) -> bytes:
        assert amount > 0
        self.read_timeouts.append(timeout)
        if self._clock is not None:
            self._clock.now += self._seconds_per_read
        if not self._steps:
            return b""
        step = self._steps[0]
        if isinstance(step, BaseException):
            self._steps.pop(0)
            raise step
        piece, rest = step[:amount], step[amount:]
        if rest:
            self._steps[0] = rest
        else:
            self._steps.pop(0)
        return piece

    def close(self) -> None:
        self.closed = True


class ScriptedTransport:
    def __init__(self, *outcomes: ScriptedResponse | BaseException) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> ScriptedResponse:
        self.calls.append({"url": url, "body": body, "headers": dict(headers), "timeout": timeout})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.calls[-1]["body"].decode("utf-8"))


def make_request(content: str = PROMPT, **overrides: Any) -> ModelRequest:
    fields: dict[str, Any] = {
        "purpose": "extract_entities",
        "model": MODEL,
        "messages": [Message("system", "你是抽取助手。"), Message("user", content)],
        "max_output_tokens": 256,
    }
    fields.update(overrides)
    return ModelRequest(**fields)


def make_client(transport: ScriptedTransport, **kwargs: Any) -> CompatibleModelClient:
    kwargs.setdefault("default_timeout_seconds", 30.0)
    return CompatibleModelClient(BASE_URL, API_KEY, transport=transport, **kwargs)


def completion_body(
    content: Any = OUTPUT,
    *,
    finish_reason: Any = "stop",
    usage: Any = ...,
    model: Any = MODEL,
) -> bytes:
    body: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
    }
    if model is not ...:
        body["model"] = model
    if usage is ...:
        body["usage"] = {"prompt_tokens": 21, "completion_tokens": 7, "total_tokens": 28}
    else:
        body["usage"] = usage
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def sse(*events: Any) -> bytes:
    out = []
    for event in events:
        data = event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)
        out.append(f"data: {data}\n\n")
    return "".join(out).encode("utf-8")


def chunk(content: str | None = None, *, finish_reason: str | None = None, role: str | None = None) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "model": MODEL,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        "usage": None,
    }


USAGE_CHUNK = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "model": MODEL, "choices": [],
               "usage": {"prompt_tokens": 30, "completion_tokens": 4, "total_tokens": 34}}
SSE_HEADERS = {"Content-Type": "text/event-stream; charset=utf-8"}


def good_stream(**kwargs: Any) -> ScriptedResponse:
    body = sse(chunk(role="assistant"), chunk("栈是"), chunk("后进先出"), chunk(finish_reason="stop"), USAGE_CHUNK, "[DONE]")
    return ScriptedResponse(200, body, headers=SSE_HEADERS, **kwargs)


def drain(client: CompatibleModelClient, request: ModelRequest) -> list[Any]:
    return list(client.stream(request))


# ---------------------------------------------------------------- request shape


def test_client_satisfies_model_client_protocol() -> None:
    assert isinstance(make_client(ScriptedTransport()), ModelClient)


def test_complete_posts_chat_completions_with_output_ceiling() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body()))
    make_client(transport).complete(make_request())
    call = transport.calls[0]
    assert call["url"] == "https://llm.example.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    payload = transport.payload
    assert payload["model"] == MODEL
    assert payload["messages"] == [
        {"role": "system", "content": "你是抽取助手。"},
        {"role": "user", "content": PROMPT},
    ]
    assert payload["max_tokens"] == 256
    assert payload["stream"] is False
    assert "stream_options" not in payload
    assert "response_format" not in payload


@pytest.mark.parametrize("ceiling", [1, 64, 8192])
def test_every_request_declares_the_output_ceiling(ceiling: int) -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body()), good_stream())
    client = make_client(transport)
    client.complete(make_request(max_output_tokens=ceiling))
    assert transport.payload["max_tokens"] == ceiling
    drain(client, make_request(max_output_tokens=ceiling))
    assert transport.payload["max_tokens"] == ceiling


def test_max_completion_tokens_field_option() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body()))
    make_client(transport, max_tokens_field="max_completion_tokens").complete(make_request(max_output_tokens=99))
    assert transport.payload["max_completion_tokens"] == 99
    assert "max_tokens" not in transport.payload


def test_unknown_max_tokens_field_rejected() -> None:
    with pytest.raises(ValueError):
        make_client(ScriptedTransport(), max_tokens_field="max_new_tokens")


def test_base_url_trailing_slash_is_normalised() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body()))
    CompatibleModelClient("https://api.example.test/", API_KEY, transport=transport).complete(make_request())
    assert transport.calls[0]["url"] == "https://api.example.test/chat/completions"


def test_json_mode_requests_json_object() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body('{"entities": []}')))
    result = make_client(transport).complete(make_request(response_format="json"))
    assert transport.payload["response_format"] == {"type": "json_object"}
    assert result.json() == {"entities": []}


def test_stream_requests_usage() -> None:
    transport = ScriptedTransport(good_stream())
    drain(make_client(transport), make_request())
    payload = transport.payload
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["max_tokens"] == 256
    assert transport.calls[0]["headers"]["Accept"] == "text/event-stream"


def test_request_timeout_overrides_default() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body()), ScriptedResponse(200, completion_body()))
    client = make_client(transport, default_timeout_seconds=42.0)
    client.complete(make_request())
    client.complete(make_request(timeout_seconds=2.5))
    assert [call["timeout"] for call in transport.calls] == [42.0, 2.5]


# ---------------------------------------------------------------- success parsing


def test_complete_parses_text_model_usage_and_finish_reason() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body(model="model-x-2026-01-alias")))
    result = make_client(transport).complete(make_request())
    assert result.text == OUTPUT
    assert result.model_requested == MODEL
    assert result.model_responded == "model-x-2026-01-alias"
    assert result.usage == Usage(21, 7)
    assert result.finish_reason == "stop"


def test_complete_length_finish_reason() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body(finish_reason="length")))
    assert make_client(transport).complete(make_request()).finish_reason == "length"


@pytest.mark.parametrize(
    "usage",
    [
        None,
        "12",
        [],
        {"prompt_tokens": 3},
        {"prompt_tokens": -1, "completion_tokens": 2},
        {"prompt_tokens": True, "completion_tokens": 2},
        {"prompt_tokens": 1.5, "completion_tokens": 2},
    ],
)
def test_unparseable_usage_is_none_not_failure(usage: Any) -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body(usage=usage)))
    result = make_client(transport).complete(make_request())
    assert result.usage is None
    assert result.text == OUTPUT


def test_missing_usage_key_is_none() -> None:
    body = json.loads(completion_body())
    del body["usage"]
    transport = ScriptedTransport(ScriptedResponse(200, json.dumps(body).encode()))
    assert make_client(transport).complete(make_request()).usage is None


@pytest.mark.parametrize("model", [..., None, "", 7])
def test_missing_model_field_gives_none(model: Any) -> None:
    body = json.loads(completion_body())
    if model is ...:
        del body["model"]
    else:
        body["model"] = model
    transport = ScriptedTransport(ScriptedResponse(200, json.dumps(body).encode()))
    assert make_client(transport).complete(make_request()).model_responded is None


def test_bad_json_output_is_a_successful_billable_call() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body('{"entities": [')))
    result = make_client(transport).complete(make_request(response_format="json"))
    assert result.usage == Usage(21, 7)
    with pytest.raises(ModelOutputError) as info:
        result.json()
    assert info.value.result is result


def test_reasoning_content_is_not_part_of_text() -> None:
    body = json.loads(completion_body())
    body["choices"][0]["message"]["reasoning_content"] = "思考过程"
    transport = ScriptedTransport(ScriptedResponse(200, json.dumps(body, ensure_ascii=False).encode()))
    assert make_client(transport).complete(make_request()).text == OUTPUT


# ---------------------------------------------------------------- malformed responses


def _malformed_bodies() -> list[bytes]:
    base = json.loads(completion_body())
    no_choices = dict(base)
    del no_choices["choices"]
    variants: list[Any] = [
        [1, 2],
        "text",
        no_choices,
        {**base, "choices": []},
        {**base, "choices": "x"},
        {**base, "choices": [1]},
        {**base, "choices": [{"index": 0, "finish_reason": "stop"}]},
        {**base, "choices": [{"index": 0, "message": "x", "finish_reason": "stop"}]},
        {**base, "choices": [{"index": 0, "message": {"role": "assistant", "content": None}, "finish_reason": "stop"}]},
        {**base, "choices": [{"index": 0, "message": {"role": "assistant", "content": 5}, "finish_reason": "stop"}]},
    ]
    return [b"not json", b"", b"{\"choices\": [", *(json.dumps(v).encode() for v in variants)]


@pytest.mark.parametrize("body", _malformed_bodies())
def test_malformed_success_body(body: bytes) -> None:
    transport = ScriptedTransport(ScriptedResponse(200, body))
    with pytest.raises(ModelMalformedResponseError) as info:
        make_client(transport).complete(make_request())
    assert info.value.error_class is ErrorClass.MALFORMED_RESPONSE
    assert info.value.status_code == 200
    assert info.value.rejected_before_generation is False


@pytest.mark.parametrize("finish_reason", ["content_filter", "tool_calls", "insufficient_system_resource", None, 3])
def test_unsupported_finish_reason_is_malformed_and_keeps_usage(finish_reason: Any) -> None:
    transport = ScriptedTransport(ScriptedResponse(200, completion_body(finish_reason=finish_reason)))
    with pytest.raises(ModelMalformedResponseError) as info:
        make_client(transport).complete(make_request())
    assert info.value.usage == Usage(21, 7)


def test_error_object_with_200_is_malformed() -> None:
    body = json.dumps({"error": {"message": "overloaded", "type": "server_error"}}).encode()
    transport = ScriptedTransport(ScriptedResponse(200, body))
    with pytest.raises(ModelMalformedResponseError):
        make_client(transport).complete(make_request())


def test_invalid_utf8_is_malformed() -> None:
    transport = ScriptedTransport(ScriptedResponse(200, b"\xff\xfe{}"))
    with pytest.raises(ModelMalformedResponseError):
        make_client(transport).complete(make_request())


def test_oversized_body_is_malformed_and_closed() -> None:
    response = ScriptedResponse(200, completion_body("x" * 5000))
    transport = ScriptedTransport(response)
    with pytest.raises(ModelMalformedResponseError):
        make_client(transport, max_response_bytes=1024).complete(make_request())
    assert response.closed


@pytest.mark.parametrize("status", [101, 204, 301, 302, 304])
def test_non_200_non_error_status_is_malformed(status: int) -> None:
    transport = ScriptedTransport(ScriptedResponse(status, b""))
    with pytest.raises(ModelMalformedResponseError) as info:
        make_client(transport).complete(make_request())
    assert info.value.status_code == status


def test_status_outside_http_range_is_malformed_without_status() -> None:
    transport = ScriptedTransport(ScriptedResponse(999, b""))
    with pytest.raises(ModelMalformedResponseError) as info:
        make_client(transport).complete(make_request())
    assert info.value.status_code is None


# ---------------------------------------------------------------- HTTP error classification

STATUS_CASES = [
    (400, ModelInvalidRequestError, ErrorClass.INVALID_REQUEST),
    (401, ModelAuthError, ErrorClass.AUTH),
    (402, ModelInvalidRequestError, ErrorClass.INVALID_REQUEST),
    (403, ModelAuthError, ErrorClass.AUTH),
    (404, ModelInvalidRequestError, ErrorClass.INVALID_REQUEST),
    (408, ModelTimeoutError, ErrorClass.TIMEOUT),
    (409, ModelInvalidRequestError, ErrorClass.INVALID_REQUEST),
    (413, ModelInvalidRequestError, ErrorClass.INVALID_REQUEST),
    (422, ModelInvalidRequestError, ErrorClass.INVALID_REQUEST),
    (429, ModelRateLimitedError, ErrorClass.RATE_LIMITED),
    (500, ModelServerError, ErrorClass.SERVER),
    (502, ModelServerError, ErrorClass.SERVER),
    (503, ModelServerError, ErrorClass.SERVER),
    (504, ModelServerError, ErrorClass.SERVER),
    (529, ModelServerError, ErrorClass.SERVER),
]
ERROR_BODY = json.dumps({"error": {"message": f"echo: {PROMPT}", "type": "invalid_request_error"}}).encode()


@pytest.mark.parametrize(("status", "error_type", "error_class"), STATUS_CASES)
@pytest.mark.parametrize("mode", ["complete", "stream"])
def test_http_status_maps_to_error_class(
    status: int, error_type: type[ModelCallError], error_class: ErrorClass, mode: str
) -> None:
    response = ScriptedResponse(status, ERROR_BODY)
    client = make_client(ScriptedTransport(response))
    with pytest.raises(error_type) as info:
        if mode == "complete":
            client.complete(make_request())
        else:
            drain(client, make_request())
    error = info.value
    assert type(error) is error_type
    assert error.error_class is error_class
    assert error.status_code == status
    assert error.model == MODEL
    assert error.rejected_before_generation is (status in REJECTED_BEFORE_GENERATION_STATUSES)
    assert response.closed


def test_pre_generation_rejection_set_is_exactly_adr011_revision3() -> None:
    rejected = set()
    for status, _, _ in STATUS_CASES:
        client = make_client(ScriptedTransport(ScriptedResponse(status, b"{}")))
        try:
            client.complete(make_request())
        except ModelCallError as error:
            if error.rejected_before_generation:
                rejected.add(status)
    assert rejected == {400, 401, 403, 404, 413, 422, 429}


def test_error_body_usage_is_attached() -> None:
    body = json.dumps({"error": {"message": "x"}, "usage": {"prompt_tokens": 9, "completion_tokens": 0}}).encode()
    with pytest.raises(ModelServerError) as info:
        make_client(ScriptedTransport(ScriptedResponse(500, body))).complete(make_request())
    assert info.value.usage == Usage(9, 0)


@pytest.mark.parametrize("body", [b"<html>bad gateway</html>", b"", b"\xff", b"[1]", b"{\"usage\": 5}"])
def test_unparseable_error_body_still_classified(body: bytes) -> None:
    with pytest.raises(ModelServerError) as info:
        make_client(ScriptedTransport(ScriptedResponse(502, body))).complete(make_request())
    assert info.value.usage is None
    assert info.value.status_code == 502


def test_error_body_read_failure_still_classified() -> None:
    response = ScriptedResponse(503, steps=[ConnectionResetError("reset")])
    with pytest.raises(ModelServerError):
        make_client(ScriptedTransport(response)).complete(make_request())
    assert response.closed


def test_huge_error_body_is_not_read_whole() -> None:
    response = ScriptedResponse(500, b"x" * (1024 * 1024))
    with pytest.raises(ModelServerError):
        make_client(ScriptedTransport(response)).complete(make_request())
    assert len(response.read_timeouts) <= 20


@pytest.mark.parametrize(
    ("header", "expected"),
    [("7", 7.0), ("0", 0.0), (" 2 ", 2.0), ("1.5", 1.5), (None, None), ("-3", None), ("soon", None),
     ("nan", None), ("inf", None), ("Wed, 21 Oct 2026 07:28:00 GMT", None)],
)
def test_retry_after_seconds(header: str | None, expected: float | None) -> None:
    headers = {"Retry-After": header} if header is not None else {}
    transport = ScriptedTransport(ScriptedResponse(429, b"{}", headers=headers))
    with pytest.raises(ModelRateLimitedError) as info:
        make_client(transport).complete(make_request())
    assert info.value.retry_after_seconds == expected


# ---------------------------------------------------------------- transport failures


@pytest.mark.parametrize("exc", [TimeoutError("timed out"), socket.timeout("timed out")])
def test_open_timeout_is_timeout_without_status(exc: BaseException) -> None:
    with pytest.raises(ModelTimeoutError) as info:
        make_client(ScriptedTransport(exc)).complete(make_request())
    assert info.value.status_code is None
    assert info.value.rejected_before_generation is False


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionRefusedError("refused"),
        socket.gaierror("name"),
        OSError("unreachable"),
        http.client.RemoteDisconnected("gone"),
        http.client.BadStatusLine("junk"),
    ],
)
@pytest.mark.parametrize("mode", ["complete", "stream"])
def test_open_connection_failure_is_connection_error(exc: BaseException, mode: str) -> None:
    client = make_client(ScriptedTransport(exc))
    with pytest.raises(ModelConnectionError) as info:
        if mode == "complete":
            client.complete(make_request())
        else:
            drain(client, make_request())
    assert info.value.status_code is None
    assert info.value.rejected_before_generation is False


def test_body_read_timeout_in_complete_is_timeout() -> None:
    response = ScriptedResponse(200, steps=[b'{"choices"', TimeoutError("read")])
    with pytest.raises(ModelTimeoutError):
        make_client(ScriptedTransport(response)).complete(make_request())
    assert response.closed


@pytest.mark.parametrize("exc", [ConnectionResetError("reset"), http.client.IncompleteRead(b"")])
def test_body_read_failure_in_complete_is_connection_error(exc: BaseException) -> None:
    response = ScriptedResponse(200, steps=[b'{"choices"', exc])
    with pytest.raises(ModelConnectionError):
        make_client(ScriptedTransport(response)).complete(make_request())
    assert response.closed


def test_total_deadline_bounds_a_slow_drip_response() -> None:
    clock = FakeClock()
    body = completion_body()
    response = ScriptedResponse(200, steps=[body[i : i + 8] for i in range(0, len(body), 8)], clock=clock,
                                seconds_per_read=1.0)
    client = make_client(ScriptedTransport(response), clock=clock)
    with pytest.raises(ModelTimeoutError):
        client.complete(make_request(timeout_seconds=5))
    assert response.closed
    assert len(response.read_timeouts) <= 6
    assert all(later < earlier for earlier, later in zip(response.read_timeouts, response.read_timeouts[1:]))
    assert all(0 < t <= 5 for t in response.read_timeouts)


def test_deadline_spent_while_opening_is_timeout() -> None:
    clock = FakeClock()

    class SlowOpen(ScriptedTransport):
        def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> ScriptedResponse:
            clock.now += 10
            return super().open(url, body, headers, timeout)

    response = ScriptedResponse(200, completion_body())
    with pytest.raises(ModelTimeoutError):
        make_client(SlowOpen(response), clock=clock).complete(make_request(timeout_seconds=5))
    assert response.closed


def test_errors_do_not_chain_transport_or_parser_exceptions() -> None:
    cases = [
        ScriptedTransport(ConnectionRefusedError(PROMPT)),
        ScriptedTransport(ScriptedResponse(200, f"not json {OUTPUT}".encode())),
        ScriptedTransport(ScriptedResponse(200, steps=[b"{", TimeoutError(PROMPT)])),
    ]
    for transport in cases:
        with pytest.raises(ModelCallError) as info:
            make_client(transport).complete(make_request())
        assert info.value.__cause__ is None
        assert info.value.__suppress_context__ is True


# ---------------------------------------------------------------- streaming


def test_stream_yields_deltas_then_done_with_usage() -> None:
    response = good_stream()
    events = drain(make_client(ScriptedTransport(response)), make_request())
    deltas = [e.text for e in events if isinstance(e, StreamDelta)]
    assert deltas == ["栈是", "后进先出"]
    assert isinstance(events[-1], StreamDone)
    assert sum(isinstance(e, StreamDone) for e in events) == 1
    result = events[-1].result
    assert result.text == "栈是后进先出"
    assert result.usage == Usage(30, 4)
    assert result.model_requested == MODEL
    assert result.model_responded == MODEL
    assert result.finish_reason == "stop"
    assert response.closed


def test_stream_usage_on_finish_chunk_and_length() -> None:
    last = chunk(finish_reason="length")
    last["usage"] = {"prompt_tokens": 5, "completion_tokens": 2}
    body = sse(chunk("ab"), last, "[DONE]")
    events = drain(make_client(ScriptedTransport(ScriptedResponse(200, body, headers=SSE_HEADERS))), make_request())
    result = events[-1].result
    assert result.usage == Usage(5, 2)
    assert result.finish_reason == "length"


def test_stream_without_usage_gives_none() -> None:
    body = sse(chunk("ab"), chunk(finish_reason="stop"), "[DONE]")
    events = drain(make_client(ScriptedTransport(ScriptedResponse(200, body, headers=SSE_HEADERS))), make_request())
    assert events[-1].result.usage is None


def test_stream_parsing_tolerates_framing_variants() -> None:
    raw = (
        ": keep-alive\r\n\r\n"
        "event: message\r\n"
        f"data: {json.dumps(chunk(role='assistant'))}\r\n\r\n"
        f"data:{json.dumps(chunk('队列'), ensure_ascii=False)}\n\n"
        f"data: {json.dumps(chunk(''))}\n\n"
        f"data: {json.dumps(chunk('先进先出'), ensure_ascii=False)}\n\n"
        f"data: {json.dumps(chunk(finish_reason='stop'))}\n\n"
        "data: [DONE]\n\n"
    ).encode("utf-8")
    steps: list[bytes | BaseException] = [raw[i : i + 3] for i in range(0, len(raw), 3)]  # splits UTF-8 chars
    response = ScriptedResponse(200, steps=steps, headers=SSE_HEADERS)
    events = drain(make_client(ScriptedTransport(response)), make_request())
    assert [e.text for e in events if isinstance(e, StreamDelta)] == ["队列", "先进先出"]
    assert events[-1].result.text == "队列先进先出"


def test_stream_stops_reading_at_done() -> None:
    body = sse(chunk("a"), chunk(finish_reason="stop"), "[DONE]") + b"data: {broken\n\n"
    events = drain(make_client(ScriptedTransport(ScriptedResponse(200, body, headers=SSE_HEADERS))), make_request())
    assert events[-1].result.text == "a"


def _run_until_error(client: CompatibleModelClient) -> tuple[list[str], BaseException]:
    delivered: list[str] = []
    with pytest.raises(ModelCallError) as info:
        for event in client.stream(make_request()):
            if isinstance(event, StreamDelta):
                delivered.append(event.text)
    return delivered, info.value


def test_stream_eof_before_done_is_interrupted_after_delivered_deltas() -> None:
    body = sse(chunk("前半"), chunk("段"))
    response = ScriptedResponse(200, body, headers=SSE_HEADERS)
    delivered, error = _run_until_error(make_client(ScriptedTransport(response)))
    assert delivered == ["前半", "段"]
    assert type(error) is ModelStreamInterruptedError
    assert error.rejected_before_generation is False
    assert response.closed


def test_stream_reset_is_interrupted() -> None:
    response = ScriptedResponse(200, steps=[sse(chunk("a")), ConnectionResetError("reset")], headers=SSE_HEADERS)
    delivered, error = _run_until_error(make_client(ScriptedTransport(response)))
    assert delivered == ["a"]
    assert type(error) is ModelStreamInterruptedError


def test_stream_error_event_is_interrupted_and_keeps_usage() -> None:
    error_event = {"error": {"message": "overloaded"}, "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
    response = ScriptedResponse(200, sse(chunk("a"), error_event), headers=SSE_HEADERS)
    _, error = _run_until_error(make_client(ScriptedTransport(response)))
    assert type(error) is ModelStreamInterruptedError
    assert error.usage == Usage(3, 1)


def test_stream_read_timeout_is_timeout() -> None:
    response = ScriptedResponse(200, steps=[sse(chunk("a")), TimeoutError("idle")], headers=SSE_HEADERS)
    delivered, error = _run_until_error(make_client(ScriptedTransport(response)))
    assert delivered == ["a"]
    assert type(error) is ModelTimeoutError
    assert response.closed


def test_stream_total_deadline() -> None:
    clock = FakeClock()
    steps: list[bytes | BaseException] = [sse(chunk(str(i))) for i in range(50)]
    response = ScriptedResponse(200, steps=steps, headers=SSE_HEADERS, clock=clock, seconds_per_read=1.0)
    delivered, error = _run_until_error(make_client(ScriptedTransport(response), clock=clock))
    assert type(error) is ModelTimeoutError
    assert len(delivered) < 50


@pytest.mark.parametrize(
    "bad",
    ["{broken", "[1, 2]", json.dumps({"choices": "x"}), json.dumps({"choices": [1]}),
     json.dumps({"choices": [{"index": 0, "delta": "x"}]}),
     json.dumps({"choices": [{"index": 0, "delta": {"content": 5}}]})],
)
def test_stream_malformed_chunk(bad: str) -> None:
    response = ScriptedResponse(200, sse(chunk("a")) + f"data: {bad}\n\n".encode(), headers=SSE_HEADERS)
    _, error = _run_until_error(make_client(ScriptedTransport(response)))
    assert type(error) is ModelMalformedResponseError
    assert error.status_code == 200
    assert response.closed


def test_stream_done_without_finish_reason_is_malformed() -> None:
    body = sse(chunk("a"), USAGE_CHUNK, "[DONE]")
    _, error = _run_until_error(make_client(ScriptedTransport(ScriptedResponse(200, body, headers=SSE_HEADERS))))
    assert type(error) is ModelMalformedResponseError
    assert error.usage == Usage(30, 4)


def test_stream_content_filter_is_malformed() -> None:
    body = sse(chunk("a"), chunk(finish_reason="content_filter"), USAGE_CHUNK, "[DONE]")
    _, error = _run_until_error(make_client(ScriptedTransport(ScriptedResponse(200, body, headers=SSE_HEADERS))))
    assert type(error) is ModelMalformedResponseError


def test_stream_with_json_content_type_is_malformed() -> None:
    response = ScriptedResponse(200, completion_body(), headers={"Content-Type": "application/json"})
    _, error = _run_until_error(make_client(ScriptedTransport(response)))
    assert type(error) is ModelMalformedResponseError
    assert response.closed


def test_stream_oversized_line_is_malformed() -> None:
    response = ScriptedResponse(200, b"data: " + b"x" * 4096, headers=SSE_HEADERS)
    _, error = _run_until_error(make_client(ScriptedTransport(response), max_response_bytes=1024))
    assert type(error) is ModelMalformedResponseError


def test_stream_is_lazy_and_close_releases_response() -> None:
    response = good_stream()
    transport = ScriptedTransport(response)
    generator = make_client(transport).stream(make_request())
    assert transport.calls == []
    first = next(generator)
    assert isinstance(first, StreamDelta)
    generator.close()
    assert response.closed
    assert len(transport.calls) == 1


# ---------------------------------------------------------------- input estimate


def test_estimate_is_an_upper_bound_on_utf8_bytes_plus_overheads() -> None:
    request = make_request("栈是后进先出的线性表。" * 20)
    content_bytes = sum(len(m.content.encode("utf-8")) for m in request.messages)
    estimate = estimate_input_tokens(request)
    assert estimate >= content_bytes + len(request.messages) * MESSAGE_OVERHEAD_TOKENS + REQUEST_OVERHEAD_TOKENS
    assert estimate == estimate_input_tokens(request)


def test_estimate_grows_with_input_and_never_below_reported_usage_fixtures() -> None:
    small = estimate_input_tokens(make_request("a"))
    large = estimate_input_tokens(make_request("a" * 100))
    assert large - small >= 99
    # Byte-level BPE never yields more tokens than UTF-8 bytes; spot-check the fixtures above.
    assert estimate_input_tokens(make_request()) >= 30


def test_estimate_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        estimate_input_tokens("hello")  # type: ignore[arg-type]


# ---------------------------------------------------------------- construction and settings


@pytest.mark.parametrize(
    "base_url",
    ["", "ftp://x.test", "https://", "https://user:pw@x.test/v1", "https://x.test/v1?key=1", "https://x.test/#f",
     "https://x.test/ v1", "llm.example.test/v1"],
)
def test_invalid_base_url_rejected_without_echo(base_url: str) -> None:
    with pytest.raises(ValueError) as info:
        CompatibleModelClient(base_url, API_KEY, transport=ScriptedTransport())
    if base_url:
        assert base_url not in str(info.value)


@pytest.mark.parametrize("key", ["", "   ", "sk-abc\r\nX-Injected: 1", "sk-\x00", "sk-密钥", "sk abc"])
def test_invalid_api_key_rejected_without_echo(key: str) -> None:
    with pytest.raises(ValueError) as info:
        CompatibleModelClient(BASE_URL, key, transport=ScriptedTransport())
    if key.strip():
        assert key not in str(info.value)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_default_timeout_rejected(timeout: Any) -> None:
    with pytest.raises(ValueError):
        make_client(ScriptedTransport(), default_timeout_seconds=timeout)


def test_complete_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        make_client(ScriptedTransport()).complete("hello")  # type: ignore[arg-type]


def _settings(**extra: str) -> Any:
    env = {
        "LLM_MODE": "live",
        "LLM_BASE_URL": "https://primary.example.test/v1",
        "LLM_API_KEY": "sk-primary",
        "LLM_EXTRACTION_MODEL": "p-extract",
        "LLM_CHAT_MODEL": "p-chat",
        "LLM_REQUEST_TIMEOUT_SECONDS": "17",
    }
    env.update(extra)
    return load_settings(env)


def test_from_settings_primary_and_fallback() -> None:
    settings = _settings(
        LLM_FALLBACK_BASE_URL="https://fallback.example.test/compatible-mode/v1",
        LLM_FALLBACK_API_KEY="sk-fallback",
        LLM_FALLBACK_EXTRACTION_MODEL="f-extract",
        LLM_FALLBACK_CHAT_MODEL="f-chat",
    )
    transport = ScriptedTransport(ScriptedResponse(200, completion_body()), ScriptedResponse(200, completion_body()))
    CompatibleModelClient.from_settings(settings, transport=transport).complete(make_request())
    CompatibleModelClient.from_settings(settings, role="fallback", transport=transport).complete(make_request())
    assert transport.calls[0]["url"] == "https://primary.example.test/v1/chat/completions"
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer sk-primary"
    assert transport.calls[0]["timeout"] == 17.0
    assert transport.calls[1]["url"] == "https://fallback.example.test/compatible-mode/v1/chat/completions"
    assert transport.calls[1]["headers"]["Authorization"] == "Bearer sk-fallback"


def test_from_settings_missing_fallback_names_variable() -> None:
    with pytest.raises(ValueError, match="LLM_FALLBACK_BASE_URL"):
        CompatibleModelClient.from_settings(_settings(), role="fallback", transport=ScriptedTransport())
    with pytest.raises(ValueError):
        CompatibleModelClient.from_settings(_settings(), role="backup", transport=ScriptedTransport())  # type: ignore[arg-type]


# ---------------------------------------------------------------- log safety


def test_no_key_prompt_or_output_in_repr_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    leak_body = json.dumps({"error": {"message": f"{PROMPT} {API_KEY}"}, "echo": OUTPUT}, ensure_ascii=False).encode()
    transports = [
        ScriptedTransport(ScriptedResponse(400, leak_body)),
        ScriptedTransport(ScriptedResponse(200, f"{OUTPUT} not json".encode())),
        ScriptedTransport(ScriptedResponse(200, completion_body(finish_reason="content_filter"))),
        ScriptedTransport(ScriptedResponse(200, sse(chunk(OUTPUT)) + b"data: {bad " + PROMPT.encode() + b"\n\n",
                                           headers=SSE_HEADERS)),
        ScriptedTransport(ConnectionRefusedError(API_KEY)),
    ]
    rendered: list[str] = []
    for index, transport in enumerate(transports):
        client = make_client(transport)
        rendered.append(repr(client))
        with pytest.raises(ModelCallError) as info:
            if index == 3:
                drain(client, make_request())
            else:
                client.complete(make_request())
        rendered.extend([str(info.value), repr(info.value), repr(info.value.args), repr(vars(info.value))])
    ok = make_client(ScriptedTransport(ScriptedResponse(200, completion_body()))).complete(make_request())
    rendered.append(repr(ok))
    rendered.append(caplog.text)
    blob = "\n".join(rendered)
    for secret in (API_KEY, PROMPT, OUTPUT):
        assert secret not in blob
    assert caplog.records == []


# ---------------------------------------------------------------- default stdlib transport (loopback only)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    script: dict[str, Any] = {}
    seen: list[dict[str, Any]] = []

    def log_message(self, format: str, *args: Any) -> None:  # silence stderr
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).seen.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body)})
        mode = type(self).script["mode"]
        if mode == "sleep":
            time.sleep(1.0)
            return
        if mode == "json":
            payload = completion_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if mode == "embeddings":
            request = type(self).seen[-1]["body"]
            payload = embedding_body(
                [[float(i + 1)] * request["dimensions"] for i in range(len(request["input"]))],
                model=request["model"],
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if mode == "error":
            payload = b'{"error": {"message": "slow down"}}'
            self.send_response(429)
            self.send_header("Retry-After", "3")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        # chunked SSE
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for part in (sse(chunk("回")), sse(chunk("环")), sse(chunk(finish_reason="stop"), USAGE_CHUNK, "[DONE]")):
            self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")


@pytest.fixture
def loopback() -> Iterator[str]:
    _Handler.seen = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def test_stdlib_transport_complete_over_loopback(loopback: str) -> None:
    _Handler.script = {"mode": "json"}
    client = CompatibleModelClient(loopback, API_KEY, transport=StdlibTransport())
    result = client.complete(make_request())
    assert result.text == OUTPUT
    seen = _Handler.seen[0]
    assert seen["path"] == "/v1/chat/completions"
    assert seen["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert seen["body"]["max_tokens"] == 256


def test_stdlib_transport_stream_over_loopback(loopback: str) -> None:
    _Handler.script = {"mode": "sse"}
    events = drain(CompatibleModelClient(loopback, API_KEY), make_request())
    assert [e.text for e in events if isinstance(e, StreamDelta)] == ["回", "环"]
    assert events[-1].result.usage == Usage(30, 4)
    assert _Handler.seen[0]["body"]["stream_options"] == {"include_usage": True}


def test_stdlib_transport_error_status_over_loopback(loopback: str) -> None:
    _Handler.script = {"mode": "error"}
    with pytest.raises(ModelRateLimitedError) as info:
        CompatibleModelClient(loopback, API_KEY).complete(make_request())
    assert info.value.retry_after_seconds == 3.0


def test_stdlib_transport_timeout_over_loopback(loopback: str) -> None:
    _Handler.script = {"mode": "sleep"}
    started = time.monotonic()
    with pytest.raises(ModelTimeoutError):
        CompatibleModelClient(loopback, API_KEY).complete(make_request(timeout_seconds=0.2))
    assert time.monotonic() - started < 0.9


def test_stdlib_transport_connection_refused() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(ModelConnectionError):
        CompatibleModelClient(f"http://127.0.0.1:{port}/v1", API_KEY).complete(make_request(timeout_seconds=2))


# ================================================================ embeddings (ADR-017 决定 2)

EMB_MODEL = "text-embedding-v4"
EMB_TEXT = "课程片段-不应出现在日志-5d71"
EMB_SECRET_VALUE = 0.123456789


def make_embed_request(texts: tuple[str, ...] = ("a", "b"), *, dimensions: int = 4, model: str = EMB_MODEL) -> EmbeddingRequest:
    return EmbeddingRequest(model=model, texts=texts, dimensions=dimensions)


def make_embed_client(transport: ScriptedTransport, **kwargs: Any) -> CompatibleEmbeddingClient:
    kwargs.setdefault("default_timeout_seconds", 30.0)
    return CompatibleEmbeddingClient(BASE_URL, API_KEY, transport=transport, **kwargs)


def vec(seed: int, dimensions: int = 4) -> list[float]:
    return [float(seed) + i / 10 for i in range(dimensions)]


def embedding_body(
    vectors: list[Any],
    *,
    indexes: list[Any] | None = None,
    model: Any = EMB_MODEL,
    usage: Any = ...,
    order: list[int] | None = None,
) -> bytes:
    """An OpenAI-style embeddings response; ``order`` shuffles the ``data`` items."""

    items = [
        {"object": "embedding", "index": i if indexes is None else indexes[i], "embedding": vector}
        for i, vector in enumerate(vectors)
    ]
    if order is not None:
        items = [items[i] for i in order]
    body: dict[str, Any] = {"object": "list", "data": items}
    if model is not ...:
        body["model"] = model
    if usage is ...:
        body["usage"] = {"prompt_tokens": 3 * len(vectors), "total_tokens": 3 * len(vectors)}
    else:
        body["usage"] = usage
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def ok_embed(count: int, *, dimensions: int = 4, start: int = 0, **kwargs: Any) -> ScriptedResponse:
    return ScriptedResponse(200, embedding_body([vec(start + i, dimensions) for i in range(count)], **kwargs))


def test_embedding_client_satisfies_embedding_client_protocol() -> None:
    assert isinstance(make_embed_client(ScriptedTransport()), EmbeddingClient)


def test_embed_posts_embeddings_with_dimensions_and_float_encoding() -> None:
    transport = ScriptedTransport(ok_embed(2))
    make_embed_client(transport).embed(make_embed_request(("甲", "乙")))
    call = transport.calls[0]
    assert call["url"] == "https://llm.example.test/v1/embeddings"
    assert call["headers"]["Authorization"] == f"Bearer {API_KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["headers"]["Accept"] == "application/json"
    assert call["timeout"] == 30.0
    assert transport.payload == {"model": EMB_MODEL, "input": ["甲", "乙"], "dimensions": 4, "encoding_format": "float"}


def test_embed_base_url_trailing_slash_is_normalised() -> None:
    transport = ScriptedTransport(ok_embed(1))
    CompatibleEmbeddingClient(BASE_URL + "/", API_KEY, transport=transport).embed(make_embed_request(("a",)))
    assert transport.calls[0]["url"] == "https://llm.example.test/v1/embeddings"


def test_embed_parses_vectors_model_and_usage() -> None:
    response = ok_embed(2, usage={"prompt_tokens": 11, "total_tokens": 11})
    result = make_embed_client(ScriptedTransport(response)).embed(make_embed_request())
    assert result.vectors == (tuple(vec(0)), tuple(vec(1)))
    assert all(type(x) is float for vector in result.vectors for x in vector)
    assert result.model_requested == EMB_MODEL
    assert result.model_responded == EMB_MODEL
    assert result.usage == Usage(11, 0)
    assert response.closed


def test_embed_integer_components_become_floats() -> None:
    body = embedding_body([[1, 0, 0, 0]])
    result = make_embed_client(ScriptedTransport(ScriptedResponse(200, body))).embed(make_embed_request(("a",)))
    assert result.vectors == ((1.0, 0.0, 0.0, 0.0),)
    assert all(type(x) is float for x in result.vectors[0])


def test_embed_restores_input_order_by_index() -> None:
    response = ok_embed(3, order=[2, 0, 1])
    result = make_embed_client(ScriptedTransport(response)).embed(make_embed_request(("a", "b", "c")))
    assert result.vectors == (tuple(vec(0)), tuple(vec(1)), tuple(vec(2)))


def test_embed_splits_by_batch_size_and_restores_order_across_batches() -> None:
    transport = ScriptedTransport(
        ok_embed(2, start=0, order=[1, 0], usage={"prompt_tokens": 4, "total_tokens": 4}),
        ok_embed(2, start=2, order=[1, 0], usage={"prompt_tokens": 5, "total_tokens": 5}),
        ok_embed(1, start=4, usage={"prompt_tokens": 6, "total_tokens": 6}),
    )
    result = make_embed_client(transport, batch_size=2).embed(make_embed_request(("a", "b", "c", "d", "e")))
    sent = [json.loads(call["body"])["input"] for call in transport.calls]
    assert sent == [["a", "b"], ["c", "d"], ["e"]]
    assert all(json.loads(call["body"])["dimensions"] == 4 for call in transport.calls)
    assert result.vectors == tuple(tuple(vec(i)) for i in range(5))
    assert result.usage == Usage(15, 0)
    assert result.model_responded == EMB_MODEL


def test_embed_default_batch_size_is_ten() -> None:
    transport = ScriptedTransport(ok_embed(10), ok_embed(1, start=10))
    texts = tuple(f"t{i}" for i in range(11))
    result = make_embed_client(transport).embed(make_embed_request(texts))
    assert [len(json.loads(call["body"])["input"]) for call in transport.calls] == [10, 1]
    assert len(result.vectors) == 11


def test_embed_usage_is_none_when_any_batch_lacks_usage() -> None:
    transport = ScriptedTransport(ok_embed(1), ok_embed(1, start=1, usage=None))
    result = make_embed_client(transport, batch_size=1).embed(make_embed_request(("a", "b")))
    assert result.usage is None
    assert len(result.vectors) == 2


@pytest.mark.parametrize(
    "usage",
    [None, 5, "12", {}, {"prompt_tokens": -1}, {"prompt_tokens": True}, {"prompt_tokens": 1.5},
     {"total_tokens": "3"}],
)
def test_embed_unparseable_usage_is_none_not_failure(usage: Any) -> None:
    result = make_embed_client(ScriptedTransport(ok_embed(1, usage=usage))).embed(make_embed_request(("a",)))
    assert result.usage is None


def test_embed_usage_falls_back_to_total_tokens() -> None:
    response = ok_embed(1, usage={"total_tokens": 7})
    assert make_embed_client(ScriptedTransport(response)).embed(make_embed_request(("a",))).usage == Usage(7, 0)


@pytest.mark.parametrize("model", [..., None, "", 7])
def test_embed_missing_model_field_gives_none(model: Any) -> None:
    result = make_embed_client(ScriptedTransport(ok_embed(1, model=model))).embed(make_embed_request(("a",)))
    assert result.model_responded is None


def test_embed_batches_answering_different_models_is_malformed() -> None:
    transport = ScriptedTransport(ok_embed(1), ok_embed(1, start=1, model="text-embedding-v3"))
    with pytest.raises(ModelMalformedResponseError) as info:
        make_embed_client(transport, batch_size=1).embed(make_embed_request(("a", "b")))
    assert info.value.model == EMB_MODEL


@pytest.mark.parametrize(
    "vectors",
    [
        [vec(0, 3), vec(1)],        # one vector too short
        [vec(0), vec(1, 5)],        # one vector too long
        [[], vec(1)],               # empty vector
        [vec(0, 8), vec(1, 8)],     # provider ignored ``dimensions``
    ],
)
def test_embed_dimension_mismatch_is_malformed_and_keeps_usage(vectors: list[Any]) -> None:
    body = embedding_body(vectors, usage={"prompt_tokens": 6, "total_tokens": 6})
    with pytest.raises(ModelMalformedResponseError) as info:
        make_embed_client(ScriptedTransport(ScriptedResponse(200, body))).embed(make_embed_request())
    assert info.value.status_code == 200
    assert info.value.usage == Usage(6, 0)
    assert info.value.rejected_before_generation is False


@pytest.mark.parametrize(
    "bad",
    [[1.0, 2.0, "3", 4.0], [1.0, True, 0.0, 0.0], [1.0, None, 0.0, 0.0], [1.0, [2.0], 0.0, 0.0], "AAAAAA==", None, 5],
)
def test_embed_non_numeric_vector_is_malformed(bad: Any) -> None:
    body = embedding_body([bad, vec(1)])
    with pytest.raises(ModelMalformedResponseError):
        make_embed_client(ScriptedTransport(ScriptedResponse(200, body))).embed(make_embed_request())


@pytest.mark.parametrize("raw", [b"NaN", b"Infinity", b"-Infinity", b"1e999", b"1" + b"0" * 400])
def test_embed_non_finite_vector_value_is_malformed(raw: bytes) -> None:
    body = embedding_body([[1.0, 2.0, 3.0, 4.0]]).replace(b"4.0", raw, 1)
    with pytest.raises(ModelMalformedResponseError):
        make_embed_client(ScriptedTransport(ScriptedResponse(200, body))).embed(make_embed_request(("a",)))


@pytest.mark.parametrize("count", [0, 1, 3])
def test_embed_count_mismatch_is_malformed(count: int) -> None:
    with pytest.raises(ModelMalformedResponseError) as info:
        make_embed_client(ScriptedTransport(ok_embed(count))).embed(make_embed_request(("a", "b")))
    assert info.value.status_code == 200


@pytest.mark.parametrize(
    "indexes",
    [[0, 0], [1, 2], [-1, 0], [True, 0], ["0", 1], [None, 1], [0.0, 1]],
)
def test_embed_bad_indexes_are_malformed(indexes: list[Any]) -> None:
    body = embedding_body([vec(0), vec(1)], indexes=indexes)
    with pytest.raises(ModelMalformedResponseError):
        make_embed_client(ScriptedTransport(ScriptedResponse(200, body))).embed(make_embed_request())


def test_embed_missing_index_is_malformed() -> None:
    body = json.dumps({"data": [{"embedding": vec(0)}], "model": EMB_MODEL}).encode()
    with pytest.raises(ModelMalformedResponseError):
        make_embed_client(ScriptedTransport(ScriptedResponse(200, body))).embed(make_embed_request(("a",)))


def _malformed_embedding_bodies() -> list[bytes]:
    return [
        b"",
        b"not json",
        b"\xff\xfe",
        b"[1, 2]",
        b'{"object": "list"}',
        b'{"data": null}',
        b'{"data": {"0": [1, 2, 3, 4]}}',
        b'{"data": [[1.0, 2.0, 3.0, 4.0]]}',
        b'{"data": [{"index": 0}]}',
        json.dumps({"data": [{"index": 0, "embedding": vec(0)}], "error": {"message": "x"}}).encode(),
        b'{"data": [{"index": 0, "embedding": [NaN, 0, 0, 0]}]}',
    ]


@pytest.mark.parametrize("body", _malformed_embedding_bodies())
def test_embed_malformed_success_body(body: bytes) -> None:
    response = ScriptedResponse(200, body)
    with pytest.raises(ModelMalformedResponseError) as info:
        make_embed_client(ScriptedTransport(response)).embed(make_embed_request(("a",)))
    assert info.value.status_code == 200
    assert info.value.__cause__ is None and info.value.__context__ is None
    assert response.closed


def test_embed_oversized_body_is_malformed_and_closed() -> None:
    response = ScriptedResponse(200, embedding_body([vec(0)]))
    with pytest.raises(ModelMalformedResponseError):
        make_embed_client(ScriptedTransport(response), max_response_bytes=16).embed(make_embed_request(("a",)))
    assert response.closed


@pytest.mark.parametrize("status", [101, 204, 301])
def test_embed_non_200_non_error_status_is_malformed(status: int) -> None:
    with pytest.raises(ModelMalformedResponseError) as info:
        make_embed_client(ScriptedTransport(ScriptedResponse(status, b""))).embed(make_embed_request(("a",)))
    assert info.value.status_code == status


@pytest.mark.parametrize(("status", "error_type", "error_class"), STATUS_CASES)
def test_embed_http_status_maps_to_error_class(
    status: int, error_type: type[ModelCallError], error_class: ErrorClass
) -> None:
    response = ScriptedResponse(status, ERROR_BODY)
    with pytest.raises(error_type) as info:
        make_embed_client(ScriptedTransport(response)).embed(make_embed_request())
    error = info.value
    assert type(error) is error_type
    assert error.error_class is error_class
    assert error.status_code == status
    assert error.model == EMB_MODEL
    assert error.rejected_before_generation is (status in REJECTED_BEFORE_GENERATION_STATUSES)
    assert response.closed


def test_embed_rate_limit_keeps_retry_after_and_error_usage() -> None:
    body = json.dumps({"error": {"message": "x"}, "usage": {"prompt_tokens": 4, "total_tokens": 4}}).encode()
    response = ScriptedResponse(429, body, headers={"Retry-After": "7"})
    with pytest.raises(ModelRateLimitedError) as info:
        make_embed_client(ScriptedTransport(response)).embed(make_embed_request())
    assert info.value.retry_after_seconds == 7.0
    assert info.value.usage == Usage(4, 0)


def test_embed_failure_in_later_batch_returns_no_partial_result() -> None:
    transport = ScriptedTransport(ok_embed(2), ScriptedResponse(503, b"{}"))
    with pytest.raises(ModelServerError):
        make_embed_client(transport, batch_size=2).embed(make_embed_request(("a", "b", "c")))
    assert len(transport.calls) == 2


@pytest.mark.parametrize("exc", [TimeoutError("timed out"), socket.timeout("timed out")])
def test_embed_open_timeout_is_timeout(exc: BaseException) -> None:
    with pytest.raises(ModelTimeoutError) as info:
        make_embed_client(ScriptedTransport(exc)).embed(make_embed_request())
    assert info.value.status_code is None
    assert info.value.__cause__ is None and info.value.__context__ is None


def test_embed_body_read_timeout_is_timeout() -> None:
    response = ScriptedResponse(200, steps=[b'{"data": [', TimeoutError("read timed out")])
    with pytest.raises(ModelTimeoutError):
        make_embed_client(ScriptedTransport(response)).embed(make_embed_request())
    assert response.closed


def test_embed_total_deadline_bounds_a_slow_drip_response() -> None:
    clock = FakeClock()
    body = embedding_body([vec(0), vec(1)])
    response = ScriptedResponse(200, steps=[bytes([b]) for b in body], clock=clock, seconds_per_read=1.0)
    client = make_embed_client(ScriptedTransport(response), clock=clock, default_timeout_seconds=5.0)
    with pytest.raises(ModelTimeoutError):
        client.embed(make_embed_request())
    assert all(timeout <= 5.0 for timeout in response.read_timeouts)
    assert len(response.read_timeouts) <= 6


@pytest.mark.parametrize(
    "exc", [ConnectionRefusedError("refused"), socket.gaierror("dns"), http.client.RemoteDisconnected("gone")]
)
def test_embed_open_connection_failure_is_connection_error(exc: BaseException) -> None:
    with pytest.raises(ModelConnectionError):
        make_embed_client(ScriptedTransport(exc)).embed(make_embed_request())


@pytest.mark.parametrize("exc", [ConnectionResetError("reset"), http.client.IncompleteRead(b"")])
def test_embed_body_read_failure_is_connection_error(exc: BaseException) -> None:
    response = ScriptedResponse(200, steps=[b'{"data"', exc])
    with pytest.raises(ModelConnectionError):
        make_embed_client(ScriptedTransport(response)).embed(make_embed_request())
    assert response.closed


@pytest.mark.parametrize("batch_size", [0, -1, 11, True, 2.0, "2"])
def test_embed_batch_size_must_be_within_provider_limit(batch_size: Any) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        make_embed_client(ScriptedTransport(), batch_size=batch_size)


def test_embed_provider_limit_defaults_to_d02c_candidate_and_is_configurable() -> None:
    assert DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH == 10
    make_embed_client(ScriptedTransport(), batch_size=10)
    transport = ScriptedTransport(ok_embed(64))
    client = make_embed_client(transport, batch_size=64, provider_max_batch_size=2048)
    assert len(client.embed(make_embed_request(tuple(f"t{i}" for i in range(64)))).vectors) == 64
    assert len(transport.calls) == 1
    with pytest.raises(ValueError, match="provider_max_batch_size"):
        make_embed_client(ScriptedTransport(), batch_size=1, provider_max_batch_size=0)


@pytest.mark.parametrize("base_url", ["", "ftp://x.test", "https://user:pw@x.test/v1", "https://x.test/v1?key=1"])
def test_embed_invalid_base_url_rejected_without_echo(base_url: str) -> None:
    with pytest.raises(ValueError) as info:
        CompatibleEmbeddingClient(base_url, API_KEY, transport=ScriptedTransport())
    if base_url:
        assert base_url not in str(info.value)


@pytest.mark.parametrize("key", ["", "sk-abc\r\nX-Injected: 1", "sk-密钥", "sk abc"])
def test_embed_invalid_api_key_rejected_without_echo(key: str) -> None:
    with pytest.raises(ValueError) as info:
        CompatibleEmbeddingClient(BASE_URL, key, transport=ScriptedTransport())
    if key.strip():
        assert key not in str(info.value)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), True])
def test_embed_invalid_default_timeout_rejected(timeout: Any) -> None:
    with pytest.raises(ValueError):
        make_embed_client(ScriptedTransport(), default_timeout_seconds=timeout)


def test_embed_rejects_non_request() -> None:
    with pytest.raises(TypeError):
        make_embed_client(ScriptedTransport()).embed(make_request())  # type: ignore[arg-type]


def _embedding_settings(**extra: str) -> Any:
    env = {
        "EMBEDDING_MODE": "online",
        "EMBEDDING_BASE_URL": "https://dashscope.example.test/compatible-mode/v1",
        "EMBEDDING_API_KEY": "sk-embedding",
        "EMBEDDING_MODEL": EMB_MODEL,
        "EMBEDDING_DIMENSIONS": "4",
        "EMBEDDING_BATCH_SIZE": "3",
        "LLM_REQUEST_TIMEOUT_SECONDS": "19",
    }
    env.update(extra)
    return load_settings(env)


def test_embed_from_settings_uses_embedding_variables() -> None:
    transport = ScriptedTransport(ok_embed(3), ok_embed(1, start=3))
    client = CompatibleEmbeddingClient.from_settings(_embedding_settings(), transport=transport)
    client.embed(make_embed_request(("a", "b", "c", "d")))
    assert transport.calls[0]["url"] == "https://dashscope.example.test/compatible-mode/v1/embeddings"
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer sk-embedding"
    assert transport.calls[0]["timeout"] == 19.0
    assert [len(json.loads(call["body"])["input"]) for call in transport.calls] == [3, 1]


def test_embed_from_settings_missing_values_name_the_variable() -> None:
    settings = Settings(EMBEDDING_MODE="online", EMBEDDING_MODEL=EMB_MODEL)
    with pytest.raises(ValueError, match="EMBEDDING_BASE_URL"):
        CompatibleEmbeddingClient.from_settings(settings, transport=ScriptedTransport())


def test_embed_from_settings_batch_size_over_provider_limit_names_the_variable() -> None:
    with pytest.raises(ValueError, match="EMBEDDING_BATCH_SIZE"):
        CompatibleEmbeddingClient.from_settings(_embedding_settings(EMBEDDING_BATCH_SIZE="11"), transport=ScriptedTransport())
    client = CompatibleEmbeddingClient.from_settings(
        _embedding_settings(EMBEDDING_BATCH_SIZE="11"), transport=ScriptedTransport(), provider_max_batch_size=2048
    )
    assert isinstance(client, CompatibleEmbeddingClient)


def test_embed_no_key_text_or_vector_in_repr_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    leak = json.dumps({"error": {"message": f"{EMB_TEXT} {API_KEY}"}}, ensure_ascii=False).encode()
    short = embedding_body([[EMB_SECRET_VALUE, 0.0, 0.0]])
    request = make_embed_request((EMB_TEXT,))
    rendered: list[str] = [repr(request)]
    for transport in (
        ScriptedTransport(ScriptedResponse(400, leak)),
        ScriptedTransport(ScriptedResponse(200, short)),
        ScriptedTransport(ScriptedResponse(200, f"{EMB_TEXT} not json".encode())),
        ScriptedTransport(ConnectionRefusedError(API_KEY)),
    ):
        client = make_embed_client(transport)
        rendered.append(repr(client))
        with pytest.raises(ModelCallError) as info:
            client.embed(request)
        rendered.extend([str(info.value), repr(info.value), repr(info.value.args), repr(vars(info.value))])
    ok = make_embed_client(ScriptedTransport(ScriptedResponse(200, embedding_body([[EMB_SECRET_VALUE, 0, 0, 0]]))))
    rendered.append(repr(ok.embed(request)))
    rendered.append(caplog.text)
    blob = "\n".join(rendered)
    for secret in (API_KEY, EMB_TEXT, str(EMB_SECRET_VALUE)):
        assert secret not in blob
    assert caplog.records == []


# ---------------------------------------------------------------- embeddings through E07


def _e07_adapter(client: CompatibleEmbeddingClient, cache: EmbeddingCache | None = None) -> EmbeddingAdapter:
    settings = Settings(EMBEDDING_MODE="online", EMBEDDING_MODEL=EMB_MODEL, EMBEDDING_DIMENSIONS=4, EMBEDDING_BATCH_SIZE=2)
    return EmbeddingAdapter(settings, client, cache=cache)


def test_e07_adapter_over_compatible_client_keeps_order_and_space() -> None:
    transport = ScriptedTransport(ok_embed(2, order=[1, 0]), ok_embed(1, start=2))
    vectors = _e07_adapter(make_embed_client(transport, batch_size=2)).embed(["a", "b", "c"])
    assert [v.values for v in vectors] == [tuple(vec(0)), tuple(vec(1)), tuple(vec(2))]
    assert all(v.space == f"real/{EMB_MODEL}/4" for v in vectors)
    assert [json.loads(call["body"])["input"] for call in transport.calls] == [["a", "b"], ["c"]]


def test_e07_dimension_mismatch_from_provider_fails_the_batch_before_cache() -> None:
    cache = EmbeddingCache()
    transport = ScriptedTransport(
        ScriptedResponse(200, embedding_body([vec(0, 3)])),
        ok_embed(1),
    )
    service = _e07_adapter(make_embed_client(transport, batch_size=2), cache)
    with pytest.raises(EmbeddingBatchError) as info:
        service.embed(["a"])
    assert isinstance(info.value.__cause__, ModelMalformedResponseError)
    assert info.value.batch_index == 0 and info.value.completed_count == 0
    assert service.embed(["a"])[0].values == tuple(vec(0))
    assert len(transport.calls) == 2


def test_stdlib_transport_embeddings_over_loopback(loopback: str) -> None:
    _Handler.script = {"mode": "embeddings"}
    client = CompatibleEmbeddingClient(loopback, API_KEY, batch_size=2)
    result = client.embed(make_embed_request(("a", "b", "c"), dimensions=3))
    assert result.vectors == ((1.0, 1.0, 1.0), (2.0, 2.0, 2.0), (1.0, 1.0, 1.0))
    assert [seen["path"] for seen in _Handler.seen] == ["/v1/embeddings", "/v1/embeddings"]
    assert _Handler.seen[0]["body"] == {"model": EMB_MODEL, "input": ["a", "b"], "dimensions": 3, "encoding_format": "float"}
