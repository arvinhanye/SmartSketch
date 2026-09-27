"""K04's fake benchmark must measure the successful extraction path."""

from app.config import Settings
from app.services.ai.client import Message, ModelRequest
from app.services.ai.entities import ENTITY_PROMPT_PURPOSE
from evaluation.benchmark_pipeline import build_toolkit


def test_fake_benchmark_client_returns_extractable_entities() -> None:
    toolkit = build_toolkit(Settings())
    client = toolkit.policy._primary.client
    request = ModelRequest(
        purpose=ENTITY_PROMPT_PURPOSE,
        model="fake",
        messages=(Message("user", "第3章 栈与队列 > 3.2 栈 > 第1段\n栈是一种线性表。"),),
        max_output_tokens=4096,
        response_format="json",
    )

    entities = client.complete(request).json()["entities"]

    assert any(entity["name"] == "栈" for entity in entities)
