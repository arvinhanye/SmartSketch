"""K05 E2E's fixed, self-authored extraction response for the worker fake adapter."""

import json

from app.services.ai.client import ModelRequest
from app.services.ai.fake import default_text


def respond(request: ModelRequest) -> str:
    if request.purpose == "extract_relations":
        return '{"relations": []}'
    if request.purpose == "extract_entities_gleaning":
        return '{"entities": []}'
    if request.purpose != "extract_entities":
        return default_text(request)
    chunk = request.messages[-1].content.rsplit("资料块：\n", 1)[-1]
    entities = []
    for name, evidence in (
        ("Stack", "A stack is last in first out."),
        ("Queue", "A queue is first in first out."),
    ):
        if evidence in chunk:
            entities.append({
                "name": name, "type": "concept", "definition": evidence,
                "evidence": evidence, "confidence": 0.95,
            })
    return json.dumps({"entities": entities})
