"""E07 embedding batches with explicit vector-space labels and validation."""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from contextvars import ContextVar

from app.config import Settings, embedding_model_id
from app.repositories.model_calls import EMBEDDING_PURPOSE, CallOutcome, CallRecord
from app.services.ai.client import EmbeddingClient, EmbeddingRequest, ModelCallError
from app.services.ai.policy import CallStore, new_call_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddedVector:
    """A vector and the space required for a safe repository write."""

    values: tuple[float, ...] = field(repr=False)
    model: str
    dimensions: int
    space: str
    text_hash: str


class EmbeddingBatchError(RuntimeError):
    """The batch failed without returning a partial vector list."""

    def __init__(self, reason: str, batch_index: int, completed_count: int) -> None:
        self.batch_index = batch_index
        self.completed_count = completed_count
        super().__init__(
            f"embedding batch {batch_index} failed ({reason}); "
            f"{completed_count} vectors completed"
        )


class EmbeddingDeadlineExceeded(EmbeddingBatchError):
    """The caller's deadline left no time for (another) embedding request."""


class EmbeddingRecordError(EmbeddingBatchError):
    """The ``model_calls`` prewrite failed, so the request was not sent."""


@dataclass(frozen=True)
class EmbeddingCallScope:
    """Who a shared vector call belongs to (ADR-082 决定 6): the course and the QA request or publish."""

    course_id: str
    request_id: str
    user_id: str | None = None


_CALL_SCOPE: ContextVar[EmbeddingCallScope | None] = ContextVar("embedding_call_scope", default=None)


@contextmanager
def embedding_calls(*, course_id: str, request_id: str, user_id: str | None = None) -> Iterator[None]:
    """Attribute every vector request made in this context (``model_calls`` course/request columns)."""
    if not course_id or not request_id:
        raise ValueError("course_id and request_id are required")
    token = _CALL_SCOPE.set(EmbeddingCallScope(course_id, request_id, user_id))
    try:
        yield
    finally:
        _CALL_SCOPE.reset(token)


class EmbeddingCache:
    """Bounded process-local LRU cache partitioned by vector space."""

    def __init__(self, max_entries: int = 1024) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], EmbeddedVector] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, space: str, text_hash: str) -> EmbeddedVector | None:
        with self._lock:
            key = (space, text_hash)
            vector = self._entries.get(key)
            if vector is not None:
                self._entries.move_to_end(key)
            return vector

    def put_batch(self, vectors: Sequence[EmbeddedVector]) -> None:
        with self._lock:
            for vector in vectors:
                key = (vector.space, vector.text_hash)
                self._entries[key] = vector
                self._entries.move_to_end(key)
                if len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)

    def clear_space(self, space: str) -> None:
        with self._lock:
            for key in tuple(self._entries):
                if key[0] == space:
                    del self._entries[key]


class EmbeddingAdapter:
    """Batch an injected E02 client and validate every response before caching."""

    def __init__(
        self,
        settings: Settings,
        client: EmbeddingClient,
        *,
        cache: EmbeddingCache | None = None,
        store: CallStore | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._cache = cache if cache is not None else EmbeddingCache()
        is_fake = settings.EMBEDDING_MODE == "fake"
        # demo 用保留模型 ID，自成 ``real/<ID>/<维度>`` 空间（ADR-076）
        self._model = embedding_model_id(settings)
        if not self._model:
            raise ValueError("EMBEDDING_MODEL is required for online/local embedding")
        self._dimensions = settings.EMBEDDING_DIMENSIONS
        self._batch_size = settings.EMBEDDING_BATCH_SIZE
        self.space = (
            f"fake/{self._dimensions}" if is_fake else f"real/{self._model}/{self._dimensions}"
        )

    @property
    def records_calls(self) -> bool:
        """With a store, every real request is prewritten and finished in ``model_calls`` (ADR-082 决定 6)."""
        return self._store is not None

    def _prewrite(self, texts: tuple[str, ...], batch_index: int, completed: int) -> str | None:
        if self._store is None:
            return None
        scope = _CALL_SCOPE.get()
        if scope is None:
            raise RuntimeError("a recording EmbeddingAdapter needs embedding_calls(course_id=..., request_id=...)")
        call_id = new_call_id()
        record = CallRecord(
            call_id=call_id, course_id=scope.course_id, task_id=None, chunk_id=None, request_id=scope.request_id,
            purpose=EMBEDDING_PURPOSE, task_attempt=None, chunk_attempt=None, call_seq=None,
            provider_role="primary", is_repair=False, model_requested=self._model,
            # E03 口径：按 UTF-8 字节数估算输入 token（只会高估）；向量没有输出
            input_tokens_est=sum(len(text.encode("utf-8")) for text in texts), max_output_tokens=0,
            user_id=scope.user_id,
        )
        try:
            # 向量费用归部署者：model_calls 对 embedding 用途不做预算检查，也不计入生成模型日预算
            self._store.prewrite(record, task_budget=0, daily_budget=0)
        except Exception as exc:
            raise EmbeddingRecordError("call record", batch_index, completed) from exc
        return call_id

    def _finish(self, call_id: str | None, started: float, *, model: str | None, usage: object,
                error: BaseException | None) -> None:
        if call_id is None or self._store is None:
            return
        usage_input = getattr(usage, "input_tokens", None)
        rejected = isinstance(error, ModelCallError) and error.rejected_before_generation
        error_class = None
        if error is not None:
            error_class = error.error_class.value if isinstance(error, ModelCallError) else "unexpected"
        try:
            self._store.finish(CallOutcome(
                call_id=call_id, status="error" if error is not None else "ok", model_responded=model,
                usage_input=usage_input, usage_output=None if usage_input is None else 0,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)), error_class=error_class,
                rejected_before_generation=rejected,
            ))
        except Exception as exc:  # noqa: BLE001 - the sent row stays (billed by estimate); never mask the call
            logger.warning("embedding call %s write-back failed (%s)", call_id, type(exc).__name__)

    def embed(self, texts: Sequence[str], *, deadline: float | None = None) -> tuple[EmbeddedVector, ...]:
        """``deadline`` (``time.monotonic()`` axis) bounds QA query embedding (ADR-082 决定 3): each request
        carries the remaining time and none is sent once it has passed. Publish/offline callers pass
        nothing and keep the client's per-request timeout. Cache hits never send a request.
        """
        if isinstance(texts, str) or not isinstance(texts, Sequence) or not all(
            isinstance(text, str) for text in texts
        ):
            raise ValueError("texts must be a sequence of strings")
        if not texts:
            return ()

        found: list[EmbeddedVector | None] = [None] * len(texts)
        pending: list[tuple[tuple[str, str], str]] = []
        pending_indices: dict[tuple[str, str], list[int]] = {}
        for index, text in enumerate(texts):
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            key = (self.space, text_hash)
            if key in pending_indices:
                pending_indices[key].append(index)
                continue
            cached = self._cache.get(self.space, text_hash)
            if cached is None:
                pending.append((key, text))
                pending_indices[key] = [index]
            else:
                found[index] = cached

        for batch_index, start in enumerate(range(0, len(pending), self._batch_size)):
            batch = pending[start : start + self._batch_size]
            completed = sum(vector is not None for vector in found)
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise EmbeddingDeadlineExceeded("deadline reached", batch_index, completed)
            batch_texts = tuple(text for _, text in batch)
            call_id = self._prewrite(batch_texts, batch_index, completed)   # 预写失败则不发请求
            started = time.monotonic()
            try:
                response = self._client.embed(
                    EmbeddingRequest(
                        model=self._model,
                        texts=batch_texts,
                        dimensions=self._dimensions,
                        timeout_seconds=remaining,
                    )
                )
            except Exception as exc:
                self._finish(call_id, started, model=None, usage=getattr(exc, "usage", None), error=exc)
                if deadline is not None and time.monotonic() >= deadline:
                    raise EmbeddingDeadlineExceeded("deadline reached", batch_index, completed) from exc
                raise EmbeddingBatchError("client call", batch_index, completed) from exc
            self._finish(call_id, started, model=response.model_responded, usage=response.usage, error=None)

            if response.model_requested != self._model or response.model_responded not in (None, self._model):
                raise EmbeddingBatchError("model mismatch", batch_index, completed)
            if len(response.vectors) != len(batch):
                raise EmbeddingBatchError("vector count mismatch", batch_index, completed)

            validated: list[EmbeddedVector] = []
            for ((_, text_hash), _), values in zip(batch, response.vectors, strict=True):
                if len(values) != self._dimensions:
                    raise EmbeddingBatchError("dimensions mismatch", batch_index, completed)
                if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
                    raise EmbeddingBatchError("non-finite vector value", batch_index, completed)
                validated.append(
                    EmbeddedVector(tuple(values), self._model, self._dimensions, self.space, text_hash)
                )
            self._cache.put_batch(validated)
            for (key, _), vector in zip(batch, validated, strict=True):
                for index in pending_indices[key]:
                    found[index] = vector

        return tuple(vector for vector in found if vector is not None)


__all__ = ["EmbeddedVector", "EmbeddingAdapter", "EmbeddingBatchError", "EmbeddingCache", "EmbeddingDeadlineExceeded", "EmbeddingRecordError", "embedding_calls"]
