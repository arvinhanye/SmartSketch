"""J07 chain deadline at the generation terminal boundary."""

import time

from app.config import Settings
from app.services.ai.client import ModelResult, StreamDone
from app.services.qa.chat import ChatService, PreparedChat
from app.services.qa.context import (
    ContextStats, ContextStatus, EvidenceChunk, EvidenceContext, GraphContext,
)
from app.services.qa.generate import AnswerGeneration
from app.services.versions.resolver import PublishedVersion


def test_late_stream_done_is_timeout() -> None:
    version = PublishedVersion("course", "version", 1, frozenset({"revision"}))
    chunk = EvidenceChunk(1, "chunk", "revision", "document", 1, None,
                          "课程原文", 0.9, ("vector",), (), 20)
    context = EvidenceContext(ContextStatus.READY, None, (chunk,), GraphContext(), 1, ContextStats())
    expired = time.monotonic() - 1
    prepared = PreparedChat(version, "request", expired - 1, expired, "问题", context)

    def supplier():
        yield StreamDone(ModelResult("", "fake", "fake", None, "stop"))

    generation = AnswerGeneration(supplier, lambda: -1)
    generator = type("Generator", (), {"generate": lambda self, *args, **kwargs: generation})()
    service = ChatService(Settings(), None, None, None, generator)

    events = list(service.events(prepared))
    assert [event["event"] for event in events] == ["meta", "error"]
    assert events[-1]["error"]["code"] == "LLM_UNAVAILABLE"
    assert events[-1]["error"]["details"]["reason"] == "timeout"
