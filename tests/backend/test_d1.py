"""D1：生成被截断（``finish_reason = length``）且未通过逐句出处校验时，是生成故障而不是「资料未覆盖」。

ADR-082 决定 2：截断 + 校验不通过 → ``LLM_UNAVAILABLE`` + ``details.reason = truncated``，整段撤回；
截断但每个结论单元都有有效出处 → 仍按 ADR-015 ``answered``；没有截断的校验失败仍是 ``not_covered``。
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.dependencies import course_student
from app.config import Settings
from app.repositories.chat_logs import list_chat_logs
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import ModelConnectionError, ModelResult, StreamDelta, StreamDone
from app.services.qa.chat import ChatService, PreparedChat
from app.services.qa.context import (
    ContextReason, ContextStats, ContextStatus, EvidenceChunk, EvidenceContext, GraphContext,
)
from app.services.qa.generate import AnswerGeneration
from app.services.versions.resolver import PublishedVersion

COURSE, VERSION_ID = "c" * 32, "v" * 26
VERSION = PublishedVersion(COURSE, VERSION_ID, 1, frozenset({"revision"}))


def _chunk(index):
    return EvidenceChunk(index, f"chunk-{index}", "revision", "document", 3, None,
                         "栈只允许在一端插入删除；队列在一端插入、另一端删除。", 0.9, ("vector",), (), 20)


COVERED = EvidenceContext(ContextStatus.READY, None, (_chunk(1), _chunk(2)), GraphContext(), 2, ContextStats())
UNCOVERED = EvidenceContext(ContextStatus.NOT_COVERED, ContextReason.NO_RETRIEVAL_HIT, (), GraphContext(), 0,
                            ContextStats())


def _generator(parts, finish_reason="stop", *, fail_after=None):
    def supplier():
        for position, part in enumerate(parts):
            if fail_after is not None and position == fail_after:
                raise ModelConnectionError("m")
            yield StreamDelta(part)
        yield StreamDone(ModelResult("".join(parts), "m", "m", None, finish_reason))

    class Generator:
        def generate(self, *args, **kwargs):
            return AnswerGeneration(supplier, lambda: 10.0)

    return Generator()


def _prepared(context=COVERED, *, deadline_in=10.0):
    now = time.monotonic()
    return PreparedChat(VERSION, "request", now, now + deadline_in, "栈和队列有什么区别？", context)


def _run(generator, context=COVERED):
    prepared = _prepared(context)
    events = list(ChatService(Settings(), None, None, None, generator).events(prepared))
    return events, prepared


def _error(events):
    assert [e["event"] for e in events][-1] == "error"
    assert not any(e["event"] == "done" for e in events)   # 不构造 answered / not_covered 终态
    return events[-1]["error"]


# ---- 终态分类 ---------------------------------------------------------------------------------

def test_no_retrieval_is_still_not_covered():
    events, _ = _run(_generator([]), UNCOVERED)
    assert events[-1]["final"]["status"] == "not_covered"
    assert events[-1]["final"]["reason"] == "no_retrieval_hit"


def test_normal_cited_answer_is_answered():
    events, prepared = _run(_generator(["栈后进先出[1]。", "队列先进先出[2]。"]))
    final = events[-1]["final"]
    assert final["status"] == "answered" and [c["index"] for c in final["citations"]] == [1, 2]
    assert prepared.audit.truncated is False


def test_truncated_without_markers_is_generation_failure_not_not_covered():
    events, prepared = _run(_generator(["栈和队列都是线性表，区别在于", "插入和删除的位置不同"], "length"))
    error = _error(events)
    assert error["code"] == "LLM_UNAVAILABLE" and error["details"]["reason"] == "truncated"
    assert prepared.audit.truncated is True and prepared.audit.invalidation_subtype == "no_markers"


def test_truncated_with_unknown_markers_only_is_generation_failure():
    events, prepared = _run(_generator(["栈后进先出[9]。队列先进先出"], "length"))
    assert _error(events)["details"]["reason"] == "truncated"
    assert prepared.audit.invalidation_subtype == "unknown_only"


def test_truncated_after_valid_citation_with_cut_sentence_is_generation_failure():
    events, prepared = _run(_generator(["栈后进先出[1]。", "队列在一端插入、另一端"], "length"))
    assert [e["event"] for e in events] == ["meta", "delta", "delta", "error"]   # 临时正文须由客户端撤回
    assert _error(events)["details"]["reason"] == "truncated"
    assert prepared.audit.invalidation_subtype == "uncited_sentence" and prepared.audit.uncovered_unit_count == 1


def test_truncated_but_every_unit_cited_stays_answered_per_adr015():
    events, prepared = _run(_generator(["栈后进先出[1]。", "队列先进先出[2]。"], "length"))
    assert events[-1]["final"]["status"] == "answered"
    assert prepared.audit.truncated is True


def test_untruncated_invalid_citations_remain_not_covered():
    events, prepared = _run(_generator(["栈和队列都是线性表。"], "stop"))
    final = events[-1]["final"]
    assert (final["status"], final["reason"]) == ("not_covered", "all_citations_invalidated")
    assert prepared.audit.truncated is False


def test_sentinel_with_length_is_still_insufficient_evidence():
    events, _ = _run(_generator(["<<INSUFFICIENT_EVIDENCE>>"], "length"))
    assert events[-1]["final"]["reason"] == "insufficient_evidence"


def test_supplier_interruption_after_delta_is_stream_interrupted():
    events, _ = _run(_generator(["栈后进先出[1]。", "队列"], fail_after=1))
    error = _error(events)
    assert error["code"] == "LLM_UNAVAILABLE" and error["details"]["reason"] == "stream_interrupted"


def test_deadline_reached_during_generation_is_timeout():
    def supplier():
        yield StreamDelta("栈后进先出[1]。")
        yield StreamDone(ModelResult("栈后进先出[1]。", "m", "m", None, "length"))

    class Generator:
        def generate(self, *args, **kwargs):
            return AnswerGeneration(supplier, lambda: -1.0)

    events, _ = _run(Generator())
    assert _error(events)["details"]["reason"] == "timeout"


# ---- 两种传输与问答日志一致 -----------------------------------------------------------------------

@pytest.fixture
def chat_app(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'chat.sqlite').as_posix()}"
    migrate(url)
    user_id = "u" * 32
    with connect(url) as db:
        db.execute("INSERT INTO users(id, username, password_hash, role) VALUES (?, 'student', ?, 'student')",
                   (user_id, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"))
        db.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Course', ?)", (COURSE, user_id))
        db.execute("INSERT INTO graph_versions(version_id, course_id, kind, expires_at) VALUES (?, ?, 'publish', 1)",
                   (VERSION_ID, COURSE))
    monkeypatch.setattr(chat_api, "resolve_published", lambda *_: VERSION)

    class Service(ChatService):
        def prepare(self, *, version, request_id, started, question, history, kp_id):
            return PreparedChat(version, request_id, started, started + 10, question, COVERED)

    service = Service(Settings(SQLITE_URL=url), None, None, None,
                      _generator(["栈后进先出[1]。", "队列在一端插入、另一端"], "length"))
    app = FastAPI()
    app.state.settings = SimpleNamespace(SQLITE_URL=url)
    app.state.chat_service = service
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=COURSE), user=SimpleNamespace(id=user_id))
    return app, url, user_id


@pytest.mark.parametrize("accept", ["application/json", "text/event-stream"])
def test_truncation_failure_is_the_same_on_both_transports_and_in_the_log(chat_app, accept):
    app, url, user_id = chat_app
    with TestClient(app) as client:
        response = client.post(f"/api/v1/courses/{COURSE}/chat", json={"question": "栈和队列有什么区别？"},
                               headers={"accept": accept})
    if accept == "application/json":
        assert response.status_code == 503
        assert response.json()["code"] == "LLM_UNAVAILABLE"
        assert response.json()["details"]["reason"] == "truncated"
    else:
        assert response.status_code == 200
        assert "event: error" in response.text and '"reason":"truncated"' in response.text
        assert "event: done" not in response.text
    [row] = list_chat_logs(url, user_id=user_id, course_id=COURSE)
    assert (row.outcome, row.error_code, row.error_reason) == ("error", "LLM_UNAVAILABLE", "truncated")
    assert row.truncated is True and row.reason is None
