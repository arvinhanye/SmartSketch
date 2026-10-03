"""N07：凭据存储未启用时 /test 的任何分支都在解析与出站前返回 503；N08：空白模型名 422，不写库、不出站。"""
from __future__ import annotations

import base64
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.credentials import CredentialCipher

SECRET = "n07-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()
API_KEY = "sk-live-AAAABBBBCCCC1234"
BASE = "/api/v1/me/model-config"


class CountingTransport:
    def __init__(self):
        self.requests = []

    def open(self, url, body, headers, timeout):
        self.requests.append(url)
        payload = json.dumps({"model": "m", "choices": [{"message": {"content": "o"}, "finish_reason": "length"}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        state = {"data": payload}

        def read(amount, timeout):
            chunk, state["data"] = state["data"][:amount], state["data"][amount:]
            return chunk

        return type("R", (), {"status": 200, "header": lambda self, name: None, "read": lambda self, a, t: read(a, t),
                              "close": lambda self: None})()


def _client(tmp_path, monkeypatch, *, mode, root_key):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    user = insert_account(url, account_id=uuid.uuid4().hex, username="carol01", password_hash=VALID_HASH, role="student")
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", mode)
    monkeypatch.setenv("EMBEDDING_MODE", "demo" if mode == "demo" else "fake")
    if root_key:
        monkeypatch.setenv("MODEL_CREDENTIAL_KEY", ROOT_KEY_B64)
    else:
        monkeypatch.delenv("MODEL_CREDENTIAL_KEY", raising=False)
    resolved = []

    def resolver(host, port):
        resolved.append(host)
        return ["1.1.1.1"]

    monkeypatch.setattr("app.services.model_configs.system_resolver", resolver)
    app = create_app()
    transport = CountingTransport()
    app.state.model_transport = transport
    token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                               issued_at=int(time.time()), ttl_seconds=3600)
    return app, url, user, {"Authorization": f"Bearer {token}"}, transport, resolved


# ---- N07 -----------------------------------------------------------------------------------------

FULL = {"base_url": "https://api.example.com/v1", "model": "m1", "api_key": API_KEY}


@pytest.mark.parametrize("mode", ["demo", "fake"])
@pytest.mark.parametrize("body", [FULL, None], ids=["full-body", "empty-body"])
def test_test_endpoint_is_disabled_without_root_key_before_any_network(tmp_path, monkeypatch, mode, body):
    app, _, _, auth, transport, resolved = _client(tmp_path, monkeypatch, mode=mode, root_key=False)
    with TestClient(app) as client:
        response = (client.post(f"{BASE}/test", headers=auth, json=body) if body is not None
                    else client.post(f"{BASE}/test", headers=auth))
    assert response.status_code == 503
    assert response.json()["details"] == {"reason": "credential_store_disabled"}
    assert transport.requests == [] and resolved == []


def test_disabled_store_wins_even_with_a_leftover_saved_config(tmp_path, monkeypatch):
    app, url, user, auth, transport, resolved = _client(tmp_path, monkeypatch, mode="demo", root_key=False)
    repo.save_config(url, user_id=user.id, base_url="https://api.example.com/v1", model="m1",
                     sealed=CredentialCipher(ROOT_KEY).seal(user.id, API_KEY), key_hint="1234")
    with TestClient(app) as client:
        for body in (FULL, None):
            response = client.post(f"{BASE}/test", headers=auth, **({"json": body} if body else {}))
            assert response.status_code == 503
    assert transport.requests == [] and resolved == []


def test_enabled_store_still_tests_a_full_body(tmp_path, monkeypatch):
    app, _, _, auth, transport, _ = _client(tmp_path, monkeypatch, mode="personal", root_key=True)
    with TestClient(app) as client:
        response = client.post(f"{BASE}/test", headers=auth, json=FULL)
    assert response.status_code == 200 and response.json()["ok"] is True
    assert len(transport.requests) == 1


# ---- N08 -----------------------------------------------------------------------------------------

BLANKS = [" ", "   ", "\t", "\n", " \t\n "]


def _assert_blank_model_rejected(response):
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["fields"] == [{"in": "body", "field": "model", "reason": "blank"}]


@pytest.mark.parametrize("model", BLANKS, ids=repr)
def test_blank_model_save_is_422_and_writes_nothing(tmp_path, monkeypatch, model):
    app, url, user, auth, transport, resolved = _client(tmp_path, monkeypatch, mode="personal", root_key=True)
    with TestClient(app) as client:
        _assert_blank_model_rejected(client.put(BASE, headers=auth, json={**FULL, "model": model}))
    assert repo.get_config(url, user.id) is None
    assert transport.requests == [] and resolved == []


@pytest.mark.parametrize("model", BLANKS, ids=repr)
def test_blank_model_on_keep_key_save_is_422_and_keeps_the_old_config(tmp_path, monkeypatch, model):
    app, url, user, auth, _, _ = _client(tmp_path, monkeypatch, mode="personal", root_key=True)
    with TestClient(app) as client:
        assert client.put(BASE, headers=auth, json=FULL).status_code == 200
        _assert_blank_model_rejected(client.put(BASE, headers=auth, json={"base_url": FULL["base_url"], "model": model}))
    row = repo.get_config(url, user.id)
    assert (row.model, row.version) == ("m1", 1)


@pytest.mark.parametrize("model", BLANKS, ids=repr)
def test_blank_model_test_is_422_without_any_request(tmp_path, monkeypatch, model):
    app, url, _, auth, transport, resolved = _client(tmp_path, monkeypatch, mode="personal", root_key=True)
    with TestClient(app) as client:
        _assert_blank_model_rejected(client.post(f"{BASE}/test", headers=auth, json={**FULL, "model": model}))
    assert transport.requests == [] and resolved == []
    with connect(url) as database:
        assert database.execute("SELECT count(*) FROM model_calls").fetchone() == (0,)


def test_model_name_is_stored_trimmed(tmp_path, monkeypatch):
    app, url, user, auth, _, _ = _client(tmp_path, monkeypatch, mode="personal", root_key=True)
    with TestClient(app) as client:
        assert client.put(BASE, headers=auth, json={**FULL, "model": "  deepseek-flash \t"}).json()["model"] == "deepseek-flash"
    assert repo.get_config(url, user.id).model == "deepseek-flash"
