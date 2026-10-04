"""L06：/api/v1/me/model-config——只作用于本人、脱敏、地址校验、测试连接与限流（ADR-080）。"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.sqlite import migrate
from app.services.auth import issue_access_token

SECRET = "l06-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY_B64 = base64.urlsafe_b64encode(bytes(range(32))).decode()
API_KEY = "sk-live-AAAABBBBCCCC1234"
BASE = "/api/v1/me/model-config"


class FakeResponse:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def header(self, name):
        return None

    def read(self, amount, timeout):
        data, self._body = self._body[:amount], self._body[amount:]
        return data

    def close(self):
        pass


class FakeTransport:
    def __init__(self, status=200):
        self.status, self.requests = status, []

    def open(self, url, body, headers, timeout):
        self.requests.append((url, json.loads(body), dict(headers)))
        payload = {"model": "m", "choices": [{"message": {"content": "o"}, "finish_reason": "length"}],
                   "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        if self.status != 200:
            payload = {"error": {"message": f"upstream said no to {headers.get('Authorization')}"}}
        return FakeResponse(self.status, json.dumps(payload).encode())


def _token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                              issued_at=int(time.time()), ttl_seconds=3600)


def _auth(user):
    return {"Authorization": f"Bearer {_token(user)}"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    alice = insert_account(url, account_id=uuid.uuid4().hex, username="alice01", password_hash=VALID_HASH, role="teacher")
    bob = insert_account(url, account_id=uuid.uuid4().hex, username="bob0001", password_hash=VALID_HASH, role="student")
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", "personal")
    monkeypatch.setenv("MODEL_CREDENTIAL_KEY", ROOT_KEY_B64)
    monkeypatch.setattr("app.services.model_configs.system_resolver", lambda host, port: ["1.1.1.1"])
    app = create_app()
    app.state.model_transport = FakeTransport()
    with TestClient(app) as client:
        yield type("Env", (), {"client": client, "url": url, "alice": alice, "bob": bob, "app": app})


def _save(env, user, **body):
    payload = {"base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY, **body}
    return env.client.put(BASE, json=payload, headers=_auth(user))


def test_requires_login(env):
    assert env.client.get(BASE).status_code == 401
    assert env.client.put(BASE, json={}).status_code == 401
    assert env.client.delete(BASE).status_code == 401
    assert env.client.post(f"{BASE}/test").status_code == 401


def test_unconfigured_view(env):
    body = env.client.get(BASE, headers=_auth(env.alice)).json()
    assert body == {"runtime_mode": "personal", "configured": False}


def test_save_returns_masked_view_and_never_the_key(env, caplog):
    caplog.set_level(logging.DEBUG)
    response = _save(env, env.alice)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["configured"] is True and body["key_hint"] == "1234" and body["version"] == 1
    assert body["base_url"] == "https://api.example.com/v1" and body["model"] == "m1"
    again = env.client.get(BASE, headers=_auth(env.alice))
    assert API_KEY not in response.text and API_KEY not in again.text
    assert API_KEY not in caplog.text


def test_configs_are_per_user(env):
    _save(env, env.alice)
    assert env.client.get(BASE, headers=_auth(env.bob)).json()["configured"] is False
    env.client.delete(BASE, headers=_auth(env.bob))
    assert env.client.get(BASE, headers=_auth(env.alice)).json()["configured"] is True


def test_body_cannot_name_another_user(env):
    response = env.client.put(BASE, headers=_auth(env.bob), json={
        "base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY, "user_id": env.alice.id})
    assert response.status_code == 422
    assert repo.get_config(env.url, env.alice.id) is None


def test_key_required_on_first_save_and_when_endpoint_changes(env):
    first = env.client.put(BASE, headers=_auth(env.alice), json={"base_url": "https://api.example.com/v1", "model": "m1"})
    assert first.status_code == 422
    assert first.json()["details"]["fields"] == [{"in": "body", "field": "api_key", "reason": "required_when_endpoint_changes"}]
    _save(env, env.alice)
    keep = env.client.put(BASE, headers=_auth(env.alice), json={"base_url": "https://api.example.com/v1", "model": "m2"})
    assert keep.status_code == 200 and keep.json()["model"] == "m2" and keep.json()["version"] == 2
    moved = env.client.put(BASE, headers=_auth(env.alice), json={"base_url": "https://other.example.com/v1", "model": "m2"})
    assert moved.status_code == 422


@pytest.mark.parametrize("base_url, reason", [
    ("http://api.example.com/v1", "scheme"),
    ("https://u:p@api.example.com/v1", "credentials"),
    ("https://api.example.com/v1?a=1", "query"),
])
def test_rejects_bad_urls(env, base_url, reason):
    response = _save(env, env.alice, base_url=base_url)
    assert response.status_code == 422
    assert response.json()["details"]["fields"] == [{"in": "body", "field": "base_url", "reason": reason}]
    assert API_KEY not in response.text


def test_rejects_private_address(env, monkeypatch):
    monkeypatch.setattr("app.services.model_configs.system_resolver", lambda host, port: ["169.254.169.254"])
    response = _save(env, env.alice, base_url="https://metadata.example.com/v1")
    assert response.status_code == 422
    assert response.json()["details"]["fields"][0]["reason"] == "private_address"
    assert repo.get_config(env.url, env.alice.id) is None


def test_rejects_key_with_spaces(env):
    response = _save(env, env.alice, api_key="sk bad key")
    assert response.status_code == 422
    assert response.json()["details"]["fields"] == [{"in": "body", "field": "api_key", "reason": "invalid_characters"}]


def test_delete_is_idempotent(env):
    _save(env, env.alice)
    assert env.client.delete(BASE, headers=_auth(env.alice)).status_code == 204
    assert env.client.delete(BASE, headers=_auth(env.alice)).status_code == 204
    assert env.client.get(BASE, headers=_auth(env.alice)).json() == {"runtime_mode": "personal", "configured": False}


def test_test_saved_config_sends_one_minimal_request_and_records_result(env):
    _save(env, env.alice)
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert response.status_code == 200 and response.json()["ok"] is True
    [(url, payload, headers)] = env.app.state.model_transport.requests
    assert url == "https://api.example.com/v1/chat/completions"
    assert payload["model"] == "m1" and payload["max_tokens"] == 1
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    view = env.client.get(BASE, headers=_auth(env.alice)).json()
    assert view["last_test"]["ok"] is True


def test_test_failure_reports_class_only(env):
    _save(env, env.alice)
    env.app.state.model_transport = FakeTransport(status=401)
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["error_class"] == "auth"
    assert API_KEY not in response.text and "upstream said no" not in response.text
    assert env.client.get(BASE, headers=_auth(env.alice)).json()["last_test"]["error_class"] == "auth"


def test_test_unsaved_values_does_not_store(env):
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice), json={
        "base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY})
    assert response.status_code == 200 and response.json()["ok"] is True
    assert repo.get_config(env.url, env.alice.id) is None


def test_test_without_body_and_without_config(env):
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert response.status_code == 409 and response.json()["code"] == "MODEL_CONFIG_REQUIRED"


def test_test_with_partial_body(env):
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice), json={"model": "m1"})
    assert response.status_code == 422


def test_test_blocked_address_is_reported_without_a_request(env, monkeypatch):
    monkeypatch.setattr("app.services.model_configs.system_resolver", lambda host, port: ["10.0.0.1"])
    response = env.client.post(f"{BASE}/test", headers=_auth(env.alice), json={
        "base_url": "https://intranet.example.com/v1", "model": "m1", "api_key": API_KEY})
    assert response.status_code == 200
    assert response.json() == {"ok": False, "latency_ms": 0, "error_class": "blocked_address"}
    assert env.app.state.model_transport.requests == []


def test_test_is_rate_limited_per_user(env):
    _save(env, env.alice)
    _save(env, env.bob)
    for _ in range(5):
        assert env.client.post(f"{BASE}/test", headers=_auth(env.alice)).status_code == 200
    limited = env.client.post(f"{BASE}/test", headers=_auth(env.alice))
    assert limited.status_code == 429 and limited.json()["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1
    assert env.client.post(f"{BASE}/test", headers=_auth(env.bob)).status_code == 200


def test_writes_disabled_without_root_key(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    user = insert_account(url, account_id=uuid.uuid4().hex, username="carol01", password_hash=VALID_HASH, role="student")
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", "demo")
    monkeypatch.setenv("EMBEDDING_MODE", "demo")
    monkeypatch.delenv("MODEL_CREDENTIAL_KEY", raising=False)
    with TestClient(create_app()) as client:
        assert client.get(BASE, headers=_auth(user)).json() == {"runtime_mode": "demo", "configured": False}
        response = client.put(BASE, headers=_auth(user), json={
            "base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY})
        assert response.status_code == 503
        assert response.json()["details"] == {"reason": "credential_store_disabled"}
