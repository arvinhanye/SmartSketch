"""E07: batching, vector-space integrity, and recoverable batch failures."""

import math

import pytest

from app.config import Settings
from app.services.ai.client import ModelRateLimitedError
from app.services.ai.embeddings import (
    EmbeddingAdapter,
    EmbeddingBatchError,
    EmbeddingCache,
)
from app.services.ai.fake import FakeEmbedding, FakeEmbeddingClient


def adapter(
    client: FakeEmbeddingClient,
    *,
    mode: str = "fake",
    model: str = "",
    dimensions: int = 4,
    batch_size: int = 2,
    cache: EmbeddingCache | None = None,
) -> EmbeddingAdapter:
    settings = Settings(
        EMBEDDING_MODE=mode,
        EMBEDDING_MODEL=model,
        EMBEDDING_DIMENSIONS=dimensions,
        EMBEDDING_BATCH_SIZE=batch_size,
    )
    return EmbeddingAdapter(settings, client, cache=cache)


def test_empty_batch_makes_no_client_call() -> None:
    client = FakeEmbeddingClient()
    assert adapter(client).embed([]) == ()
    assert client.calls == ()


def test_batches_preserve_order_and_tag_vectors_with_model_and_space() -> None:
    client = FakeEmbeddingClient()
    vectors = adapter(client, mode="online", model="emb-v1").embed(["a", "b", "c"])
    assert [call.request.texts for call in client.calls] == [("a", "b"), ("c",)]
    assert all(call.request.dimensions == 4 for call in client.calls)
    assert [v.text_hash for v in vectors] == [v.text_hash for v in adapter(FakeEmbeddingClient(), mode="online", model="emb-v1").embed(["a", "b", "c"])]
    assert all(v.model == "emb-v1" and v.dimensions == 4 and v.space == "real/emb-v1/4" for v in vectors)
    assert vectors[0].values != vectors[1].values


def test_fake_space_is_separate_and_local_uses_configured_model() -> None:
    fake = adapter(FakeEmbeddingClient()).embed(["a"])[0]
    local_client = FakeEmbeddingClient()
    local = adapter(local_client, mode="local", model="emb-v1").embed(["a"])[0]
    assert fake.space == "fake/4" and fake.model == "fake"
    assert local.space == "real/emb-v1/4" and local.model == "emb-v1"
    assert local_client.calls[0].request.model == "emb-v1"


def test_vector_repr_does_not_expose_embedding_values() -> None:
    client = FakeEmbeddingClient()
    client.script(FakeEmbedding(vectors=((0.123456789, 0.0, 0.0, 0.0),)))
    vector = adapter(client).embed(["private"])[0]
    assert "0.123456789" not in repr(vector)


def test_real_model_named_fake_cannot_hit_fake_space_cache() -> None:
    cache = EmbeddingCache()
    fake_client = FakeEmbeddingClient()
    fake = adapter(fake_client, cache=cache).embed(["same"])[0]
    real_client = FakeEmbeddingClient()
    real = adapter(real_client, mode="online", model="fake", cache=cache).embed(["same"])[0]
    assert fake.space != real.space
    assert len(real_client.calls) == 1


@pytest.mark.parametrize(
    ("script", "message"),
    [
        (FakeEmbedding(vectors=((1.0, 2.0),)), "dimensions"),
        (FakeEmbedding(vectors=()), "count"),
        (FakeEmbedding(vectors=((math.nan,) * 4,)), "finite"),
        (FakeEmbedding(vectors=((1.0,) * 4,), model_responded="other"), "model"),
    ],
)
def test_invalid_provider_result_fails_before_cache(script: FakeEmbedding, message: str) -> None:
    client = FakeEmbeddingClient()
    client.script(script)
    cache = EmbeddingCache()
    service = adapter(client, mode="online", model="emb-v1", cache=cache)
    with pytest.raises(EmbeddingBatchError, match=message) as info:
        service.embed(["a"])
    assert info.value.batch_index == 0
    assert info.value.completed_count == 0
    assert service.embed(["a"])
    assert len(client.calls) == 2


def test_partial_failure_reports_progress_and_retry_reuses_completed_batch() -> None:
    client = FakeEmbeddingClient()
    client.script(
        FakeEmbedding(vectors=((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0))),
        ModelRateLimitedError("emb-v1"),
    )
    service = adapter(client, mode="online", model="emb-v1")
    with pytest.raises(EmbeddingBatchError) as info:
        service.embed(["a", "b", "c"])
    assert info.value.batch_index == 1
    assert info.value.completed_count == 2
    assert isinstance(info.value.__cause__, ModelRateLimitedError)
    result = service.embed(["a", "b", "c"])
    assert result[0].values == (1.0, 0.0, 0.0, 0.0)
    assert [call.request.texts for call in client.calls] == [("a", "b"), ("c",), ("c",)]


def test_cache_is_partitioned_by_space_and_can_clear_one_space() -> None:
    cache = EmbeddingCache()
    client = FakeEmbeddingClient()
    online_v1 = adapter(client, mode="online", model="emb-v1", cache=cache)
    first = online_v1.embed(["same"])[0]
    assert online_v1.embed(["same"])[0] == first
    assert len(client.calls) == 1
    second = adapter(client, mode="local", model="emb-v2", cache=cache).embed(["same"])[0]
    assert second.space == "real/emb-v2/4" and second.values != first.values
    assert len(client.calls) == 2
    cache.clear_space(first.space)
    online_v1.embed(["same"])
    assert len(client.calls) == 3


def test_same_batch_duplicate_text_is_embedded_once_and_expanded() -> None:
    client = FakeEmbeddingClient()
    vectors = adapter(client).embed(["same", "same"])

    assert [call.request.texts for call in client.calls] == [("same",)]
    assert len(vectors) == 2
    assert vectors[0] == vectors[1]


def test_duplicate_text_across_batches_is_embedded_once() -> None:
    client = FakeEmbeddingClient()
    vectors = adapter(client, batch_size=2).embed(["same", "other", "third", "same"])

    assert [call.request.texts for call in client.calls] == [
        ("same", "other"),
        ("third",),
    ]
    assert len(vectors) == 4
    assert vectors[0] == vectors[3]
    assert vectors[0] != vectors[1]


def test_lru_capacity_evicts_old_vectors_and_recomputes_them() -> None:
    client = FakeEmbeddingClient()
    cache = EmbeddingCache(max_entries=2)
    service = adapter(client, cache=cache, batch_size=1)

    service.embed(["first"])
    service.embed(["second"])
    service.embed(["first"])  # A hit keeps first more recent than second.
    service.embed(["third"])
    service.embed(["first"])
    service.embed(["second"])

    assert [call.request.texts for call in client.calls] == [
        ("first",),
        ("second",),
        ("third",),
        ("second",),
    ]


def test_cache_rejects_nonpositive_capacity() -> None:
    with pytest.raises(ValueError, match="max_entries"):
        EmbeddingCache(max_entries=0)


def test_non_string_input_is_rejected_before_client_call() -> None:
    client = FakeEmbeddingClient()
    service = adapter(client)
    with pytest.raises(ValueError, match="texts"):
        service.embed("a")
    with pytest.raises(ValueError, match="texts"):
        service.embed(["a", 4])
    assert client.calls == ()
