"""J10 chat outcome persistence on the current migration sequence."""

import asyncio
import json
import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.dependencies import course_student
from app.repositories.chat_logs import ChatLog, count_chat_outcomes, list_chat_logs, write_chat_log
from app.repositories.sqlite import connect, migrate
from app.services.qa.chat import ChatFailure
from app.services.qa.chat import ChatAudit, ChatService, PreparedChat
from app.services.qa.context import ContextStats, ContextStatus, EvidenceChunk, EvidenceContext, GraphContext
from app.services.qa.generate import AnswerGeneration
from app.services.ai.client import ModelResult, StreamDelta, StreamDone
from app.config import Settings
from app.services.versions.resolver import PublishedVersion


@pytest.fixture
def chat_env(tmp_path):
    url = f"sqlite:///{(tmp_path / 'chat.sqlite').as_posix()}"
    assert migrate(url)[-1] == "016"
    user_id = "u" * 32
    course_id = "c" * 32
    version_id = "v" * 26
    with connect(url) as db:
        db.execute(
            "INSERT INTO users(id, username, password_hash, role) VALUES (?, 'teacher', ?, 'teacher')",
            (user_id, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"),
        )
        db.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Course', ?)", (course_id, user_id))
        db.execute(
            "INSERT INTO graph_versions(version_id, course_id, kind, expires_at) VALUES (?, ?, 'publish', 1)",
            (version_id, course_id),
        )
    return url, user_id, course_id, version_id


def test_one_log_per_bound_request(chat_env):
    url, user_id, course_id, version_id = chat_env

    log = ChatLog(
        request_id="r" * 26, user_id=user_id, course_id=course_id,
        version_id=version_id, question="What is a stack?", outcome="answered",
        latency_ms=42, citations=((1, "chunk-1"),), first_delta_latency_ms=12,
    )
    write_chat_log(url, log)
    with connect(url) as db:
        row = db.execute(
            "SELECT question, outcome, citations_json, first_delta_latency_ms FROM chat_logs WHERE request_id = ?",
            (log.request_id,),
        ).fetchone()
    assert row[:2] == ("What is a stack?", "answered")
    assert json.loads(row[2]) == [[1, "chunk-1"]]
    assert row[3] == 12
    with pytest.raises(sqlite3.IntegrityError):
        write_chat_log(url, log)


def test_scoped_search_stats_retry_and_retention(chat_env):
    url, user_id, course_id, version_id = chat_env
    other_user = "o" * 32
    other_course = "d" * 32
    with connect(url) as db:
        db.execute(
            "INSERT INTO users(id, username, password_hash, role) VALUES (?, 'other', ?, 'teacher')",
            (other_user, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"),
        )
        db.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Other', ?)",
                   (other_course, other_user))
        db.execute("INSERT INTO graph_versions(version_id, course_id, kind, expires_at) "
                   "VALUES (?, ?, 'publish', 1)", ("w" * 26, other_course))
    original = ChatLog("r" * 26, user_id, course_id, version_id, "question", "error", 10)
    retry = ChatLog("s" * 26, user_id, course_id, version_id, "question", "answered", 20)
    foreign = ChatLog("t" * 26, other_user, other_course, "w" * 26, "other", "answered", 30)
    for log in (original, retry, foreign):
        write_chat_log(url, log)
    assert [row.request_id for row in list_chat_logs(url, user_id=user_id, course_id=course_id)] == [retry.request_id, original.request_id]
    assert [row.request_id for row in list_chat_logs(url, user_id=user_id, course_id=course_id,
                                                      request_id=original.request_id)] == [original.request_id]
    assert count_chat_outcomes(url, user_id=user_id, course_id=course_id) == {"answered": 1, "error": 1}
    assert list_chat_logs(url, user_id=other_user, course_id=course_id) == ()
    assert count_chat_outcomes(url, user_id=user_id, course_id=other_course) == {}
    with connect(url) as db:
        db.execute("UPDATE chat_logs SET created_at='2020-01-01T00:00:00.000Z' WHERE request_id=?",
                   (original.request_id,))
    write_chat_log(url, ChatLog("u" * 26, user_id, course_id, version_id, "new", "not_covered", 15))
    assert count_chat_outcomes(url, user_id=user_id, course_id=course_id) == {"answered": 1, "not_covered": 1}


@pytest.mark.parametrize("terminal, expected", [
    ("answered", "answered"),
    ("not_covered", "not_covered"),
    ("error", "error"),
    ("prepare_error", "error"),
])
def test_chat_route_records_one_bound_terminal(chat_env, monkeypatch, terminal, expected):
    url, user_id, course_id, version_id = chat_env
    version = PublishedVersion(course_id, version_id, 1, frozenset())
    monkeypatch.setattr(chat_api, "resolve_published", lambda *_: version)

    class FakeService:
        def prepare(self, **kwargs):
            if terminal == "prepare_error":
                raise ChatFailure("LLM_UNAVAILABLE", reason="timeout")
            return SimpleNamespace(version=version, request_id=kwargs["request_id"],
                                   started=kwargs["started"], audit=SimpleNamespace(
                                       unknown_citation_count=2, invalidation_subtype=None,
                                       uncovered_unit_count=0, truncated=False,
                                       first_delta_latency_ms=8))

        def events(self, prepared, stop=None):
            yield {"event": "meta", "request_id": prepared.request_id}
            if terminal == "answered":
                yield {"event": "delta", "delta": "Answer [1]"}
                yield {"event": "done", "final": {
                    "status": "answered", "answer": "Answer [1]", "citations": [
                        {"index": 1, "chunk_id": "chunk-1"}], "latency_ms": 12,
                    "request_id": prepared.request_id, "graph_version": 1,
                }}
            elif terminal == "not_covered":
                yield {"event": "done", "final": {
                    "status": "not_covered", "reason": "no_retrieval_hit", "answer": "未覆盖",
                    "citations": [], "latency_ms": 12, "request_id": prepared.request_id,
                    "graph_version": 1,
                }}
            else:
                yield {"event": "error", "error": ChatFailure(
                    "LLM_UNAVAILABLE", reason="upstream").body(prepared.request_id)}

    monkeypatch.setattr(chat_api, "chat_service", lambda request: FakeService())
    app = FastAPI()
    app.state.settings = SimpleNamespace(SQLITE_URL=url)
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=course_id), user=SimpleNamespace(id=user_id))
    with TestClient(app) as client:
        response = client.post(f"/api/v1/courses/{course_id}/chat", json={"question": "What is a stack?"},
                               headers={"accept": "application/json"})
    assert response.status_code == (503 if terminal in ("error", "prepare_error") else 200)
    [row] = list_chat_logs(url, user_id=user_id, course_id=course_id)
    assert row.outcome == expected
    assert row.version_id == version_id and row.question == "What is a stack?"
    if terminal == "answered":
        assert row.citations == ((1, "chunk-1"),)
        assert row.first_delta_latency_ms == 8
        assert row.unknown_citation_count == 2
    if terminal == "prepare_error":
        assert row.error_code == "LLM_UNAVAILABLE" and row.error_reason == "timeout"


def test_failed_p2_does_not_create_chat_log(chat_env, monkeypatch):
    url, user_id, course_id, _ = chat_env
    def unavailable(*args):
        raise sqlite3.OperationalError("unavailable")
    monkeypatch.setattr(chat_api, "resolve_published", unavailable)
    app = FastAPI()
    app.state.settings = SimpleNamespace(SQLITE_URL=url)
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=course_id), user=SimpleNamespace(id=user_id))
    with TestClient(app) as client:
        response = client.post(f"/api/v1/courses/{course_id}/chat", json={"question": "What is a stack?"})
    assert response.status_code == 503
    assert list_chat_logs(url, user_id=user_id, course_id=course_id) == ()


def test_sse_terminal_is_logged_once(chat_env, monkeypatch):
    url, user_id, course_id, version_id = chat_env
    version = PublishedVersion(course_id, version_id, 1, frozenset())
    monkeypatch.setattr(chat_api, "resolve_published", lambda *_: version)

    class FakeService:
        def prepare(self, **kwargs):
            return SimpleNamespace(version=version, request_id=kwargs["request_id"],
                                   started=kwargs["started"], audit=ChatAudit())

        def events(self, prepared, stop=None):
            yield {"event": "meta", "status": "not_covered", "retrieved": 0,
                   "graph_version": 1, "request_id": prepared.request_id}
            yield {"event": "done", "final": {
                "status": "not_covered", "reason": "no_retrieval_hit", "answer": "未覆盖",
                "citations": [], "latency_ms": 12, "request_id": prepared.request_id,
                "graph_version": 1,
            }}

    monkeypatch.setattr(chat_api, "chat_service", lambda request: FakeService())
    app = FastAPI()
    app.state.settings = SimpleNamespace(SQLITE_URL=url)
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=course_id), user=SimpleNamespace(id=user_id))
    with TestClient(app) as client:
        response = client.post(f"/api/v1/courses/{course_id}/chat", json={"question": "What is a stack?"},
                               headers={"accept": "text/event-stream"})
    assert response.status_code == 200
    assert "event: done" in response.text
    [row] = list_chat_logs(url, user_id=user_id, course_id=course_id)
    assert row.outcome == "not_covered" and row.reason == "no_retrieval_hit"


def test_disconnected_sse_is_logged_as_aborted(chat_env):
    url, user_id, course_id, version_id = chat_env
    request_id = "z" * 26
    prepared = SimpleNamespace(request_id=request_id, audit=ChatAudit())

    class Disconnected:
        async def is_disconnected(self):
            return True

    class FakeService:
        def events(self, prepared, stop=None):
            yield {"event": "meta"}

    def record(terminal):
        chat_api._record_outcome(
            url, request_id=request_id, user_id=user_id, course_id=course_id,
            version_id=version_id, question="What is a stack?", started=time.monotonic(),
            terminal=terminal, audit=prepared.audit,
        )

    async def consume():
        async for _ in chat_api._stream(Disconnected(), FakeService(), prepared, record):
            pass

    asyncio.run(consume())
    [row] = list_chat_logs(url, user_id=user_id, course_id=course_id)
    assert row.outcome == "aborted"


@pytest.mark.parametrize("answer, outcome, subtype, uncovered", [
    ("句子[1]。[99]", "answered", None, 0),
    ("句子[1]。另一句。", "not_covered", "uncited_sentence", 1),
])
def test_service_citation_diagnostics_reach_audit(answer, outcome, subtype, uncovered):
    version = PublishedVersion("course", "version", 1, frozenset({"revision"}))
    chunk = EvidenceChunk(1, "chunk", "revision", "document", 1, None,
                          "课程原文", 0.9, ("vector",), (), 20)
    context = EvidenceContext(ContextStatus.READY, None, (chunk,), GraphContext(), 1, ContextStats())
    started = time.monotonic()
    prepared = PreparedChat(version, "request", started, started + 10, "问题", context)

    def supplier():
        yield StreamDelta(answer)
        yield StreamDone(ModelResult("", "fake", "fake", None, "stop"))

    generator = type("Generator", (), {"generate": lambda self, *args, **kwargs:
                     AnswerGeneration(supplier, lambda: 10)})()
    service = ChatService(Settings(), None, None, None, generator)
    events = list(service.events(prepared))
    assert events[-1]["final"]["status"] == outcome
    assert prepared.audit.unknown_citation_count == (1 if "[99]" in answer else 0)
    assert prepared.audit.invalidation_subtype == subtype
    assert prepared.audit.uncovered_unit_count == uncovered
    assert prepared.audit.first_delta_latency_ms is not None
