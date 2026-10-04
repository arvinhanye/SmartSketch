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
        pass

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
