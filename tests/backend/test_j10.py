"""J10 chat audit and statistics (specs/grounded-qa.md Q10).

Acceptance (docs/atomic-tasks.json J10): course/user isolation; version and
latency always present; retention and redaction explicit; retries never counted
twice. Covers the repository, the recorder on the real J07 event path, and the
HTTP route (JSON, SSE, aborted stream, P2 failures that must not log).
"""

import asyncio
import json
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.config import Settings
from app.main import create_app
from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.chat_logs import (
    ChatLog,
    ChatLogScopeError,
    chat_stats,
    get_chat_log,
    list_chat_logs,
    write_chat_log,
)
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import ModelResult, StreamDelta, StreamDone
from app.services.auth import issue_access_token
from app.services.qa.audit import ChatAudit
from app.services.qa.chat import ChatFailure, ChatService, PreparedChat
from app.services.qa.context import (
    ContextStats, ContextStatus, EvidenceChunk, EvidenceContext, GraphContext,
)
from app.services.qa.generate import AnswerGeneration
from app.services.versions import resolver
from app.services.versions.resolver import PublishedVersion
from app.services.versions.snapshot import DraftGraph, DraftNode, Revision, build_snapshot

SECRET = "j10-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
EXCLUDED = {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0}


def test_one_log_per_bound_request(tmp_path):
    url = f"sqlite:///{(tmp_path / 'chat.sqlite').as_posix()}"
    assert migrate(url)[-1] == "014"
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


# --- shared fixtures ------------------------------------------------------


def _account(url, username, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=username, password_hash=VALID_HASH, role=role)


def _pointer(url, course_id):
    with connect(url) as db:
        return db.execute("SELECT published_version_id FROM courses WHERE id = ?", (course_id,)).fetchone()[0]


def _publish(url, course_id, teacher):
    """Commit one real version through G04 so P2 binding resolves it."""
    node = DraftNode(kp_id="stack", name="栈", type="concept", definition="定义", status="approved",
                     source_refs=("ch-1",))
    revision = Revision("rev-1", "mat-1", "sha256:" + "a" * 64, "txt/1+chunk/1@1500-200")
    snap = build_snapshot(DraftGraph(course_id, [revision], [], [node], [], {"ch-1": "rev-1"})).snapshot
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=teacher.id, lease_seconds=60)
    assert versions.record_snapshot(url, attempt.version_id, snapshot=snap.canonical, digest=snap.digest,
                                    node_count=1, edge_count=0, excluded=EXCLUDED, draft_revision=1,
                                    task_watermark=0, embedding_space="bge-m3@1024")
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        versions.commit_attempt(db, attempt.version_id, expected_pointer=_pointer(url, course_id),
                                published_from_revision=1)
    return attempt.version_id


class World:
    def __init__(self, tmp_path):
        self.url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
        migrate(self.url)
        self.teacher = _account(self.url, "teacher1", "teacher")
        self.alice = _account(self.url, "alice01", "student")
        self.bob = _account(self.url, "bob0001", "student")
        self.outsider = _account(self.url, "carol01", "student")
        self.course = create_course(self.url, name="数据结构", description=None, creator_id=self.teacher.id).id
        self.other = create_course(self.url, name="他课", description=None, creator_id=self.teacher.id).id
        self.unpublished = create_course(self.url, name="未发布", description=None, creator_id=self.teacher.id).id
        for student in (self.alice, self.bob):
            for course_id in (self.course, self.other, self.unpublished):
                add_member(self.url, course_id=course_id, user_id=student.id, role="student",
                           added_by=self.teacher.id)
        self.version = _publish(self.url, self.course, self.teacher)
        self.other_version = _publish(self.url, self.other, self.teacher)

    def log(self, request_id, *, user=None, course=None, outcome="answered", **extra):
        course = course or self.course
        version = self.version if course == self.course else self.other_version
        return ChatLog(request_id=request_id, user_id=(user or self.alice).id, course_id=course,
                       version_id=version, question="栈是什么？", outcome=outcome, latency_ms=10, **extra)

    def rows(self, course=None):
        return list_chat_logs(self.url, course_id=course or self.course, limit=500)


@pytest.fixture(autouse=True)
def fresh_cache():
    resolver.clear_cache()
    yield
    resolver.clear_cache()


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# --- repository: isolation, retrieval, statistics, retention, redaction ----


def test_version_from_another_course_is_rejected_without_a_row(world):
    bad = ChatLog(request_id="x" * 26, user_id=world.alice.id, course_id=world.course,
                  version_id=world.other_version, question="q", outcome="answered", latency_ms=1)
    with pytest.raises(ChatLogScopeError):
        write_chat_log(world.url, bad)
    with connect(world.url) as db:
        assert db.execute("SELECT COUNT(*) FROM chat_logs").fetchone()[0] == 0


def test_unknown_outcome_and_missing_identity_are_refused_by_the_schema(world):
    with pytest.raises(sqlite3.IntegrityError):
        write_chat_log(world.url, world.log("a" * 26, outcome="partial"))
    ghost = ChatLog(request_id="b" * 26, user_id="nobody", course_id=world.course, version_id=world.version,
                    question="q", outcome="answered", latency_ms=1)
    with pytest.raises(sqlite3.IntegrityError):
        write_chat_log(world.url, ghost)


def test_reads_are_scoped_to_one_course_and_filterable(world):
    write_chat_log(world.url, world.log("r1" + "0" * 24))
    write_chat_log(world.url, world.log("r2" + "0" * 24, user=world.bob, outcome="not_covered",
                                        reason="no_retrieval_hit"))
    write_chat_log(world.url, world.log("r3" + "0" * 24, course=world.other))

    assert {log.request_id[:2] for log in world.rows()} == {"r1", "r2"}
    assert [log.request_id[:2] for log in world.rows(world.other)] == ["r3"]
    assert [log.request_id[:2] for log in list_chat_logs(world.url, course_id=world.course,
                                                         user_id=world.bob.id)] == ["r2"]
    assert [log.request_id[:2] for log in list_chat_logs(world.url, course_id=world.course,
                                                         outcome="answered")] == ["r1"]
    assert get_chat_log(world.url, course_id=world.other, request_id="r1" + "0" * 24) is None
    found = get_chat_log(world.url, course_id=world.course, request_id="r1" + "0" * 24)
    assert (found.version_id, found.latency_ms, found.user_id) == (world.version, 10, world.alice.id)
    assert found.created_at is not None
    with pytest.raises(ValueError):
        list_chat_logs(world.url, course_id=world.course, outcome="partial")
    for limit in (0, 501):
        with pytest.raises(ValueError):
            list_chat_logs(world.url, course_id=world.course, limit=limit)


def test_round_trip_keeps_every_diagnostic_field(world):
    log = world.log("rt" + "0" * 24, outcome="not_covered", reason="all_citations_invalidated",
                    citations=((2, "chunk-b"), (1, "chunk-a")), unknown_citation_count=3,
                    invalidation_subtype="uncited_sentence", uncovered_unit_count=2, truncated=True,
                    first_delta_latency_ms=7)
    write_chat_log(world.url, log)
    [stored] = world.rows()
    assert stored == ChatLog(**{**{f: getattr(log, f) for f in log.__slots__}, "created_at": stored.created_at})


def test_stats_count_each_request_once_per_course(world):
    for index in range(3):
        write_chat_log(world.url, world.log(f"s{index}" + "0" * 24))
    write_chat_log(world.url, world.log("n0" + "0" * 24, user=world.bob, outcome="not_covered",
                                        reason="below_similarity_threshold"))
    write_chat_log(world.url, world.log("e0" + "0" * 24, outcome="error", error_code="LLM_UNAVAILABLE",
                                        error_reason="timeout"))
    write_chat_log(world.url, world.log("o0" + "0" * 24, course=world.other))
    with pytest.raises(sqlite3.IntegrityError):  # the same request cannot be counted again
        write_chat_log(world.url, world.log("s0" + "0" * 24))

    stats = chat_stats(world.url, course_id=world.course)
    assert stats["requests"] == 5
    assert stats["users"] == 2
    assert stats["outcomes"] == {"answered": 3, "not_covered": 1, "error": 1, "aborted": 0}
    assert stats["not_covered_reasons"] == {"below_similarity_threshold": 1}
    assert stats["error_codes"] == {"LLM_UNAVAILABLE": 1}
    assert stats["latency_ms"] == {"avg": 10.0, "max": 10}
    assert chat_stats(world.url, course_id=world.other)["requests"] == 1
    assert chat_stats(world.url, course_id=world.course, since="2999-01-01T00:00:00Z")["requests"] == 0


def test_rows_older_than_thirty_days_are_removed_on_the_next_write(world):
    write_chat_log(world.url, world.log("old" + "0" * 23))
    write_chat_log(world.url, world.log("kept" + "0" * 22))
    with connect(world.url) as db:
        db.execute("UPDATE chat_logs SET created_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-31 days')"
                   " WHERE request_id LIKE 'old%'")
        db.execute("UPDATE chat_logs SET created_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-29 days')"
                   " WHERE request_id LIKE 'kept%'")
    assert len(world.rows()) == 2  # no write, no cleanup
    write_chat_log(world.url, world.log("new" + "0" * 23))
    assert {log.request_id[:3] for log in world.rows()} == {"kep", "new"}


def test_no_column_can_hold_answer_text_or_raw_model_output(world):
    with connect(world.url) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(chat_logs)")}
    assert columns == {
        "request_id", "user_id", "course_id", "version_id", "question", "outcome", "reason",
        "error_code", "error_reason", "citations_json", "unknown_citation_count",
        "invalidation_subtype", "uncovered_unit_count", "truncated", "latency_ms",
        "first_delta_latency_ms", "created_at",
    }


# --- recorder on the real J07 event path -----------------------------------


def _prepared(world, request_id="req" + "0" * 23):
    version = PublishedVersion(world.course, world.version, 1, frozenset({"rev-1"}))
    chunk = EvidenceChunk(1, "chunk-1", "rev-1", "document", 1, None, "栈是一种线性表。", 0.9,
                          ("vector",), (), 20)
    context = EvidenceContext(ContextStatus.READY, None, (chunk,), GraphContext(), 1, ContextStats())
    now = time.monotonic()
    return PreparedChat(version, request_id, now, now + 60, "栈是什么？", context)


def _service(*parts):
    def supplier():
        for part in parts:
            yield StreamDelta(part)
        yield StreamDone(ModelResult("".join(parts), "fake", "fake", None, "stop"))

    generator = type("Generator", (), {"generate": lambda self, *a, **k: AnswerGeneration(supplier, lambda: 60)})()
    return ChatService(Settings(), None, None, None, generator)


def _audit(world, prepared):
    return ChatAudit(world.url, request_id=prepared.request_id, user_id=world.alice.id,
                     version=prepared.version, question="栈是什么？", started=prepared.started)


def _run(world, *parts):
    prepared = _prepared(world)
    audit = _audit(world, prepared)
    for event in _service(*parts).events(prepared, audit=audit):
        audit.observe(event)
    assert audit.record() is True
    return get_chat_log(world.url, course_id=world.course, request_id=prepared.request_id)


def test_answered_request_logs_citation_ids_but_not_answer_text(world):
    log = _run(world, "栈是一种", "线性表[1]。")
    assert (log.outcome, log.reason, log.citations) == ("answered", None, ((1, "chunk-1"),))
    assert (log.unknown_citation_count, log.invalidation_subtype, log.truncated) == (0, None, False)
    assert log.first_delta_latency_ms is not None and log.first_delta_latency_ms <= log.latency_ms
    with connect(world.url) as db:
        stored = " ".join(str(value) for value in db.execute("SELECT * FROM chat_logs").fetchone())
    assert "线性表" not in stored


def test_unknown_only_citations_log_subtype_and_count(world):
    log = _run(world, "栈是一种线性表[9]。")
    assert (log.outcome, log.reason) == ("not_covered", "all_citations_invalidated")
    assert (log.invalidation_subtype, log.unknown_citation_count, log.citations) == ("unknown_only", 1, ())


def test_uncited_sentence_logs_uncovered_unit_count(world):
    log = _run(world, "栈是一种线性表[1]。队列先进先出。")
    assert (log.outcome, log.invalidation_subtype) == ("not_covered", "uncited_sentence")
    assert log.uncovered_unit_count == 1


def test_record_writes_once_and_a_storage_failure_does_not_raise(world, tmp_path, caplog):
    prepared = _prepared(world)
    audit = _audit(world, prepared)
    assert audit.record() is True
    assert audit.record() is False
    assert [log.outcome for log in world.rows()] == ["aborted"]

    broken = ChatAudit(f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}", request_id="z" * 26,
                       user_id=world.alice.id, version=prepared.version, question="敏感原问题", started=prepared.started)
    assert broken.record() is False
    assert "chat log not written" in caplog.text and "z" * 26 in caplog.text
    assert "敏感原问题" not in caplog.text


# --- HTTP route --------------------------------------------------------------


class ScriptedService:
    """Stands in for ChatService behind ``app.state.chat_service``."""

    def __init__(self, events=(), prepare_error=None):
        self.script = list(events)
        self.prepare_error = prepare_error

    def prepare(self, *, version, request_id, started, **_):
        if self.prepare_error is not None:
            raise self.prepare_error
        return type("Prepared", (), {"request_id": request_id, "version": version, "started": started})()

    def events(self, prepared, stop=None, audit=None):
        for event in self.script:
            if event["event"] == "done" and audit is not None:
                audit.diagnose(unknown_count=0, invalidation_subtype=None, uncited_units=0, truncated=True)
            yield json.loads(json.dumps(event).replace("REQ", prepared.request_id))


def _answered():
    return [
        {"event": "meta", "status": "answered", "retrieved": 1, "graph_version": 1, "request_id": "REQ"},
        {"event": "delta", "delta": "栈是一种线性表"},
        {"event": "delta", "delta": "[1]。"},
        {"event": "done", "final": {"status": "answered", "answer": "栈是一种线性表[1]。",
                                    "citations": [{"index": 1, "chunk_id": "chunk-1"}], "related_kp_ids": [],
                                    "graph_version": 1, "request_id": "REQ", "latency_ms": 33}},
    ]


@pytest.fixture
def api(world, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", world.url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    with TestClient(create_app()) as client:
        yield client


def _chat(client, world, *, user=None, course=None, stream=False):
    user = user or world.alice
    token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                               issued_at=int(time.time()), ttl_seconds=3600)
    accept = "text/event-stream" if stream else "application/json"
    return client.post(f"/api/v1/courses/{course or world.course}/chat", json={"question": "栈是什么？"},
                       headers={"Authorization": f"Bearer {token}", "Accept": accept})


def _wait_rows(world, count):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = world.rows()
        if len(rows) >= count:
            return rows
        time.sleep(0.02)
    return world.rows()


def test_json_answer_writes_one_complete_row(world, api):
    api.app.state.chat_service = ScriptedService(_answered())
    response = _chat(api, world)
    assert response.status_code == 200, response.text
    [log] = world.rows()
    assert log.request_id == response.json()["request_id"]
    assert (log.user_id, log.course_id, log.version_id) == (world.alice.id, world.course, world.version)
    assert (log.outcome, log.latency_ms, log.citations, log.truncated) == ("answered", 33, ((1, "chunk-1"),), True)
    assert log.question == "栈是什么？"
    assert log.first_delta_latency_ms is not None


def test_failure_after_binding_logs_error_with_code_and_reason(world, api):
    api.app.state.chat_service = ScriptedService(
        prepare_error=ChatFailure("LLM_UNAVAILABLE", reason="timeout"))
    response = _chat(api, world)
    assert response.status_code == 503
    [log] = world.rows()
    assert log.request_id == response.json()["details"]["request_id"]
    assert (log.outcome, log.error_code, log.error_reason) == ("error", "LLM_UNAVAILABLE", "timeout")
    assert log.version_id == world.version and log.first_delta_latency_ms is None


def test_generation_error_event_is_logged_as_error(world, api):
    error = {"code": "BUDGET_EXCEEDED", "message": "m", "details": {"request_id": "REQ"}}
    api.app.state.chat_service = ScriptedService([_answered()[0], {"event": "error", "error": error}])
    assert _chat(api, world).status_code == 429
    [log] = world.rows()
    assert (log.outcome, log.error_code, log.error_reason) == ("error", "BUDGET_EXCEEDED", None)


def test_requests_rejected_before_binding_write_no_row(world, api):
    api.app.state.chat_service = ScriptedService(_answered())
    assert _chat(api, world, course=world.unpublished).status_code == 404
    assert _chat(api, world, user=world.outsider).status_code == 403
    assert _chat(api, world, user=world.teacher).status_code == 403
    for course in (world.course, world.other, world.unpublished):
        assert world.rows(course) == []


def test_sse_stream_logs_once_and_a_retry_is_a_new_row(world, api):
    api.app.state.chat_service = ScriptedService(_answered())
    first = _chat(api, world, stream=True)
    second = _chat(api, world, stream=True)
    assert first.status_code == second.status_code == 200
    assert "event: done" in first.text
    rows = _wait_rows(world, 2)
    assert len(rows) == 2 and len({log.request_id for log in rows}) == 2
    assert all(log.outcome == "answered" and log.first_delta_latency_ms is not None for log in rows)
    assert chat_stats(world.url, course_id=world.course)["requests"] == 2


def test_client_disconnect_before_terminal_is_logged_as_aborted(world):
    class Disconnected:
        async def is_disconnected(self):
            return True

    prepared = type("Prepared", (), {"request_id": "ab" + "0" * 24})()
    audit = ChatAudit(world.url, request_id=prepared.request_id, user_id=world.alice.id,
                      version=PublishedVersion(world.course, world.version, 1, frozenset()),
                      question="栈是什么？", started=time.monotonic())

    async def drain():
        return [chunk async for chunk in chat_api._stream(Disconnected(), ScriptedService(_answered()),
                                                          prepared, audit)]

    assert asyncio.run(drain()) == []
    [log] = _wait_rows(world, 1)
    assert (log.request_id, log.outcome, log.citations) == (prepared.request_id, "aborted", ())


def test_first_terminal_event_wins_and_later_deltas_do_not_move_first_delta(world):
    prepared = _prepared(world)
    audit = _audit(world, prepared)
    done, late_error = _answered()[3], {"event": "error", "error": {"code": "INTERNAL_ERROR", "details": {}}}
    done = json.loads(json.dumps(done).replace("REQ", prepared.request_id))
    for event in (done, late_error, {"event": "delta", "delta": "x"}):
        audit.observe(event)
    log = audit.build()
    assert (log.outcome, log.error_code, log.first_delta_latency_ms) == ("answered", None, None)
