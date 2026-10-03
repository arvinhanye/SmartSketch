"""L08：问答按本人配置取模型；熔断、预算与调用记录按用户隔离（ADR-080 决定 4）。"""
from __future__ import annotations

import base64
import json
import uuid
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.model_calls import BudgetRejected, CallRecord, SqliteCallStore
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import Message, ModelAuthError, ModelRequest
from app.services.ai.policy import CallAttribution, ModelUnavailableError
from app.services.credentials import CredentialCipher, ModelConfigRequired
from app.services.qa.chat import ChatFailure
from app.services.qa.user_models import UserChatModels

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()


class Transport:
    """200 for every key except those listed in ``bad`` (401)."""

    def __init__(self, bad=()):
        self.bad, self.calls = set(bad), []

    def open(self, url, body, headers, timeout):
        key = headers["Authorization"].removeprefix("Bearer ")
        self.calls.append((url, key, json.loads(body)["model"]))
        status = 401 if key in self.bad else 200
        payload = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        state = {"data": payload if status == 200 else b'{"error":{"message":"bad key"}}'}

        def read(amount, timeout):
            chunk, state["data"] = state["data"][:amount], state["data"][amount:]
            return chunk

        return SimpleNamespace(status=status, header=lambda name: None, read=read, close=lambda: None)


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _settings(url, **extra):
    return load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                          "LLM_MAX_RETRIES": "0", "LLM_CIRCUIT_FAILURE_THRESHOLD": "1", **extra})


def _user(url, name):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role="student")


def _configure(url, user, *, base_url="https://a.example/v1", model, key):
    repo.save_config(url, user_id=user.id, base_url=base_url, model=model,
                     sealed=CredentialCipher(ROOT_KEY).seal(user.id, key), key_hint=key[-4:])


def _ask(models, user):
    """One chat-purpose call through the user's generator policy, attributed like a chat request."""
    _, generator = models.for_user(user.id)
    client = generator._policy.bind(CallAttribution(course_id="c1", request_id=uuid.uuid4().hex, user_id=user.id))
    return client.complete(ModelRequest(purpose="answer_with_context", model=generator._model,
                                        messages=(Message("user", "q"),), max_output_tokens=8))


def test_unconfigured_user_is_refused(url):
    alice = _user(url, "alice01")
    with pytest.raises(ModelConfigRequired):
        UserChatModels(_settings(url), transport=Transport()).for_user(alice.id)


def test_each_user_calls_with_own_key_and_model(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    _configure(url, alice, model="model-a", key="sk-alice-0001")
    _configure(url, bob, base_url="https://b.example/v1", model="model-b", key="sk-bob-0002")
    transport = Transport()
    models = UserChatModels(_settings(url), transport=transport)
    _ask(models, alice)
    _ask(models, bob)
    assert transport.calls == [
        ("https://a.example/v1/chat/completions", "sk-alice-0001", "model-a"),
        ("https://b.example/v1/chat/completions", "sk-bob-0002", "model-b"),
    ]
    with connect(url) as database:
        assert database.execute("SELECT user_id FROM model_calls ORDER BY rowid").fetchall() == [
            (alice.id,), (bob.id,)]


def test_one_users_bad_key_does_not_break_another(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    _configure(url, alice, model="m", key="sk-bad-0000")
    _configure(url, bob, model="m", key="sk-good-0001")
    models = UserChatModels(_settings(url), transport=Transport(bad={"sk-bad-0000"}))
    for _ in range(2):                            # 被供应商拒绝，或本人的熔断已打开——都只落在 alice 身上
        with pytest.raises((ModelAuthError, ModelUnavailableError)):
            _ask(models, alice)
    assert _ask(models, bob).text == "ok"        # bob 不受影响
    assert models.for_user(alice.id)[1]._policy is not models.for_user(bob.id)[1]._policy


def test_new_config_version_replaces_cached_models(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="old", key="sk-old-0001")
    transport = Transport()
    models = UserChatModels(_settings(url), transport=transport)
    first = models.for_user(alice.id)
    assert models.for_user(alice.id)[1] is first[1]
    _configure(url, alice, model="new", key="sk-new-0002")
    _ask(models, alice)
    assert transport.calls[-1][1:] == ("sk-new-0002", "new")
    repo.delete_config(url, alice.id)
    with pytest.raises(ModelConfigRequired):
        models.for_user(alice.id)


def test_cache_is_bounded(url):
    users = [_user(url, f"user{i:04d}") for i in range(3)]
    for user in users:
        _configure(url, user, model="m", key=f"sk-key-{user.username}")
    models = UserChatModels(_settings(url), transport=Transport(), capacity=2)
    for user in users:
        models.for_user(user.id)
    assert len(models) == 2


def _record(user_id, call_id=None):
    return CallRecord(call_id=call_id or uuid.uuid4().hex, course_id="c1", task_id=None, chunk_id=None,
                      request_id=uuid.uuid4().hex, purpose="answer_with_context", task_attempt=None,
                      chunk_attempt=None, call_seq=1, provider_role="primary", is_repair=False,
                      model_requested="m", input_tokens_est=60, max_output_tokens=60, user_id=user_id)


def test_daily_budget_is_per_user(url):
    store = SqliteCallStore(url)
    store.prewrite(_record("alice"), task_budget=10**6, daily_budget=100)   # billed estimate: 120
    with pytest.raises(BudgetRejected):
        store.prewrite(_record("alice"), task_budget=10**6, daily_budget=100)
    store.prewrite(_record("bob"), task_budget=10**6, daily_budget=100)       # bob has his own budget


def test_calls_without_user_keep_the_global_budget(url):
    store = SqliteCallStore(url)
    store.prewrite(_record(None), task_budget=10**6, daily_budget=100)
    with pytest.raises(BudgetRejected):
        store.prewrite(_record(None), task_budget=10**6, daily_budget=100)


def test_chat_failure_status_for_missing_config():
    failure = ChatFailure("MODEL_CONFIG_REQUIRED")
    assert failure.status_code == 409
    assert failure.body("r1")["code"] == "MODEL_CONFIG_REQUIRED"


def test_chat_requires_model_config(url, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import chat as chat_api
    from app.api.dependencies import course_student
    from app.services.versions.resolver import PublishedVersion

    student = _user(url, "alice01")
    course_id, version_id = "c" * 32, "v" * 26
    with connect(url) as database:
        database.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Course', ?)", (course_id, student.id))
        database.execute(
            "INSERT INTO graph_versions(version_id, course_id, kind, expires_at) VALUES (?, ?, 'publish', 1)",
            (version_id, course_id))
    version = PublishedVersion(course_id, version_id, 1, frozenset())
    monkeypatch.setattr(chat_api, "resolve_published", lambda *_: version)
    app = FastAPI()
    app.state.settings = _settings(url)
    app.state.chat_service = object()   # 基础服务不会被用到：未配置在取模型时就被拒绝
    app.include_router(chat_api.router)
    app.dependency_overrides[course_student] = lambda: SimpleNamespace(
        course=SimpleNamespace(id=course_id), user=SimpleNamespace(id=student.id))

    with TestClient(app) as client:
        response = client.post(f"/api/v1/courses/{course_id}/chat", json={"question": "什么是栈？"},
                               headers={"accept": "application/json"})

    assert response.status_code == 409
    assert response.json()["code"] == "MODEL_CONFIG_REQUIRED"
    with connect(url) as database:
        assert database.execute("SELECT outcome, error_code FROM chat_logs").fetchall() == [
            ("error", "MODEL_CONFIG_REQUIRED")]
        assert database.execute("SELECT count(*) FROM model_calls").fetchone() == (0,)
