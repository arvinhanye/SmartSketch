"""Model interface shared by every adapter (E02): requests, results, errors, protocols.

Adapters (``fake.py`` here, the compatible HTTP adapter in E03) only translate one
request into one provider call. Retries, fallback switching, circuit breaking, budgets
and ``model_calls`` bookkeeping belong to E04 (``docs/integrations.md``「模型接入规则」),
which wraps an adapter and reads the facts exposed here:

- ``ModelRequest.max_output_tokens`` is mandatory: every LLM request declares its output
  ceiling, used for the pre-write estimate (ADR-011 修订 2).
- ``ModelResult`` carries ``model_requested`` and ``model_responded`` (the ``model`` field
  of the response) plus ``usage`` (``None`` when the response has no parseable usage).
- ``ModelCallError`` subclasses name the switching-matrix row they belong to through
  ``error_class``; ``rejected_before_generation`` is the ADR-011 修订 3 status set.
- Bad model *output* (e.g. invalid JSON) is not a call failure: the call succeeded and is
  billable. ``ModelResult.json()`` raises ``ModelOutputError`` with the result attached so
  E05 can run its single repair call.

The interface is synchronous. Streams are generators: errors surface while iterating,
and callers stop early with ``close()``.

Nothing here logs, and no repr or error message contains prompt text, model output or
vectors: those are course material or student questions (E04 验收「日志无 token/原文」).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]
ResponseFormat = Literal["text", "json"]
FinishReason = Literal["stop", "length"]

ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})
RESPONSE_FORMATS: frozenset[str] = frozenset({"text", "json"})
FINISH_REASONS: frozenset[str] = frozenset({"stop", "length"})

# docs/integrations.md「调用记录」第 5 条（ADR-011 修订 3）：生成前被拒、不产生计费用量。
REJECTED_BEFORE_GENERATION_STATUSES: frozenset[int] = frozenset({400, 401, 403, 404, 413, 422, 429})

_PURPOSE = re.compile(r"[a-z][a-z0-9_]*")


def _is_int(value: object) -> bool:
    return type(value) is int


def _check_model_id(value: object, owner: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{owner}: model must be a non-empty string")


# ---------------------------------------------------------------- requests and results


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"Message: role must be one of {sorted(ROLES)}")
        if not isinstance(self.content, str):
            raise ValueError("Message: content must be str")


@dataclass(frozen=True)
class ModelRequest:
    """One LLM call. ``purpose`` names the caller (prompt purpose, ``repair`` …) for audits."""

    purpose: str
    model: str
    messages: tuple[Message, ...]
    max_output_tokens: int
    response_format: ResponseFormat = "text"
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, str) or not _PURPOSE.fullmatch(self.purpose):
            raise ValueError("ModelRequest: purpose must be a lowercase identifier")
        _check_model_id(self.model, "ModelRequest")
        messages = tuple(self.messages) if isinstance(self.messages, Iterable) else ()
        if not messages or not all(isinstance(message, Message) for message in messages):
            raise ValueError("ModelRequest: messages must be a non-empty sequence of Message")
        object.__setattr__(self, "messages", messages)
        if not _is_int(self.max_output_tokens) or self.max_output_tokens < 1:
            raise ValueError("ModelRequest: max_output_tokens must be an int >= 1")
        if self.response_format not in RESPONSE_FORMATS:
            raise ValueError(f"ModelRequest: response_format must be one of {sorted(RESPONSE_FORMATS)}")
        timeout = self.timeout_seconds
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("ModelRequest: timeout_seconds must be a finite number > 0")


@dataclass(frozen=True)
class Usage:
    """Token usage as reported by the provider (or by the fake's documented rule)."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if not _is_int(value) or value < 0:
                raise ValueError(f"Usage: {name} must be an int >= 0")

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ModelResult:
    text: str = field(repr=False)
    model_requested: str
    model_responded: str | None
    usage: Usage | None
    finish_reason: FinishReason

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise ValueError("ModelResult: text must be str")
        _check_model_id(self.model_requested, "ModelResult")
        if self.model_responded is not None and not isinstance(self.model_responded, str):
            raise ValueError("ModelResult: model_responded must be str or None")
        if self.usage is not None and not isinstance(self.usage, Usage):
            raise ValueError("ModelResult: usage must be Usage or None")
        if self.finish_reason not in FINISH_REASONS:
            raise ValueError(f"ModelResult: finish_reason must be one of {sorted(FINISH_REASONS)}")

    def json(self) -> Any:
        """Parse ``text`` as strict JSON (no NaN/Infinity); schema checks stay with the caller."""

        def reject_constant(name: str) -> Any:
            raise ValueError(name)

        try:
            return json.loads(self.text, parse_constant=reject_constant)
        except ValueError:
            raise ModelOutputError("invalid_json", self) from None


@dataclass(frozen=True)
class StreamDelta:
    text: str = field(repr=False)


@dataclass(frozen=True)
class StreamDone:
    """Last event of a successful stream; ``result.text`` equals the concatenated deltas."""

    result: ModelResult


StreamEvent = StreamDelta | StreamDone


@dataclass(frozen=True)
class EmbeddingRequest:
    """One vector call. ``dimensions`` is sent to the provider (``EMBEDDING_DIMENSIONS``)."""

    model: str
    texts: tuple[str, ...] = field(repr=False)
    dimensions: int

    def __post_init__(self) -> None:
        _check_model_id(self.model, "EmbeddingRequest")
        texts = tuple(self.texts) if isinstance(self.texts, Iterable) and not isinstance(self.texts, str) else ()
        if not texts or not all(isinstance(text, str) for text in texts):
            raise ValueError("EmbeddingRequest: texts must be a non-empty sequence of str")
        object.__setattr__(self, "texts", texts)
        if not _is_int(self.dimensions) or self.dimensions < 1:
            raise ValueError("EmbeddingRequest: dimensions must be an int >= 1")


@dataclass(frozen=True)
class EmbeddingResult:
    """Vectors in input order, as returned; length and dimension checks belong to E07."""

    vectors: tuple[tuple[float, ...], ...] = field(repr=False)
    model_requested: str
    model_responded: str | None
    usage: Usage | None


# ---------------------------------------------------------------- errors


class ErrorClass(StrEnum):
    """Adapter-level failure categories, one per row of the A07 switching matrix."""

    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMITED = "rate_limited"
    SERVER = "server"
    AUTH = "auth"
    INVALID_REQUEST = "invalid_request"
    STREAM_INTERRUPTED = "stream_interrupted"
    MALFORMED_RESPONSE = "malformed_response"


class ModelError(Exception):
    """Base class for every model-layer error."""


class ModelCallError(ModelError):
    """The provider call failed. Messages name the model and status only, never content."""

    error_class: ErrorClass
    default_status: int | None = None

    def __init__(self, model: str, *, status_code: int | None = None, usage: Usage | None = None) -> None:
        _check_model_id(model, type(self).__name__)
        if status_code is None:
            status_code = self.default_status
        if status_code is not None and (not _is_int(status_code) or not self._status_allowed(status_code)):
            raise ValueError(f"{type(self).__name__}: status_code {status_code!r} does not fit {self.error_class}")
        if usage is not None and not isinstance(usage, Usage):
            raise ValueError(f"{type(self).__name__}: usage must be Usage or None")
        self.model = model
        self.status_code = status_code
        self.usage = usage
        status = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"{self.error_class} from model {model!r}{status}")

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return False

    @property
    def rejected_before_generation(self) -> bool:
        return self.status_code in REJECTED_BEFORE_GENERATION_STATUSES


class ModelTimeoutError(ModelCallError):
    """No complete response in time (client-side timeout, or HTTP 408)."""

    error_class = ErrorClass.TIMEOUT

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return status == 408


class ModelConnectionError(ModelCallError):
    """The connection could not be made or was lost before a response arrived."""

    error_class = ErrorClass.CONNECTION


class ModelRateLimitedError(ModelCallError):
    error_class = ErrorClass.RATE_LIMITED
    default_status = 429

    def __init__(
        self,
        model: str,
        *,
        status_code: int | None = None,
        usage: Usage | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(model, status_code=status_code, usage=usage)
        if retry_after_seconds is not None and (
            isinstance(retry_after_seconds, bool)
            or not isinstance(retry_after_seconds, int | float)
            or not math.isfinite(retry_after_seconds)
            or retry_after_seconds < 0
        ):
            raise ValueError("ModelRateLimitedError: retry_after_seconds must be a finite number >= 0")
        self.retry_after_seconds = retry_after_seconds

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return status == 429


class ModelServerError(ModelCallError):
    error_class = ErrorClass.SERVER
    default_status = 500

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return 500 <= status <= 599


class ModelAuthError(ModelCallError):
    error_class = ErrorClass.AUTH
    default_status = 401

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return status in (401, 403)


class ModelInvalidRequestError(ModelCallError):
    """Parameter errors (unknown model, context too long, …): any 4xx not covered above."""

    error_class = ErrorClass.INVALID_REQUEST
    default_status = 400

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return 400 <= status <= 499 and status not in (401, 403, 408, 429)


class ModelStreamInterruptedError(ModelCallError):
    """A stream broke off after it started; whether text was shown is the caller's record."""

    error_class = ErrorClass.STREAM_INTERRUPTED


class ModelMalformedResponseError(ModelCallError):
    """The response could not be parsed at the protocol level (not a content-quality issue)."""

    error_class = ErrorClass.MALFORMED_RESPONSE

    @classmethod
    def _status_allowed(cls, status: int) -> bool:
        return 100 <= status <= 599


class ModelOutputError(ModelError):
    """The call succeeded but the output does not meet the requested format."""

    def __init__(self, reason: str, result: ModelResult) -> None:
        self.reason = reason
        self.result = result
        super().__init__(f"model output rejected: {reason} (model {result.model_requested!r})")


# ---------------------------------------------------------------- protocols


@runtime_checkable
class ModelClient(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult: ...

    def stream(self, request: ModelRequest) -> Generator[StreamEvent, None, None]: ...


@runtime_checkable
class EmbeddingClient(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


__all__ = [
    "FINISH_REASONS",
    "REJECTED_BEFORE_GENERATION_STATUSES",
    "RESPONSE_FORMATS",
    "ROLES",
    "EmbeddingClient",
    "EmbeddingRequest",
    "EmbeddingResult",
    "ErrorClass",
    "FinishReason",
    "Message",
    "ModelAuthError",
    "ModelCallError",
    "ModelClient",
    "ModelConnectionError",
    "ModelError",
    "ModelInvalidRequestError",
    "ModelMalformedResponseError",
    "ModelOutputError",
    "ModelRateLimitedError",
    "ModelRequest",
    "ModelResult",
    "ModelServerError",
    "ModelStreamInterruptedError",
    "ModelTimeoutError",
    "ResponseFormat",
    "Role",
    "StreamDelta",
    "StreamDone",
    "StreamEvent",
    "Usage",
]
