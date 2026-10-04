"""L07：上传绑定任务快照、worker 按任务取模型、改/清配置与重启接管的语义（ADR-080 决定 3）。"""
from __future__ import annotations

import base64
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate
from app.repositories.task_leases import Lease
from app.repositories.tasks import ModelConfigMissing, create_material_task
from app.services.ai.client import Message, ModelRequest
from app.services.ai.policy import CallAttribution
from app.services.auth import issue_access_token
from app.services.credentials import CredentialCipher, CredentialUnavailable
from app.workers.runner import BindingScrub, build_toolkit
from app.workers.toolkits import TaskToolkits

SECRET = "l07-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()


class RecordingTransport:
    """Answers every chat request and records (url, bearer, model)."""

    def __init__(self):
        self.calls = []

    def open(self, url, body, headers, timeout):
        self.calls.append((url, headers["Authorization"], json.loads(body)["model"]))
        payload = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        return SimpleNamespace(status=200, header=lambda name: None, close=lambda: None,
                               read=_reader(payload))


def _reader(payload):
    state = {"data": payload}

    def read(amount, timeout):
        chunk, state["data"] = state["data"][:amount], state["data"][amount:]
        return chunk

    return read


def _settings(url, **extra):
    return load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64, **extra})


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _user(url, name, role="teacher"):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def _configure(url, user, *, base_url, model, key):
    return repo.save_config(url, user_id=user.id, base_url=base_url, model=model,
                            sealed=CredentialCipher(ROOT_KEY).seal(user.id, key), key_hint=key[-4:])


def _stored():
    return SimpleNamespace(original_filename="a.md", format="markdown", size_bytes=10,
                           content_hash="sha256:" + "0" * 64, storage_name=uuid.uuid4().hex)


def _bound_task(url, course_id, user):
    return create_material_task(url, course_id=course_id, stored_file=_stored(), idempotency_key=uuid.uuid4().hex,
                                created_by=user.id, bind_model_config=True).task


def _lease(task):
    return Lease(task_id=task.id, course_id=task.course_id, document_id=task.document_id, stage="extracting",
                 progress=0.0, attempt=1, owner="w", token="t" * 32, expires_at=int(time.time()) + 60)


def _call(toolkit, lease):
    if toolkit.guard is not None:
        toolkit.guard()
    client = toolkit.policy.bind(CallAttribution(course_id=lease.course_id, task_id=lease.task_id,
                                                 user_id=toolkit.user_id))
    return client.complete(ModelRequest(purpose="extract_entities", model=toolkit.model,
                                        messages=(Message("user", "x"),), max_output_tokens=8))


def test_create_task_records_creator_and_snapshot(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    with connect(url) as database:
        assert database.execute("SELECT created_by FROM processing_tasks WHERE id = ?", (task.id,)).fetchone() == (teacher.id,)
    assert repo.get_binding(url, task.id).model == "m1"


def test_create_task_without_config_writes_nothing(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    with pytest.raises(ModelConfigMissing):
        create_material_task(url, course_id=course.id, stored_file=_stored(), idempotency_key="k1",
                             created_by=teacher.id, bind_model_config=True)
    with connect(url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (0,)


def test_two_teachers_use_their_own_key_and_model(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    course = create_course(url, name="课", description=None, creator_id=alice.id)
    _configure(url, alice, base_url="https://a.example/v1", model="model-a", key="sk-alice-0001")
    _configure(url, bob, base_url="https://b.example/v1", model="model-b", key="sk-bob-0002")
    task_a, task_b = _bound_task(url, course.id, alice), _bound_task(url, course.id, bob)
    transport = RecordingTransport()
    toolkits = TaskToolkits(_settings(url), transport=transport)
    _call(toolkits.for_lease(_lease(task_a)), _lease(task_a))
    _call(toolkits.for_lease(_lease(task_b)), _lease(task_b))
    assert transport.calls == [
        ("https://a.example/v1/chat/completions", "Bearer sk-alice-0001", "model-a"),
        ("https://b.example/v1/chat/completions", "Bearer sk-bob-0002", "model-b"),
    ]
    with connect(url) as database:
        rows = database.execute("SELECT task_id, user_id FROM model_calls ORDER BY rowid").fetchall()
    assert rows == [(task_a.id, alice.id), (task_b.id, bob.id)]


def test_changing_config_does_not_change_a_queued_task(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="old-model", key="sk-old-0001")
    task = _bound_task(url, course.id, teacher)
    _configure(url, teacher, base_url="https://b.example/v1", model="new-model", key="sk-new-0002")
    transport = RecordingTransport()
    _call(TaskToolkits(_settings(url), transport=transport).for_lease(_lease(task)), _lease(task))
    assert transport.calls == [("https://a.example/v1/chat/completions", "Bearer sk-old-0001", "old-model")]


def test_restart_resolves_the_same_snapshot(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    first, second = RecordingTransport(), RecordingTransport()
    _call(TaskToolkits(_settings(url), transport=first).for_lease(_lease(task)), _lease(task))
    _call(TaskToolkits(_settings(url), transport=second).for_lease(_lease(task)), _lease(task))
    assert first.calls == second.calls


def test_clearing_config_revokes_before_and_during_a_task(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    running, queued = _bound_task(url, course.id, teacher), _bound_task(url, course.id, teacher)
    transport = RecordingTransport()
    toolkits = TaskToolkits(_settings(url), transport=transport)
    toolkit = toolkits.for_lease(_lease(running))
    _call(toolkit, _lease(running))
    repo.delete_config(url, teacher.id)
    with pytest.raises(CredentialUnavailable) as caught:
        toolkit.guard()
    assert caught.value.reason == "credential_revoked"
    with pytest.raises(CredentialUnavailable) as caught:
        toolkits.for_lease(_lease(queued))
    assert caught.value.reason == "credential_revoked"
    assert len(transport.calls) == 1


def test_task_without_snapshot_is_refused(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    task = create_material_task(url, course_id=course.id, stored_file=_stored(), idempotency_key="k").task
    with pytest.raises(CredentialUnavailable) as caught:
        TaskToolkits(_settings(url), transport=RecordingTransport()).for_lease(_lease(task))
    assert caught.value.reason == "credential_missing"


def test_snapshot_sealed_under_another_root_key_is_unreadable(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    other = base64.urlsafe_b64encode(bytes(range(1, 33))).decode()
    settings = load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": other})
    with pytest.raises(CredentialUnavailable) as caught:
        TaskToolkits(settings, transport=RecordingTransport()).for_lease(_lease(task))
    assert caught.value.reason == "credential_unreadable"


def test_binding_scrub_hook(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
    task = _bound_task(url, course.id, teacher)
    with connect(url) as database:
        database.execute("UPDATE processing_tasks SET stage = 'awaiting_review', progress = 1 WHERE id = ?", (task.id,))
    BindingScrub(url)()
    assert repo.get_binding(url, task.id).scrub_reason == "terminal"


def test_build_toolkit_by_mode(url):
    assert callable(build_toolkit(_settings(url))) and not hasattr(build_toolkit(_settings(url)), "policy")
    demo = load_settings({"SQLITE_URL": url, "LLM_MODE": "demo", "EMBEDDING_MODE": "demo"})
    assert hasattr(build_toolkit(demo), "policy")


def _api(tmp_path, monkeypatch, url):
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("LLM_MODE", "personal")
    monkeypatch.setenv("MODEL_CREDENTIAL_KEY", ROOT_KEY_B64)
    return TestClient(create_app())


def _auth(user):
    token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                               issued_at=int(time.time()), ttl_seconds=3600)
    return {"Authorization": f"Bearer {token}"}


def test_upload_requires_config_then_binds(tmp_path, monkeypatch, url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    files = {"file": ("ch1.md", b"# \xe7\xac\xac\xe4\xb8\x80\xe7\xab\xa0\n\n\xe6\xa0\x88\xe6\x98\xaf\xe4\xb8\x80\xe7\xa7\x8d\xe7\xba\xbf\xe6\x80\xa7\xe8\xa1\xa8\xe3\x80\x82\n", "text/markdown")}
    with _api(tmp_path, monkeypatch, url) as client:
        refused = client.post(f"/api/v1/courses/{course.id}/documents", files=files, headers=_auth(teacher))
        assert refused.status_code == 409 and refused.json()["code"] == "MODEL_CONFIG_REQUIRED"
        with connect(url) as database:
            assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert not any((tmp_path / "storage").rglob("*.md"))
        _configure(url, teacher, base_url="https://a.example/v1", model="m1", key="sk-aaaa-1111")
        accepted = client.post(f"/api/v1/courses/{course.id}/documents", files=files, headers=_auth(teacher))
        assert accepted.status_code == 202, accepted.text
        assert repo.binding_active(url, accepted.json()["task_id"]) is True
