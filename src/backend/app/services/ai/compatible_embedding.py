"""Internal compatible_embedding responsibilities; public compatibility entry: app.services.ai.compatible."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from .client import EmbeddingRequest, EmbeddingResult, ModelTimeoutError, Usage
from app.services.ai.compatible_base import (
    _CompatibleHttpClient,
)
from app.services.ai.compatible_protocol import (
    DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH,
    DEFAULT_MAX_RESPONSE_BYTES,
    _Fail,
    _malformed,
    _parse_embedding_usage,
    _parse_model,
    _vector_component,
)
from app.services.ai.compatible_transport import (
    HttpTransport,
)

if TYPE_CHECKING:
    from app.config import Settings

# ---------------------------------------------------------------- embeddings adapter


class CompatibleEmbeddingClient(_CompatibleHttpClient):
    """``EmbeddingClient`` for one OpenAI-compatible provider (ADR-017 决定 2).

    ``batch_size`` is ``EMBEDDING_BATCH_SIZE``; ``provider_max_batch_size`` is the
    provider's per-request limit (default: the D-02c candidate's 10). E07 already cuts
    its batches at ``EMBEDDING_BATCH_SIZE``, so with the same value each E07 batch is
    exactly one HTTP call; the split here only protects callers that do not batch.
    """

    _path = "/embeddings"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        batch_size: int = DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH,
        provider_max_batch_size: int = DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH,
        transport: HttpTransport | None = None,
        default_timeout_seconds: float = 60.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            base_url,
            api_key,
            transport=transport,
            default_timeout_seconds=default_timeout_seconds,
            max_response_bytes=max_response_bytes,
            clock=clock,
        )
        if type(provider_max_batch_size) is not int or provider_max_batch_size < 1:
            raise ValueError("CompatibleEmbeddingClient: provider_max_batch_size must be an int >= 1")
        if type(batch_size) is not int or not 1 <= batch_size <= provider_max_batch_size:
            raise ValueError(
                "CompatibleEmbeddingClient: batch_size (EMBEDDING_BATCH_SIZE) must be an int from 1 to the "
                f"provider limit {provider_max_batch_size}"
            )
        self._batch_size = batch_size

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        provider_max_batch_size: int = DEFAULT_EMBEDDING_PROVIDER_MAX_BATCH,
        transport: HttpTransport | None = None,
    ) -> CompatibleEmbeddingClient:
        """``EMBEDDING_BASE_URL`` / ``EMBEDDING_API_KEY`` / ``EMBEDDING_BATCH_SIZE``.

        There is no embedding-specific timeout variable; ``LLM_REQUEST_TIMEOUT_SECONDS``
        bounds each HTTP call (docs/handoffs/claude-e03.md, 待决).
        """

        base_url = settings.EMBEDDING_BASE_URL
        api_key = settings.EMBEDDING_API_KEY.get_secret_value()
        if not base_url.strip() or not api_key.strip():
            raise ValueError("CompatibleEmbeddingClient: EMBEDDING_BASE_URL and EMBEDDING_API_KEY are required")
        return cls(
            base_url,
            api_key,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            provider_max_batch_size=provider_max_batch_size,
            transport=transport,
            default_timeout_seconds=settings.LLM_REQUEST_TIMEOUT_SECONDS,
        )

    def _usage_from(self, value: object) -> Usage | None:
        return _parse_embedding_usage(value)

    # -- EmbeddingClient

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        if not isinstance(request, EmbeddingRequest):
            raise TypeError("request must be an EmbeddingRequest")
        try:
            return self._embed(request)
        except _Fail as fail:
            error = fail.error
        raise error from None

    def _embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        model = request.model
        vectors: list[tuple[float, ...]] = []
        input_tokens: int | None = 0
        responded: str | None = None
        # A QA deadline budget is shared by every batch of this request (ADR-082 决定 3).
        budget_end = None if request.timeout_seconds is None else self._clock() + request.timeout_seconds
        for start in range(0, len(request.texts), self._batch_size):
            batch = request.texts[start : start + self._batch_size]
            timeout = self._default_timeout
            if budget_end is not None:
                remaining = budget_end - self._clock()
                if remaining <= 0:
                    raise _Fail(ModelTimeoutError(model))
                timeout = min(timeout, remaining)
            batch_vectors, usage, batch_model, status = self._embed_batch(request, batch, timeout)
            if batch_model is not None:
                if responded is not None and batch_model != responded:
                    raise _Fail(_malformed(model, status, usage))
                responded = batch_model
            input_tokens = None if input_tokens is None or usage is None else input_tokens + usage.input_tokens
            vectors.extend(batch_vectors)
        return EmbeddingResult(
            vectors=tuple(vectors),
            model_requested=model,
            model_responded=responded,
            usage=None if input_tokens is None else Usage(input_tokens, 0),
        )

    def _embed_batch(
        self, request: EmbeddingRequest, batch: tuple[str, ...], timeout: float
    ) -> tuple[list[tuple[float, ...]], Usage | None, str | None, int]:
        model = request.model
        payload = {
            "model": model,
            "input": list(batch),
            "dimensions": request.dimensions,
            "encoding_format": "float",
        }
        response, deadline = self._post(payload, model, timeout, accept="application/json")
        parsed, status = self._read_json(response, deadline, model)
        usage = _parse_embedding_usage(parsed.get("usage"))
        if parsed.get("error") is not None:
            raise _Fail(_malformed(model, status, usage))
        data = parsed.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            raise _Fail(_malformed(model, status, usage))
        slots: list[tuple[float, ...] | None] = [None] * len(batch)
        for item in data:
            if not isinstance(item, dict):
                raise _Fail(_malformed(model, status, usage))
            index = item.get("index")
            if type(index) is not int or not 0 <= index < len(batch) or slots[index] is not None:
                raise _Fail(_malformed(model, status, usage))
            values = item.get("embedding")
            # Same criterion as E07 (app/services/ai/embeddings.py): exact length, finite numbers.
            if not isinstance(values, list) or len(values) != request.dimensions:
                raise _Fail(_malformed(model, status, usage))
            vector: list[float] = []
            for value in values:
                component = _vector_component(value)
                if component is None:
                    raise _Fail(_malformed(model, status, usage))
                vector.append(component)
            slots[index] = tuple(vector)
        return [vector for vector in slots if vector is not None], usage, _parse_model(parsed.get("model")), status
