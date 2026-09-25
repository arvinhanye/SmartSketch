"""E07 embedding batches with explicit vector-space labels and validation."""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.config import Settings
from app.services.ai.client import EmbeddingClient, EmbeddingRequest


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
    ) -> None:
        self._client = client
        self._cache = cache if cache is not None else EmbeddingCache()
        is_fake = settings.EMBEDDING_MODE == "fake"
        self._model = "fake" if is_fake else settings.EMBEDDING_MODEL
        if not self._model:
            raise ValueError("EMBEDDING_MODEL is required for online/local embedding")
        self._dimensions = settings.EMBEDDING_DIMENSIONS
        self._batch_size = settings.EMBEDDING_BATCH_SIZE
        self.space = (
            f"fake/{self._dimensions}" if is_fake else f"real/{self._model}/{self._dimensions}"
        )

    def embed(self, texts: Sequence[str]) -> tuple[EmbeddedVector, ...]:
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
            try:
                response = self._client.embed(
                    EmbeddingRequest(
                        model=self._model,
                        texts=tuple(text for _, text in batch),
                        dimensions=self._dimensions,
                    )
                )
            except Exception as exc:
                raise EmbeddingBatchError("client call", batch_index, completed) from exc

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


__all__ = ["EmbeddedVector", "EmbeddingAdapter", "EmbeddingBatchError", "EmbeddingCache"]
