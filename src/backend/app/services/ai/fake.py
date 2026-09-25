"""Deterministic fake adapters (E02) for ``LLM_MODE=fake`` / ``EMBEDDING_MODE=fake`` and tests.

No network, keys, settings or clock. Same request → same result, across processes
(sha256, never ``hash()``).

Behaviour of ``FakeModelClient``:

- Each call takes the next scripted step: first from the queue of its ``purpose`` (if any),
  then from the general queue; when both are empty it asks ``responder`` or falls back to
  the default output. A step is a ``str`` (reply text), a ``FakeReply`` or a
  ``ModelCallError`` instance (raised: timeout, 429, 5xx, auth …).
- Default output: ``[fake <purpose> <digest>]`` in text mode, a JSON object with
  ``fake``/``purpose``/``digest`` in JSON mode; ``digest`` covers purpose, model,
  response format and every message.
- The declared ``max_output_tokens`` is honoured: output is cut to that many characters
  and ``finish_reason`` becomes ``"length"``.
- Simulated usage (docs/integrations.md「预算」: fake 按确定规则上报模拟 usage): one token per
  character — input = characters of all message contents, output = characters returned.
  This is a fake rule, not a tokenizer estimate. ``FakeReply(usage=None)`` simulates a
  response without usage; ``FakeReply(usage=Usage(...))`` fixes it.
- ``model_responded`` echoes the requested model unless the reply overrides it.
- Streams yield the reply ``chunks`` (or the text cut into ``stream_chunk_chars`` pieces)
  then ``StreamDone``. ``FakeReply(error_after_chunks=(n, error))`` raises after ``n``
  deltas (``complete()`` raises it regardless of ``n``); a stream closed early is recorded.
- ``calls`` records every call with its request, outcome, delivered chunks and early close.

Bad JSON is simulated with an ordinary text reply such as ``BAD_JSON_TEXT``: the call
succeeds and ``ModelResult.json()`` raises ``ModelOutputError``.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Final, Literal

from .client import (
    EmbeddingRequest,
    EmbeddingResult,
    FinishReason,
    ModelCallError,
    ModelRequest,
    ModelResult,
    StreamDelta,
    StreamDone,
    StreamEvent,
    Usage,
)

BAD_JSON_TEXT: Final = '{"entities": [{"name": "栈", "type": "concept"'


class _Auto:
    """Sentinel: let the fake derive the value (simulated usage, echoed model ID)."""

    _instance: _Auto | None = None

    def __new__(cls) -> _Auto:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "AUTO"


AUTO: Final = _Auto()


def _check_error_after(value: object, chunks: tuple[str, ...] | None) -> None:
    if value is None:
        return
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError("FakeReply: error_after_chunks must be (count, ModelCallError)")
    count, error = value
    if not isinstance(error, ModelCallError):
        raise TypeError("FakeReply: error_after_chunks error must be a ModelCallError")
    if type(count) is not int or count < 0:
        raise ValueError("FakeReply: error_after_chunks count must be an int >= 0")
    if chunks is not None and count > len(chunks):
        raise ValueError("FakeReply: error_after_chunks count exceeds the number of chunks")


@dataclass(frozen=True)
class FakeReply:
    text: str | None = field(default=None, repr=False)
    chunks: tuple[str, ...] | None = field(default=None, repr=False)
    usage: Usage | None | _Auto = AUTO
    model_responded: str | None | _Auto = AUTO
    error_after_chunks: tuple[int, ModelCallError] | None = None

    def __post_init__(self) -> None:
        chunks = self.chunks
        if chunks is not None:
            chunks = tuple(chunks)
            if not all(isinstance(chunk, str) for chunk in chunks):
                raise ValueError("FakeReply: chunks must be str")
            object.__setattr__(self, "chunks", chunks)
        if self.text is None:
            if chunks is None:
                raise ValueError("FakeReply: give text or chunks")
            object.__setattr__(self, "text", "".join(chunks))
        elif not isinstance(self.text, str):
            raise ValueError("FakeReply: text must be str")
        elif chunks is not None and "".join(chunks) != self.text:
            raise ValueError("FakeReply: chunks must concatenate to text")
        if not isinstance(self.usage, Usage | _Auto) and self.usage is not None:
            raise ValueError("FakeReply: usage must be Usage, None or AUTO")
        if not isinstance(self.model_responded, str | _Auto) and self.model_responded is not None:
            raise ValueError("FakeReply: model_responded must be str, None or AUTO")
        _check_error_after(self.error_after_chunks, chunks)


@dataclass(frozen=True)
class FakeEmbedding:
    vectors: tuple[tuple[float, ...], ...] = field(repr=False)
    usage: Usage | None | _Auto = AUTO
    model_responded: str | None | _Auto = AUTO

    def __post_init__(self) -> None:
        try:
            vectors = tuple(tuple(float(x) for x in vector) for vector in self.vectors)
        except (TypeError, ValueError):
            raise ValueError("FakeEmbedding: vectors must be sequences of numbers") from None
        object.__setattr__(self, "vectors", vectors)


@dataclass
class FakeCall:
    """One recorded call. ``outcome`` is ``ok``, an ``ErrorClass`` value, ``closed`` or ``pending``."""

    kind: Literal["complete", "stream", "embed"]
    request: ModelRequest | EmbeddingRequest
    outcome: str = "pending"
    chunks_delivered: int = 0
    closed_early: bool = False


Step = str | FakeReply | ModelCallError
Responder = Callable[[ModelRequest], Step]


def _check_step(step: object) -> None:
    if not isinstance(step, str | FakeReply | ModelCallError):
        raise TypeError("script steps must be str, FakeReply or ModelCallError")


def _digest(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _input_chars(request: ModelRequest) -> int:
    return sum(len(message.content) for message in request.messages)


def default_text(request: ModelRequest) -> str:
    digest = _digest(
        request.purpose,
        request.model,
        request.response_format,
        [[message.role, message.content] for message in request.messages],
    )[:16]
    if request.response_format == "json":
        return json.dumps({"digest": digest, "fake": True, "purpose": request.purpose}, sort_keys=True)
    return f"[fake {request.purpose} {digest}]"


class FakeModelClient:
    def __init__(self, *, responder: Responder | None = None, stream_chunk_chars: int = 8) -> None:
        if type(stream_chunk_chars) is not int or stream_chunk_chars < 1:
            raise ValueError("stream_chunk_chars must be an int >= 1")
        self._responder = responder
        self._chunk_chars = stream_chunk_chars
        self._lock = threading.Lock()
        self._general: deque[Step] = deque()
        self._by_purpose: dict[str, deque[Step]] = {}
        self._calls: list[FakeCall] = []

    # -- scripting and inspection

    def script(self, *steps: Step, purpose: str | None = None) -> None:
        for step in steps:
            _check_step(step)
        with self._lock:
            queue = self._general if purpose is None else self._by_purpose.setdefault(purpose, deque())
            queue.extend(steps)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._general) + sum(len(queue) for queue in self._by_purpose.values())

    @property
    def calls(self) -> tuple[FakeCall, ...]:
        with self._lock:
            return tuple(self._calls)

    # -- ModelClient

    def complete(self, request: ModelRequest) -> ModelResult:
        call, step = self._begin("complete", request)
        if isinstance(step, ModelCallError):
            call.outcome = step.error_class.value
            raise step
        try:
            _, result, error_after = self._build(request, step)
        except ModelCallError as error:  # raised by the responder
            call.outcome = error.error_class.value
            raise
        if error_after is not None:
            call.outcome = error_after[1].error_class.value
            raise error_after[1]
        call.outcome = "ok"
        return result

    def stream(self, request: ModelRequest) -> Generator[StreamEvent, None, None]:
        call, step = self._begin("stream", request)
        return self._stream(call, request, step)

    # -- internals

    def _begin(self, kind: Literal["complete", "stream"], request: ModelRequest) -> tuple[FakeCall, Step | None]:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        with self._lock:
            call = FakeCall(kind, request)
            self._calls.append(call)
            queue = self._by_purpose.get(request.purpose)
            if queue:
                return call, queue.popleft()
            if self._general:
                return call, self._general.popleft()
        return call, None

    def _build(
        self, request: ModelRequest, step: Step | None
    ) -> tuple[tuple[str, ...], ModelResult, tuple[int, ModelCallError] | None]:
        if step is None:
            step = self._responder(request) if self._responder is not None else default_text(request)
            _check_step(step)
            if isinstance(step, ModelCallError):
                raise step
        reply = FakeReply(step) if isinstance(step, str) else step
        assert isinstance(reply, FakeReply) and reply.text is not None
        if reply.chunks is not None:
            full = reply.chunks
        else:
            size = self._chunk_chars
            full = tuple(reply.text[i : i + size] for i in range(0, len(reply.text), size))
        limit = request.max_output_tokens
        chunks: list[str] = []
        used = 0
        for chunk in full:
            if used >= limit:
                break
            piece = chunk[: limit - used]
            chunks.append(piece)
            used += len(piece)
        text = "".join(chunks)
        finish_reason: FinishReason = "length" if len(reply.text) > limit else "stop"
        usage = Usage(_input_chars(request), len(text)) if isinstance(reply.usage, _Auto) else reply.usage
        model_responded = request.model if isinstance(reply.model_responded, _Auto) else reply.model_responded
        result = ModelResult(
            text=text,
            model_requested=request.model,
            model_responded=model_responded,
            usage=usage,
            finish_reason=finish_reason,
        )
        return tuple(chunks), result, reply.error_after_chunks

    def _stream(self, call: FakeCall, request: ModelRequest, step: Step | None) -> Generator[StreamEvent, None, None]:
        done_sent = False
        try:
            if isinstance(step, ModelCallError):
                call.outcome = step.error_class.value
                raise step
            try:
                chunks, result, error_after = self._build(request, step)
            except ModelCallError as error:  # raised by the responder
                call.outcome = error.error_class.value
                raise
            fail_at = error_after[0] if error_after is not None else None
            for index, chunk in enumerate(chunks):
                if fail_at is not None and index == fail_at:
                    break
                call.chunks_delivered += 1
                yield StreamDelta(chunk)
            if error_after is not None:
                call.outcome = error_after[1].error_class.value
                raise error_after[1]
            call.outcome = "ok"
            done_sent = True
            yield StreamDone(result)
        except GeneratorExit:
            if not done_sent:
                call.closed_early = True
                call.outcome = "closed"
            raise


def _fake_vector(model: str, dimensions: int, text: str) -> tuple[float, ...]:
    seed = _digest("embedding", model, dimensions, text).encode("ascii")
    values: list[float] = []
    block = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(seed + block.to_bytes(4, "big")).digest()
        for offset in range(0, 32, 8):
            values.append(int.from_bytes(digest[offset : offset + 8], "big") / 2**63 - 1.0)
        block += 1
    values = values[:dimensions]
    norm = math.sqrt(sum(x * x for x in values))
    if norm == 0:  # pragma: no cover - would need an all-zero sha256 output
        return tuple(1.0 if i == 0 else 0.0 for i in range(dimensions))
    return tuple(x / norm for x in values)


EmbeddingStep = FakeEmbedding | ModelCallError


class FakeEmbeddingClient:
    """Deterministic unit vectors of ``request.dimensions`` per (model, dimensions, text)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: deque[EmbeddingStep] = deque()
        self._calls: list[FakeCall] = []

    def script(self, *steps: EmbeddingStep) -> None:
        for step in steps:
            if not isinstance(step, FakeEmbedding | ModelCallError):
                raise TypeError("embedding script steps must be FakeEmbedding or ModelCallError")
        with self._lock:
            self._queue.extend(steps)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def calls(self) -> tuple[FakeCall, ...]:
        with self._lock:
            return tuple(self._calls)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        if not isinstance(request, EmbeddingRequest):
            raise TypeError("request must be an EmbeddingRequest")
        with self._lock:
            call = FakeCall("embed", request)
            self._calls.append(call)
            step = self._queue.popleft() if self._queue else None
        if isinstance(step, ModelCallError):
            call.outcome = step.error_class.value
            raise step
        if step is None:
            step = FakeEmbedding(
                vectors=tuple(_fake_vector(request.model, request.dimensions, text) for text in request.texts)
            )
        usage = Usage(sum(len(text) for text in request.texts), 0) if isinstance(step.usage, _Auto) else step.usage
        model_responded = request.model if isinstance(step.model_responded, _Auto) else step.model_responded
        call.outcome = "ok"
        return EmbeddingResult(
            vectors=step.vectors,
            model_requested=request.model,
            model_responded=model_responded,
            usage=usage,
        )


__all__ = [
    "AUTO",
    "BAD_JSON_TEXT",
    "FakeCall",
    "FakeEmbedding",
    "FakeEmbeddingClient",
    "FakeModelClient",
    "FakeReply",
    "default_text",
]
