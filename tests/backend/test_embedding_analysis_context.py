"""Embedding source changes affect analysis identity while key rotation does not."""

import pytest

from app.config import load_settings
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient
from app.services.fusion.mapping import fingerprint


def _adapter(base_url: str, key: str) -> EmbeddingAdapter:
    settings = load_settings({
        "EMBEDDING_MODE": "online",
        "EMBEDDING_BASE_URL": base_url,
        "EMBEDDING_API_KEY": key,
        "EMBEDDING_MODEL": "vector-model",
        "EMBEDDING_DIMENSIONS": "4",
    })
    return EmbeddingAdapter(settings, FakeEmbeddingClient())


def _analysis_identity(adapter: EmbeddingAdapter) -> str:
    return fingerprint({"space": adapter.space, "source": dict(adapter.analysis_context)})


def test_repointing_endpoint_invalidates_analysis_without_changing_vector_space():
    first = _adapter("https://vectors.example/v1", "test-key")
    second = _adapter("https://vectors.example/v2", "test-key")

    assert first.space == second.space == "real/vector-model/4"
    assert _analysis_identity(first) != _analysis_identity(second)


def test_key_rotation_keeps_analysis_identity_without_exposing_credentials():
    first = _adapter("https://vectors.example/v1", "old-key-not-for-context")
    second = _adapter("https://vectors.example/v1", "new-key-not-for-context")

    assert _analysis_identity(first) == _analysis_identity(second)
    assert "old-key-not-for-context" not in repr(first.analysis_context)
    assert "new-key-not-for-context" not in repr(second.analysis_context)
    with pytest.raises(TypeError):
        first.analysis_context["model"] = "other"
