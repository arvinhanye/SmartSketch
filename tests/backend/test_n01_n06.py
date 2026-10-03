"""N01 / N06：配置身份 ``revision`` 在清除重建后不重复；问答缓存与测试结果落库都按它校验（ADR-082 决定 1）。"""
from __future__ import annotations

import base64
import json
import shutil
import threading
import uuid
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.repositories.tasks import create_material_task
from app.services import model_configs as service
from app.services.ai.client import Message, ModelRequest
from app.services.ai.policy import CallAttribution
from app.services.credentials import CredentialCipher
from app.services.qa.user_models import UserChatModels

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()
PUBLIC = lambda host, port: ["1.1.1.1"]  # noqa: E731


def _reply(status=200):
    payload = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
    state = {"data": payload if status == 200 else b'{"error":{"message":"no"}}'}

    def read(amount, timeout):
        chunk, state["data"] = state["data"][:amount], state["data"][amount:]
        return chunk

    return SimpleNamespace(status=status, header=lambda name: None, read=read, close=lambda: None)


class Transport:
    """Records (url, key, model); keys in ``bad`` get 401."""

    def __init__(self, bad=()):
        self.bad, self.calls = set(bad), []

    def open(self, url, body, headers, timeout):
        key = headers["Authorization"].removeprefix("Bearer ")
        self.calls.append((url, key, json.loads(body)["model"]))
        return _reply(401 if key in self.bad else 200)


class GatedTransport(Transport):
    """Each call blocks until its own gate opens, so tests can finish requests out of order."""

    def __init__(self, bad=()):
        super().__init__(bad)
        self.started: list[threading.Event] = []
        self.gates: list[threading.Event] = []
        self._mutex = threading.Lock()

    def prepare(self, count):
        self.started = [threading.Event() for _ in range(count)]
        self.gates = [threading.Event() for _ in range(count)]

    def open(self, url, body, headers, timeout):
        with self._mutex:
            index = len(self.calls)
        reply = super().open(url, body, headers, timeout)
        self.started[index].set()
        assert self.gates[index].wait(5)
        return reply


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _settings(url, **extra):
    return load_settings({"SQLITE_URL": url, "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                          "LLM_MAX_RETRIES": "0", **extra})


def _user(url, name, role="student"):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def _configure(url, user, *, base_url="https://a.example/v1", model, key):
    return repo.save_config(url, user_id=user.id, base_url=base_url, model=model,
                            sealed=CredentialCipher(ROOT_KEY).seal(user.id, key), key_hint=key[-4:])


def _ask(models, user):
    _, generator = models.for_user(user.id)
    client = generator._policy.bind(CallAttribution(course_id="c1", request_id=uuid.uuid4().hex, user_id=user.id))
    return client.complete(ModelRequest(purpose="answer_with_context", model=generator._model,
                                        messages=(Message("user", "q"),), max_output_tokens=8))


# ---- N01：问答缓存 ----------------------------------------------------------------------------

def test_clear_then_resave_without_asking_in_between_uses_new_config(url):
    alice = _user(url, "alice01")
    _configure(url, alice, base_url="https://a.example/v1", model="model-a", key="sk-alice-AAAA")
    transport = Transport()
    models = UserChatModels(_settings(url), transport=transport)
    _ask(models, alice)                                   # 缓存 A
    repo.delete_config(url, alice.id)                     # 清除与重建之间不发起提问
    _configure(url, alice, base_url="https://b.example/v1", model="model-b", key="sk-alice-BBBB")
    _ask(models, alice)
    assert transport.calls[-1] == ("https://b.example/v1/chat/completions", "sk-alice-BBBB", "model-b")


def test_resave_identical_values_after_clear_still_rebuilds(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="m", key="sk-alice-AAAA")
    models = UserChatModels(_settings(url), transport=Transport())
    first = models.for_user(alice.id)[1]
    repo.delete_config(url, alice.id)
    _configure(url, alice, model="m", key="sk-alice-AAAA")
    assert models.for_user(alice.id)[1] is not first      # 新身份 → 新策略（熔断等状态不继承）


def test_revision_never_repeats_across_saves_and_rebuilds(url):
    alice = _user(url, "alice01")
    seen = set()
    for round_ in range(3):
        seen.add(_configure(url, alice, model=f"m{round_}", key="sk-alice-AAAA").revision)
        seen.add(repo.save_config(url, user_id=alice.id, base_url="https://a.example/v1", model=f"n{round_}",
                                  sealed=None, key_hint=None).revision)
        repo.delete_config(url, alice.id)
    assert len(seen) == 6 and all(seen)


def test_one_users_rebuild_does_not_touch_another(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    _configure(url, alice, model="model-a", key="sk-alice-AAAA")
    _configure(url, bob, base_url="https://b.example/v1", model="model-b", key="sk-bob-BBBB")
    transport = Transport()
    models = UserChatModels(_settings(url), transport=transport)
    _ask(models, alice)
    bob_generator = models.for_user(bob.id)[1]
    repo.delete_config(url, alice.id)
    _configure(url, alice, base_url="https://c.example/v1", model="model-c", key="sk-alice-CCCC")
    _ask(models, alice)
    _ask(models, bob)
    assert transport.calls[-2:] == [
        ("https://c.example/v1/chat/completions", "sk-alice-CCCC", "model-c"),
        ("https://b.example/v1/chat/completions", "sk-bob-BBBB", "model-b"),
    ]
    assert models.for_user(bob.id)[1] is bob_generator


def test_task_snapshot_is_unchanged_by_resave_and_still_revoked_by_clear(url):
    teacher = _user(url, "teach01", role="teacher")
    course = create_course(url, name="C", description=None, creator_id=teacher.id)
    _configure(url, teacher, base_url="https://a.example/v1", model="model-a", key="sk-teach-AAAA")
    stored = SimpleNamespace(original_filename="a.md", format="markdown", size_bytes=10,
                             content_hash="sha256:" + "0" * 64, storage_name=uuid.uuid4().hex)
    task = create_material_task(url, course_id=course.id, stored_file=stored, idempotency_key=uuid.uuid4().hex,
                                created_by=teacher.id, bind_model_config=True).task
    _configure(url, teacher, base_url="https://b.example/v1", model="model-b", key="sk-teach-BBBB")
    binding = repo.get_binding(url, task.id)
    assert (binding.base_url, binding.model) == ("https://a.example/v1", "model-a")
    assert CredentialCipher(ROOT_KEY).open(teacher.id, binding.sealed) == "sk-teach-AAAA"
    repo.delete_config(url, teacher.id)
    assert repo.get_binding(url, task.id).scrub_reason == "revoked"


# ---- N06：测试结果只落到被测的配置 ------------------------------------------------------------------

def _start_saved_test(url, user, transport, results):
    def run():
        results.append(service.run_test(_settings(url), user.id, base_url=None, model=None, api_key=None,
                                        transport=transport, resolver=PUBLIC))
    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_old_test_success_is_not_recorded_on_config_saved_meanwhile(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="model-a", key="sk-alice-AAAA")
    transport = GatedTransport()
    transport.prepare(1)
    results = []
    thread = _start_saved_test(url, alice, transport, results)
    assert transport.started[0].wait(5)
    _configure(url, alice, base_url="https://b.example/v1", model="never-tested", key="sk-alice-BBBB")
    transport.gates[0].set()
    thread.join(5)
    assert results[0].ok is True                          # 测试本身照实返回给调用方
    row = repo.get_config(url, alice.id)
    assert row.model == "never-tested"
    assert (row.last_test_at, row.last_test_ok) == (None, None)


def test_old_test_is_not_recorded_after_clear_and_identical_rebuild(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="m", key="sk-alice-AAAA")
    transport = GatedTransport()
    transport.prepare(1)
    results = []
    thread = _start_saved_test(url, alice, transport, results)
    assert transport.started[0].wait(5)
    repo.delete_config(url, alice.id)
    _configure(url, alice, model="m", key="sk-alice-AAAA")   # 值完全相同、version 又是 1
    transport.gates[0].set()
    thread.join(5)
    row = repo.get_config(url, alice.id)
    assert row.version == 1 and row.last_test_at is None


def test_out_of_order_tests_keep_the_result_of_the_current_config(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="model-a", key="sk-alice-AAAA")
    transport = GatedTransport(bad={"sk-alice-BBBB"})
    transport.prepare(2)
    results = []
    first = _start_saved_test(url, alice, transport, results)          # 测 A（将成功）
    assert transport.started[0].wait(5)
    _configure(url, alice, base_url="https://b.example/v1", model="model-b", key="sk-alice-BBBB")
    second = _start_saved_test(url, alice, transport, results)         # 测 B（401）
    assert transport.started[1].wait(5)
    transport.gates[1].set()
    second.join(5)
    transport.gates[0].set()                                           # A 的成功最后才到
    first.join(5)
    row = repo.get_config(url, alice.id)
    assert (row.model, row.last_test_ok, row.last_test_error_class) == ("model-b", False, "auth")


def test_current_config_test_is_still_recorded(url):
    alice = _user(url, "alice01")
    _configure(url, alice, model="model-a", key="sk-alice-AAAA")
    service.run_test(_settings(url), alice.id, base_url=None, model=None, api_key=None,
                     transport=Transport(), resolver=PUBLIC)
    row = repo.get_config(url, alice.id)
    assert row.last_test_ok is True and row.last_test_at is not None


# ---- 迁移 016：已有配置回填身份 ----------------------------------------------------------------

def test_migration_backfills_distinct_revisions_for_existing_rows(tmp_path):
    before = tmp_path / "before-016"
    before.mkdir()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name < "016":
            shutil.copy(path, before / path.name)
    url = f"sqlite:///{(tmp_path / 'old.sqlite3').as_posix()}"
    migrate(url, before)
    users = [_user(url, f"user{i:04d}") for i in range(2)]
    with connect(url) as database:
        for user in users:
            database.execute(
                "INSERT INTO user_model_configs (user_id, base_url, model, key_ciphertext, key_nonce, key_hint, version)"
                " VALUES (?, 'https://a.example/v1', 'm', x'00', zeroblob(12), 'AAAA', 1)", (user.id,))
    migrate(url)
    revisions = [repo.get_config(url, user.id).revision for user in users]
    assert all(revisions) and len(set(revisions)) == 2
