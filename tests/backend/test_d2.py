"""D2：共享向量调用按 ADR-011 修订 2 决定 12 记账（ADR-082 决定 6）。

每次实际向量请求：发出前预写 ``sent``（失败则不发），之后按 ``call_id`` 回写结果与 usage；缓存命中不发请求、
不记新行；多批各记一行；归属课程与请求（问答 ``request_id`` / 发布 ``publish:<version_id>``）；
向量费用归部署者，不进个人或全站的生成模型日预算。发布路径的端到端在 ``tests/integration/test_d2_publish.py``。
"""
from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.repositories.model_calls import EMBEDDING_PURPOSE, CallRecord, SqliteCallStore, billed_for_day
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import EmbeddingResult, ModelServerError, Usage
from app.services.ai.embeddings import EmbeddingAdapter, EmbeddingRecordError, embedding_calls
from app.services.ai.factory import build_embedding_adapter
from app.services.qa.chat import ChatFailure, ChatService
from app.services.versions.resolver import PublishedVersion

COURSE = "c" * 32
SETTINGS = dict(EMBEDDING_MODE="fake", EMBEDDING_DIMENSIONS=2, EMBEDDING_BATCH_SIZE=2)


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _rows(url):
    with connect(url) as database:
        return database.execute(
            "SELECT call_id, status, course_id, task_id, request_id, purpose, user_id, usage_input, usage_output,"
            " max_output_tokens, error_class FROM model_calls ORDER BY created_at, call_id").fetchall()


class Client:
    """Records whether the ``sent`` row already existed when the request went out."""

    def __init__(self, url, *, usage=True, fail=None):
        self.url, self.usage, self.fail = url, usage, fail
        self.requests, self.rows_at_send = [], []

    def embed(self, request):
        self.requests.append(request)
        self.rows_at_send.append([row[1] for row in _rows(self.url)])
        if self.fail is not None:
            raise self.fail
        return EmbeddingResult(tuple((1.0, 0.0) for _ in request.texts), request.model, request.model,
                               Usage(7 * len(request.texts), 0) if self.usage else None)


def _adapter(url, client, store=None):
    return EmbeddingAdapter(Settings(**SETTINGS), client, store=store if store is not None else SqliteCallStore(url))


def test_each_real_request_is_prewritten_then_finished(url):
    client = Client(url)
    with embedding_calls(course_id=COURSE, request_id="req-1"):
        _adapter(url, client).embed(("栈", "队列", "树"))          # 批大小 2 → 两次请求
    rows = _rows(url)
    assert len(rows) == 2 and len({row[0] for row in rows}) == 2
    assert client.rows_at_send == [["sent"], ["ok", "sent"]]       # 发出时本次的 sent 行已存在
    for row in rows:
        assert row[1:7] == ("ok", COURSE, None, "req-1", EMBEDDING_PURPOSE, None)
        assert row[9] == 0
    assert sorted(row[7] for row in rows) == [7, 14] and all(row[8] == 0 for row in rows)


def test_cache_hit_adds_no_row(url):
    client = Client(url)
    adapter = _adapter(url, client)
    with embedding_calls(course_id=COURSE, request_id="req-1"):
        adapter.embed(("栈",))
    with embedding_calls(course_id=COURSE, request_id="req-2"):
        adapter.embed(("栈",))
    assert len(client.requests) == 1 and len(_rows(url)) == 1


def test_prewrite_failure_sends_nothing(url):
    class BrokenStore:
        def prewrite(self, record, *, task_budget, daily_budget):
            raise OSError("disk full")

        def finish(self, outcome):
            raise AssertionError("must not finish an unsent call")

    client = Client(url)
    with embedding_calls(course_id=COURSE, request_id="req-1"):
        with pytest.raises(EmbeddingRecordError):
            _adapter(url, client, BrokenStore()).embed(("栈",))
    assert client.requests == []


def test_provider_failure_is_recorded_as_error(url):
    client = Client(url, fail=ModelServerError("text-embedding-v4"))
    with embedding_calls(course_id=COURSE, request_id="req-1"):
        with pytest.raises(Exception):
            _adapter(url, client).embed(("栈",))
    [row] = _rows(url)
    assert (row[1], row[10]) == ("error", "server")


def test_missing_usage_is_kept_null(url):
    with embedding_calls(course_id=COURSE, request_id="req-1"):
        _adapter(url, Client(url, usage=False)).embed(("栈",))
    [row] = _rows(url)
    assert (row[1], row[7], row[8]) == ("ok", None, None)


def test_recording_adapter_refuses_unattributed_calls(url):
    client = Client(url)
    with pytest.raises(RuntimeError):
        _adapter(url, client).embed(("栈",))
    assert client.requests == [] and _rows(url) == []


def test_vector_rows_never_count_against_generation_budgets(url):
    with embedding_calls(course_id=COURSE, request_id="req-1", user_id="alice"):
        _adapter(url, Client(url)).embed(("栈", "队列", "树", "图"))
    assert billed_for_day(url) == 0
    record = CallRecord(call_id=uuid.uuid4().hex, course_id=COURSE, task_id=None, chunk_id=None, request_id="r",
                        purpose="answer_with_context", task_attempt=None, chunk_attempt=None, call_seq=1,
                        provider_role="primary", is_repair=False, model_requested="m", input_tokens_est=1,
                        max_output_tokens=1, user_id="alice")
    SqliteCallStore(url).prewrite(record, task_budget=10, daily_budget=3)   # 没有被向量用量挤占


def test_only_real_online_embedding_is_recorded(url):
    assert build_embedding_adapter(Settings(SQLITE_URL=url, **SETTINGS)).records_calls is False
    online = Settings(SQLITE_URL=url, EMBEDDING_MODE="online", EMBEDDING_MODEL="text-embedding-v4",
                      EMBEDDING_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1",
                      EMBEDDING_API_KEY="sk-deployer", EMBEDDING_DIMENSIONS=1024, EMBEDDING_BATCH_SIZE=10)
    assert build_embedding_adapter(online).records_calls is True


def test_chat_query_embedding_is_attributed_to_the_request(url):
    settings = Settings(SQLITE_URL=url, **SETTINGS)
    client = Client(url)
    rewriter = SimpleNamespace(rewrite=lambda question, history, **kw: SimpleNamespace(query=question))
    service = ChatService(settings, None, _adapter(url, client), rewriter, None)
    version = PublishedVersion(COURSE, "v" * 26, 1, frozenset({"revision"}))
    with pytest.raises(ChatFailure):          # 本测试没有图库与向量空间：检索阶段失败，但向量调用已记账
        service.prepare(version=version, request_id="chat-req", started=time.monotonic(),
                        question="什么是栈？", history=None, kp_id=None)
    [row] = _rows(url)
    assert row[1:6] == ("ok", COURSE, None, "chat-req", EMBEDDING_PURPOSE)


def test_chat_record_failure_is_storage_unavailable_and_sends_nothing(url):
    class BrokenStore:
        def prewrite(self, record, *, task_budget, daily_budget):
            raise OSError("disk full")

        def finish(self, outcome):
            pass

    settings = Settings(SQLITE_URL=url, **SETTINGS)
    client = Client(url)
    rewriter = SimpleNamespace(rewrite=lambda question, history, **kw: SimpleNamespace(query=question))
    service = ChatService(settings, None, _adapter(url, client, BrokenStore()), rewriter, None)
    version = PublishedVersion(COURSE, "v" * 26, 1, frozenset({"revision"}))
    with pytest.raises(ChatFailure) as caught:
        service.prepare(version=version, request_id="chat-req", started=time.monotonic(),
                        question="什么是栈？", history=None, kp_id=None)
    assert caught.value.code == "STORAGE_UNAVAILABLE"
    assert client.requests == []
