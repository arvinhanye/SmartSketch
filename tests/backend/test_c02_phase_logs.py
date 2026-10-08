"""C02-3 / C03-2 续：问答准备与抽取任务的阶段耗时日志（只写日志，不改行为、不加迁移）。

复核（`docs/reviews/claude-deepseek-c02-4-c03-1.md`）留下两段未归因时间：问答冷启动首问在查询向量之后、生成之前有 8.15 秒
没有任何调用记录；抽取末次模型调用之后到待审核有 15.6 秒。现有字段无法定位，这里给每段一行结构化 INFO 日志。
"""

from __future__ import annotations

import logging
import re
import time
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.repositories.task_leases import Lease
from app.services.qa import chat as chat_module
from app.services.qa.chat import ChatFailure, ChatService
from app.services.versions.resolver import PublishedVersion
from app.workers import persist_graph
from app.workers.extract_task import ExtractStatus
from app.workers.parse_task import ParseStatus

VERSION = PublishedVersion("c" * 32, "v" * 26, 1, frozenset({"revision"}))


def _fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", line))


# ---------------------------------------------------------------- 问答准备


class _Rewriter:
    def rewrite(self, question, history, *, course_id, request_id, deadline):
        return SimpleNamespace(query=question)


class _Embedding:
    def embed(self, texts, *, deadline):
        return [[0.1, 0.2]]


def _chat(monkeypatch, *, slow_vector: float = 0.0, fail_subgraph: bool = False) -> ChatService:
    def search_chunks(*args, **kwargs):
        time.sleep(slow_vector)
        return []

    def search_subgraph(*args, **kwargs):
        if fail_subgraph:
            raise chat_module.RepositoryError()
        return None

    monkeypatch.setattr(chat_module, "search_chunks", search_chunks)
    monkeypatch.setattr(chat_module, "search_subgraph", search_subgraph)
    monkeypatch.setattr(chat_module, "build_context", lambda **kwargs: SimpleNamespace(chunks=(), covered=False))
    service = ChatService(Settings(LLM_CHAT_TIMEOUT_SECONDS=15), None, _Embedding(), _Rewriter(), None)
    service.current_space = lambda: "real/x/2"
    return service


def _prepare(service: ChatService):
    return service.prepare(version=VERSION, request_id="req-1", started=time.monotonic(), question="什么是栈",
                           history=None, kp_id=None)


def test_prepare_logs_one_line_with_every_phase(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=chat_module.logger.name)
    _prepare(_chat(monkeypatch, slow_vector=0.05))
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chat prepare phases")]
    fields = _fields(line)
    assert fields["request_id"] == "req-1" and fields["outcome"] == "ok"
    for name in ("since_request_ms", "rewrite_ms", "embed_ms", "space_ms", "vector_ms", "subgraph_ms", "context_ms",
                 "total_ms"):
        assert fields[name].isdigit(), name
    assert int(fields["vector_ms"]) >= 50
    assert "什么是栈" not in line                          # 不记问题与资料原文


def test_prepare_logs_completed_phases_even_when_a_step_fails(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=chat_module.logger.name)
    with pytest.raises(ChatFailure):
        _prepare(_chat(monkeypatch, fail_subgraph=True))
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("chat prepare phases")]
    fields = _fields(line)
    assert fields["outcome"] == "STORAGE_UNAVAILABLE"
    assert fields["vector_ms"].isdigit() and "context_ms" not in fields


# ---------------------------------------------------------------- 抽取任务阶段


def _lease(stage: str = "parsing") -> Lease:
    return Lease(task_id="t1", course_id="c1", document_id="d1", stage=stage, progress=0.0, attempt=1,
                 owner="w", token="tok", expires_at=0)


class _Heartbeat:
    def __init__(self, *args, **kwargs):
        self.guard = SimpleNamespace(check=lambda: None, remaining=lambda: 40)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_pipeline_logs_each_stage_duration(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=persist_graph.logger.name)
    monkeypatch.setattr(persist_graph, "reclaim_expired", lambda *a, **k: SimpleNamespace(cleanup_pending=()))
    monkeypatch.setattr(persist_graph, "claim_next", lambda *a, **k: _lease())
    monkeypatch.setattr(persist_graph, "LeaseHeartbeat", _Heartbeat)
    monkeypatch.setattr(persist_graph, "ExtractLimits", SimpleNamespace(from_settings=lambda s: None))

    def slow(result, seconds=0.0):
        def run(*args, **kwargs):
            time.sleep(seconds)
            return result
        return run

    monkeypatch.setattr(persist_graph, "run_parse_stage", slow(SimpleNamespace(status=ParseStatus.ADVANCED)))
    monkeypatch.setattr(persist_graph, "run_extract_stage", slow(SimpleNamespace(status=ExtractStatus.ADVANCED)))
    monkeypatch.setattr(persist_graph, "run_merge_stage",
                        slow(SimpleNamespace(status=persist_graph.PersistStatus.ADVANCED), 0.03))
    monkeypatch.setattr(persist_graph, "run_persist_stage",
                        slow(SimpleNamespace(status=persist_graph.PersistStatus.ADVANCED), 0.05))
    settings = SimpleNamespace(SQLITE_URL="sqlite:///unused", STORAGE_DIR="unused", UPLOAD_MAX_BYTES=1,
                               TASK_LEASE_SECONDS=60, TASK_MAX_ATTEMPTS=3)
    result = persist_graph.run_pipeline_once(settings, toolkit=lambda lease: object(), repo=None, storage=object())
    assert [stage for stage, _ in result.stages] == ["parsing", "extracting", "merging", "persisting"]
    lines = [_fields(r.getMessage()) for r in caplog.records if r.getMessage().startswith("task stage done")]
    assert [f["stage"] for f in lines] == ["parsing", "extracting", "merging", "persisting"]
    assert all(f["task_id"] == "t1" and f["duration_ms"].isdigit() for f in lines)
    assert int(lines[2]["duration_ms"]) >= 30 and int(lines[3]["duration_ms"]) >= 50


# ---------------------------------------------------------------- C-ACC-B 入库子步骤计时

from contextlib import contextmanager

from app.repositories.neo4j import RepositoryError
from app.repositories.task_leases import LeaseLost


class _Sleep:
    """按名字给每个被替换的步骤一个可区分的耗时（毫秒）。"""

    def __init__(self, ms: int, result=None, exc: Exception | None = None):
        self.ms, self.result, self.exc = ms, result, exc

    def __call__(self, *args, **kwargs):
        time.sleep(self.ms / 1000)
        if self.exc is not None:
            raise self.exc
        return self.result


class _Repo:
    """Explicit transaction recorder; the worker no longer transparently retries."""

    def __init__(self, attempts: int = 1, exc: Exception | None = None):
        self.exc = exc

    @contextmanager
    def persist_write_transaction(self, scope, *, check, remaining):
        def commit(*, started_at):
            if self.exc is not None:
                raise self.exc
        yield SimpleNamespace(commit=commit, deadline=time.monotonic()+remaining(), commit_started=False, committed=False)


SENTINEL_NAME = "绝不应出现在日志里的知识点名"


def _persist(monkeypatch, caplog, *, lock=object(), repo=None, lease_check=None, released=None,
             held_context=None):
    caplog.set_level(logging.INFO, logger=persist_graph.logger.name)
    if lock is not None:
        lock = SimpleNamespace(expires_at=int(time.time()) + 60, token="lock-token")
    written = SimpleNamespace(nodes=None, relations=None, downgraded=())
    monkeypatch.setattr(persist_graph, "load_candidates", _Sleep(20, SimpleNamespace(name=SENTINEL_NAME)))
    monkeypatch.setattr(persist_graph, "build_plan", _Sleep(5, SimpleNamespace()))
    monkeypatch.setattr(persist_graph, "_source_chunk_ids", lambda plan: [])
    monkeypatch.setattr(persist_graph, "get_chunks", _Sleep(10, ()))
    monkeypatch.setattr(persist_graph.course_locks, "acquire", _Sleep(30, lock))

    @contextmanager
    def held(*args, **kwargs):
        yield lock
        time.sleep(0.015)                                 # 退出时释放锁

    monkeypatch.setattr(persist_graph.course_locks, "held", held_context or held)
    monkeypatch.setattr(persist_graph, "_check_lease", lease_check or _Sleep(2))
    monkeypatch.setattr(persist_graph, "_effective", _Sleep(2, ("t1",)))
    monkeypatch.setattr(persist_graph, "_write_draft", _Sleep(40, written))
    monkeypatch.setattr(persist_graph, "_t6_in", _Sleep(8, 1))

    @contextmanager
    def database(*args, **kwargs):
        if kwargs.get("on_acquired"):
            kwargs["on_acquired"](time.monotonic())
        yield SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: ('awaiting_review', 1, None)))

    monkeypatch.setattr(persist_graph, "persist_transaction", database)
    monkeypatch.setattr(persist_graph, "connect", database)
    outcome = SimpleNamespace(status=persist_graph.PersistStatus.RELEASED)
    monkeypatch.setattr(persist_graph, "_release", released or _Sleep(6, outcome))
    result = persist_graph.run_persist_stage("sqlite:///unused", _lease("persisting"), repo=repo or _Repo(),
                                             max_attempts=3, lock_seconds=60, lock_wait_seconds=60,
                                             task_guard=SimpleNamespace(check=lambda: None, remaining=lambda: 40))
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("persist steps")]
    assert len(lines) == 1
    assert SENTINEL_NAME not in lines[0]
    return result, _fields(lines[0])


def test_persist_logs_every_substep_on_success(monkeypatch, caplog):
    result, f = _persist(monkeypatch, caplog, repo=_Repo())
    assert result.status is persist_graph.PersistStatus.ADVANCED
    assert f["task_id"] == "t1" and f["outcome"] == "advanced"
    for name, at_least in (("candidates_ms", 20), ("plan_ms", 5), ("chunks_ms", 10), ("lock_wait_ms", 30),
                           ("lease_check_ms", 4), ("neo4j_ms", 40), ("t6_ms", 8), ("lock_release_ms", 15)):
        assert int(f[name]) >= at_least, name
    assert f["neo4j_attempts"] == "1"                     # 显式事务没有透明重跑
    assert int(f["total_ms"]) >= 130


def test_persist_logs_completed_steps_when_the_lock_is_not_acquired(monkeypatch, caplog):
    result, f = _persist(monkeypatch, caplog, lock=None)
    assert result.status is persist_graph.PersistStatus.RELEASED
    assert f["outcome"] == "released"
    assert int(f["lock_wait_ms"]) >= 30 and int(f["task_release_ms"]) >= 6
    assert "neo4j_ms" not in f and "t6_ms" not in f


def test_persist_logs_neo4j_failure_and_lost_lease(monkeypatch, caplog):
    result, f = _persist(monkeypatch, caplog, repo=_Repo(exc=RepositoryError()))
    assert result.status is persist_graph.PersistStatus.RELEASED
    assert f["outcome"] == "released" and "neo4j_ms" in f and "t6_ms" in f and f["neo4j_attempts"] == "1"
    caplog.clear()
    result, f = _persist(monkeypatch, caplog, lease_check=_Sleep(1, exc=LeaseLost("lost")))
    assert result.status is persist_graph.PersistStatus.LOST
    assert f["outcome"] == "lost" and "neo4j_ms" not in f


@pytest.mark.parametrize("failure", ["neo4j", "lease", "unlock", "uncaught"])
def test_unlock_is_timed_on_failures_without_changing_cleanup_or_propagation(monkeypatch, caplog, failure):
    import sqlite3

    events = []

    @contextmanager
    def held(*args, **kwargs):
        try:
            yield
        finally:
            events.append("unlock-start")
            time.sleep(0.020)
            events.append("unlock-end")
            if failure == "unlock":
                raise sqlite3.OperationalError("unlock failed")

    def release(*args, **kwargs):
        events.append("task-release")
        return SimpleNamespace(status=persist_graph.PersistStatus.RELEASED)

    exc = RepositoryError() if failure == "neo4j" else KeyError("uncaught") if failure == "uncaught" else None
    kwargs = dict(repo=_Repo(exc=exc), held_context=held, released=release,
                  lease_check=_Sleep(1, exc=LeaseLost("lost")) if failure == "lease" else None)
    if failure == "uncaught":
        with pytest.raises(KeyError, match="uncaught"):
            _persist(monkeypatch, caplog, **kwargs)
        [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("persist steps")]
        f = _fields(line)
        assert f["outcome"] == "KeyError"
    else:
        result, f = _persist(monkeypatch, caplog, **kwargs)
        expected = (persist_graph.PersistStatus.LOST if failure == "lease" else
                    persist_graph.PersistStatus.ADVANCED if failure == "unlock" else persist_graph.PersistStatus.RELEASED)
        assert result.status is expected
    assert events == ["unlock-start", "unlock-end"] + (["task-release"] if failure == "neo4j" else [])
    assert int(f["lock_release_ms"]) >= 20
    assert ("t6_ms" in f) == (failure != "lease")
    assert ("neo4j_ms" in f) == (failure != "lease")
    assert f.get("neo4j_attempts") == (None if failure == "lease" else "1")
