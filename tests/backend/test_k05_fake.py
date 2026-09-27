import json

from app.services.ai.client import Message, ModelRequest
from app.services.ai.k05_demo_fake import respond


def test_k05_fake_extraction_supplies_two_sourced_nodes() -> None:
    text = "Chapter 3: Stack and Queue. A stack is last in first out. A queue is first in first out."
    request = ModelRequest(
        purpose="extract_entities", model="fake",
        messages=(Message("user", "资料块：\n" + text),), max_output_tokens=512,
        response_format="json",
    )

    entities = json.loads(respond(request))["entities"]
    assert {item["name"] for item in entities} == {"Stack", "Queue"}
    assert all(item["evidence"] in text for item in entities)
