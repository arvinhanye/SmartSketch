"""Generation analysis guards, independent of transport and model quality."""
import pytest
from app.config import Settings
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient


def test_embedding_checks_cancellation_before_each_physical_batch():
    client = FakeEmbeddingClient()
    adapter = EmbeddingAdapter(Settings(EMBEDDING_MODE="fake", EMBEDDING_BATCH_SIZE=1), client)
    checked = []
    def guard():
        checked.append(1)
        if len(checked) == 2: raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        adapter.embed(["one", "two"], before_attempt=guard)
    assert len(client.calls) == 1
