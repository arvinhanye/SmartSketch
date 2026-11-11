"""Internal compatible_protocol responsibilities; public compatibility entry: app.services.ai.compatible."""

from __future__ import annotations

import http.client
import json
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final
from .client import (
    FINISH_REASONS,
    FinishReason,
    ModelAuthError,
    ModelCallError,
    ModelInvalidRequestError,
    ModelMalformedResponseError,
    ModelRateLimitedError,
    ModelRequest,
    ModelServerError,
    ModelTimeoutError,
    Usage,
)

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


# ---------------------------------------------------------------- parsing helpers

_TRANSPORT_ERRORS = (OSError, http.client.HTTPException)
_READ_SIZE: Final = 64 * 1024
MAX_ERROR_BODY_BYTES: Final = 64 * 1024
DEFAULT_MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
MAX_TOKENS_FIELDS: Final = frozenset({"max_tokens", "max_completion_tokens"})
# docs/integrations.md D-02c: the only candidate so far (text-embedding-v4) takes at most
# 10 texts per request. D-02c is not signed, so this is a default, not a constant of the
# protocol: callers pass ``provider_max_batch_size`` for another provider.
DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH: Final = 10


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
    details = value.get("completion_tokens_details")
    reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
    # ADR-089: optional; an unparseable count is dropped without discarding the usage itself
    return Usage(prompt, completion, reasoning_tokens=reasoning if _is_count(reasoning) else None)


#: ADR-090: request fields an ``extra_body`` may never replace
CORE_PAYLOAD_FIELDS: Final = frozenset({"model", "messages", "stream", "stream_options", "response_format"}) | MAX_TOKENS_FIELDS


def _plain_copy(value: Any) -> Any:
    """Deep copy into plain JSON types (mappings → dict, sequences → list)."""
    if isinstance(value, Mapping):
        return {str(key): _plain_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_copy(item) for item in value]
    return value


#: ADR-090: the only thinking switch verified on a real provider (C02b probe, DeepSeek)
THINKING_DISABLED: Final = MappingProxyType({"thinking": MappingProxyType({"type": "disabled"})})

def thinking_body(disable_thinking: bool) -> Mapping[str, Any] | None:
    """ADR-090: the ``extra_body`` for a user's switch; ``None`` (nothing added) when it is off."""
    return THINKING_DISABLED if disable_thinking else None


#: ADR-089: fields providers use for (non-answer) reasoning text; only their length is kept
REASONING_FIELDS: Final = ("reasoning_content", "reasoning")


def _reasoning_chars(container: dict[str, Any]) -> int:
    return sum(len(text) for name in REASONING_FIELDS if isinstance(text := container.get(name), str))


def _parse_embedding_usage(value: object) -> Usage | None:
    """Embeddings report ``prompt_tokens`` and ``total_tokens`` only; no output tokens."""

    if not isinstance(value, dict):
        return None
    for name in ("prompt_tokens", "total_tokens"):
        tokens = value.get(name)
        if type(tokens) is int and tokens >= 0:  # rejects bool, floats and negatives
            return Usage(tokens, 0)
    return None


def _vector_component(value: object) -> float | None:
    """A finite JSON number as float, else ``None`` (bool, strings, NaN/inf, ints beyond float)."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


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
