"""D3：问答链路共享一个单调时钟截止时刻（ADR-082 决定 3）。

覆盖：改写耗尽预算后不再出站；查询向量请求携带剩余预算；HTTP 传输把解析、多地址连接、握手、
等待响应头与读取都约束在同一预算内，到期即关闭连接（不是外层先返回、请求在后台继续）；缓存命中
不出站；图库读取带剩余时间；超时为 ``LLM_UNAVAILABLE`` / ``timeout``，两种传输与日志一致。
发布与离线向量不带截止时刻，沿用各自的单次请求时限。
"""
from __future__ import annotations

import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.dependencies import course_student
from app.config import Settings
from app.repositories.chat_logs import list_chat_logs
from app.repositories.neo4j import GraphScope, Neo4jRepository, RepositoryError, read_deadline
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import EmbeddingRequest, EmbeddingResult, ModelTimeoutError
from app.services.ai.compatible import CompatibleEmbeddingClient, StdlibTransport
from app.services.ai.embeddings import EmbeddingAdapter, EmbeddingDeadlineExceeded
from app.services.ai.outbound import GuardedTransport
from app.services.qa.chat import ChatFailure, ChatService
from app.services.versions.resolver import PublishedVersion

SLACK = 0.25          # 调度误差余量；业务时限本身不放宽
COURSE, VERSION_ID = "c" * 32, "v" * 26
VERSION = PublishedVersion(COURSE, VERSION_ID, 1, frozenset({"revision"}))


def _finishes_within(seconds, work):
    """Run ``work`` in a thread; fail (instead of hanging the suite) if it outlives ``seconds``."""
    outcome = {}

    def run():
        started = time.monotonic()
        try:
            outcome["value"] = work()
        except BaseException as error:  # noqa: BLE001 - re-raised below
            outcome["error"] = error
        outcome["elapsed"] = time.monotonic() - started

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds + 3)
    assert not thread.is_alive(), "outbound work was not bounded by the deadline"
    return outcome


# ---- 传输层：同一预算覆盖解析、连接、等待响应 ---------------------------------------------------

def _slow_resolver(delay, calls):
    def resolve(host, port):
        calls.append(host)
        time.sleep(delay)
        return ["127.0.0.1"]
    return resolve


@pytest.mark.parametrize("kind", ["stdlib", "guarded"])
def test_dns_hang_is_bounded_and_nothing_connects(kind):
    resolved, connected = [], []

    def connector(address, timeout):
        connected.append(address)
        raise OSError("must not connect")

    resolver = _slow_resolver(2.0, resolved)
    transport = (StdlibTransport(resolver=resolver, connector=connector) if kind == "stdlib"
                 else GuardedTransport(allow_private=True, resolver=resolver, connector=connector))
    outcome = _finishes_within(0.3, lambda: transport.open("http://model.test:9/v1/x", b"{}", {}, 0.3))
    assert isinstance(outcome.get("error"), TimeoutError)
    assert outcome["elapsed"] < 0.3 + SLACK
    assert connected == []


@pytest.mark.parametrize("kind", ["stdlib", "guarded"])
def test_multi_address_attempts_share_one_budget(kind):
    given = []

    def connector(address, timeout):
        given.append(timeout)
        time.sleep(min(timeout, 0.15))
        raise TimeoutError("connect timed out")

    resolver = lambda host, port: ["127.0.0.2", "127.0.0.3", "127.0.0.4", "127.0.0.5"]  # noqa: E731
    transport = (StdlibTransport(resolver=resolver, connector=connector) if kind == "stdlib"
                 else GuardedTransport(allow_private=True, resolver=resolver, connector=connector))
    outcome = _finishes_within(0.3, lambda: transport.open("http://model.test:9/v1/x", b"{}", {}, 0.3))
    assert isinstance(outcome.get("error"), TimeoutError)
    assert outcome["elapsed"] < 0.3 + SLACK
    assert given and all(later < earlier for earlier, later in zip(given, given[1:]))   # 剩余预算递减
    assert given[0] <= 0.3


class _SilentServer:
    """Accepts, reads the request, then either says nothing or drips header bytes; records client EOF."""

    def __init__(self, *, drip=False):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.drip, self.closed_at = drip, None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.sock.accept()
        conn.settimeout(0.02)
        started = time.monotonic()
        if self.drip:
            conn.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
        while time.monotonic() - started < 4:
            try:
                data = conn.recv(65536)
                if data == b"":
                    self.closed_at = time.monotonic()
                    break
            except TimeoutError:
                pass
            except OSError:
                self.closed_at = time.monotonic()
                break
            if self.drip:
                try:
                    conn.sendall(b"a")
                except OSError:
                    self.closed_at = time.monotonic()
                    break
        conn.close()

    def close(self):
        self.sock.close()


@pytest.mark.parametrize("drip", [False, True], ids=["silent", "slow-drip-headers"])
@pytest.mark.parametrize("kind", ["stdlib", "guarded"])
def test_hanging_response_is_cut_at_deadline_and_the_connection_closed(kind, drip):
    server = _SilentServer(drip=drip)
    try:
        transport = (StdlibTransport() if kind == "stdlib"
                     else GuardedTransport(allow_private=True, resolver=lambda host, port: ["127.0.0.1"]))
        started = time.monotonic()
        outcome = _finishes_within(0.3, lambda: transport.open(
            f"http://model.test:{server.port}/v1/x" if kind == "guarded" else f"http://127.0.0.1:{server.port}/v1/x",
            b"{}", {"Content-Type": "application/json"}, 0.3))
        assert isinstance(outcome.get("error"), TimeoutError)
        assert outcome["elapsed"] < 0.3 + SLACK
        server.thread.join(2)
        assert server.closed_at is not None and server.closed_at - started < 0.3 + SLACK   # 实际连接已终止
    finally:
        server.close()


# ---- 向量：请求携带剩余预算；无截止时刻（发布）沿用单次时限；缓存命中不出站 ----------------------------

class RecordingEmbeddingClient:
    def __init__(self, delay=0.0):
        self.requests, self.delay = [], delay

    def embed(self, request):
        self.requests.append(request)
        time.sleep(self.delay)
        return EmbeddingResult(tuple(tuple([1.0] + [0.0] * (request.dimensions - 1)) for _ in request.texts),
                               request.model, request.model, None)


def _adapter(client):
    return EmbeddingAdapter(Settings(), client)


def test_query_embedding_carries_the_remaining_budget():
    client = RecordingEmbeddingClient()
    _adapter(client).embed(("什么是栈？",), deadline=time.monotonic() + 5)
    [request] = client.requests
    assert request.timeout_seconds is not None and 4 < request.timeout_seconds <= 5


def test_publish_embedding_without_deadline_keeps_its_own_timeout():
    client = RecordingEmbeddingClient()
    _adapter(client).embed(("栈", "队列"))
    assert all(request.timeout_seconds is None for request in client.requests)


def test_expired_deadline_sends_no_embedding_request():
    client = RecordingEmbeddingClient()
    with pytest.raises(EmbeddingDeadlineExceeded):
        _adapter(client).embed(("什么是栈？",), deadline=time.monotonic() - 0.01)
    assert client.requests == []


def test_cache_hit_sends_nothing():
    client = RecordingEmbeddingClient()
    adapter = _adapter(client)
    adapter.embed(("什么是栈？",), deadline=time.monotonic() + 5)
    adapter.embed(("什么是栈？",), deadline=time.monotonic() + 5)
    assert len(client.requests) == 1


class BudgetTransport:
    """Honours the timeout it is given: blocks up to ``delay`` but never longer than ``timeout``."""

    def __init__(self, delay):
        self.delay, self.timeouts = delay, []

    def open(self, url, body, headers, timeout):
        self.timeouts.append(timeout)
        time.sleep(min(self.delay, timeout))
        if self.delay >= timeout:
            raise TimeoutError("timed out")
        count = len(json.loads(body)["input"])
        payload = json.dumps({"model": "text-embedding-v4", "data": [
            {"index": i, "embedding": [1.0, 0.0]} for i in range(count)], "usage": {"prompt_tokens": 1}}).encode()
        state = {"data": payload}

        def read(amount, timeout):
            chunk, state["data"] = state["data"][:amount], state["data"][amount:]
            return chunk

        return SimpleNamespace(status=200, header=lambda name: None, read=read, close=lambda: None)


def test_compatible_embedding_batches_share_the_request_budget():
    transport = BudgetTransport(0.15)
    client = CompatibleEmbeddingClient("https://e.example/v1", "sk-e", batch_size=1, transport=transport,
                                       default_timeout_seconds=60)
    with pytest.raises(ModelTimeoutError):
        client.embed(EmbeddingRequest(model="text-embedding-v4", texts=("a", "b", "c", "d"), dimensions=2,
                                      timeout_seconds=0.4))
    assert transport.timeouts[0] <= 0.4
    assert all(later < earlier for earlier, later in zip(transport.timeouts, transport.timeouts[1:]))
    assert len(transport.timeouts) <= 3


# ---- 图库读取带剩余时间 ------------------------------------------------------------------------

class RecordingDriver:
    def __init__(self):
        self.queries = []

    def execute_query(self, query, parameters_=None, routing_=None, database_=None):
        self.queries.append(query)
        return SimpleNamespace(records=[])


def test_graph_reads_carry_the_remaining_time_and_stop_after_the_deadline():
    driver = RecordingDriver()
    repo = Neo4jRepository(driver)
    scope = GraphScope(course_id=COURSE, version_id=VERSION_ID)
    query = "MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id}) RETURN n"
    with read_deadline(time.monotonic() + 5):
        repo.read(query, scope, reader="student")
    assert 4 < driver.queries[0].timeout <= 5 and driver.queries[0].text == query
    with read_deadline(time.monotonic() - 0.01):
        with pytest.raises(RepositoryError):
            repo.read(query, scope, reader="student")
    assert len(driver.queries) == 1
    repo.read(query, scope, reader="student")           # 没有截止时刻（发布、worker）：原样字符串
    assert driver.queries[-1] == query


# ---- 问答准备阶段 ------------------------------------------------------------------------------

class SlowRewriter:
    def __init__(self, delay):
        self.delay = delay

    def rewrite(self, question, history, *, course_id, request_id, deadline):
        time.sleep(self.delay)
        return SimpleNamespace(query=question)


def _service(embedding_client, *, budget=0.3, rewrite_delay=0.0, url=None):
    settings = Settings(LLM_CHAT_TIMEOUT_SECONDS=budget, LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS=budget / 2,
                        **({"SQLITE_URL": url} if url else {}))
    return ChatService(settings, None, EmbeddingAdapter(settings, embedding_client), SlowRewriter(rewrite_delay), None)


def _prepare(service):
    return service.prepare(version=VERSION, request_id="r", started=time.monotonic(),
                           question="什么是栈？", history=None, kp_id=None)


def _slow_online_client(delay):
    transport = BudgetTransport(delay)
    return CompatibleEmbeddingClient("https://e.example/v1", "sk-e", transport=transport,
                                     default_timeout_seconds=60), transport


def test_slow_query_embedding_times_out_within_the_chat_budget():
    client, transport = _slow_online_client(2.0)
    outcome = _finishes_within(0.3, lambda: _prepare(_service(client)))
    error = outcome.get("error")
    assert isinstance(error, ChatFailure) and (error.code, error.reason) == ("LLM_UNAVAILABLE", "timeout")
    assert outcome["elapsed"] < 0.3 + SLACK
    assert transport.timeouts and transport.timeouts[0] <= 0.3


def test_rewrite_exhausting_the_budget_sends_no_embedding_request():
    client = RecordingEmbeddingClient()
    outcome = _finishes_within(0.3, lambda: _prepare(_service(client, rewrite_delay=0.35)))
    error = outcome.get("error")
    assert isinstance(error, ChatFailure) and (error.code, error.reason) == ("LLM_UNAVAILABLE", "timeout")
    assert client.requests == []


# ---- 两种传输与日志 ---------------------------------------------------------------------------

@pytest.mark.parametrize("accept", ["application/json", "text/event-stream"])
def test_timeout_in_preparation_is_the_same_on_both_transports_and_in_the_log(tmp_path, monkeypatch, accept):
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
    client, _ = _slow_online_client(2.0)
    app = FastAPI()
    app.state.settings = SimpleNamespace(SQLITE_URL=url)
    app.state.chat_service = _service(client, url=url)
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=COURSE), user=SimpleNamespace(id=user_id))
    with TestClient(app) as http:
        started = time.monotonic()
        response = http.post(f"/api/v1/courses/{COURSE}/chat", json={"question": "什么是栈？"},
                             headers={"accept": accept})
        elapsed = time.monotonic() - started
    assert response.status_code == 503 and elapsed < 0.3 + 1.0
    assert response.json()["code"] == "LLM_UNAVAILABLE" and response.json()["details"]["reason"] == "timeout"
    [row] = list_chat_logs(url, user_id=user_id, course_id=COURSE)
    assert (row.outcome, row.error_code, row.error_reason) == ("error", "LLM_UNAVAILABLE", "timeout")
