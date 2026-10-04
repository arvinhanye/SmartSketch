"""L04：迁移 015、凭据加密、用户配置与任务快照仓储（ADR-080）。"""
from __future__ import annotations

import base64
import sqlite3
import uuid
from types import SimpleNamespace

import pytest

from app.config import SettingsError, load_settings
from app.repositories import model_configs as repo
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate
from app.repositories.tasks import create_material_task
from app.services.credentials import CredentialCipher, CredentialError, SealedKey

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
ROOT_KEY = bytes(range(32))
ROOT_KEY_B64 = base64.urlsafe_b64encode(ROOT_KEY).decode()
SECRET = "sk-test-0123456789abcd"


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _user(url, name, role="teacher"):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def _task(url, course_id):
    stored = SimpleNamespace(original_filename="a.md", format="markdown", size_bytes=10,
                             content_hash="sha256:" + "0" * 64, storage_name=uuid.uuid4().hex)
    return create_material_task(url, course_id=course_id, stored_file=stored, idempotency_key=uuid.uuid4().hex).task


def test_cipher_round_trip_and_binding_to_user():
    cipher = CredentialCipher(ROOT_KEY)
    sealed = cipher.seal("user-a", SECRET)
    assert SECRET.encode() not in sealed.ciphertext
    assert cipher.open("user-a", sealed) == SECRET
    with pytest.raises(CredentialError):
        cipher.open("user-b", sealed)
    with pytest.raises(CredentialError):
        cipher.open("user-a", SealedKey(sealed.ciphertext[:-1] + b"\x00", sealed.nonce))
    assert SECRET not in repr(sealed)


def test_cipher_uses_fresh_nonce():
    cipher = CredentialCipher(ROOT_KEY)
    assert cipher.seal("u", SECRET).nonce != cipher.seal("u", SECRET).nonce


def test_settings_personal_mode_requires_valid_root_key():
    base = {"LLM_MODE": "personal"}
    with pytest.raises(SettingsError, match="MODEL_CREDENTIAL_KEY"):
        load_settings(base)
    with pytest.raises(SettingsError, match="MODEL_CREDENTIAL_KEY"):
        load_settings({**base, "MODEL_CREDENTIAL_KEY": "too-short"})
    settings = load_settings({**base, "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64})
    assert settings.LLM_MODE == "personal"
    assert CredentialCipher.from_settings(settings).open("u", CredentialCipher(ROOT_KEY).seal("u", SECRET)) == SECRET


def test_settings_private_endpoints_refused_in_production():
    env = {"APP_ENV": "production", "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
           "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": "https://e.example", "EMBEDDING_API_KEY": "k",
           "EMBEDDING_MODEL": "m", "MODEL_ENDPOINT_ALLOW_PRIVATE": "1"}
    with pytest.raises(SettingsError, match="MODEL_ENDPOINT_ALLOW_PRIVATE"):
        load_settings(env)
    env["MODEL_ENDPOINT_ALLOW_PRIVATE"] = ""
    assert load_settings(env).APP_ENV == "production"


def test_save_then_update_and_key_rules(url):
    user = _user(url, "teacher1")
    cipher = CredentialCipher(ROOT_KEY)
    with pytest.raises(repo.KeyRequired):
        repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1", sealed=None, key_hint=None)
    first = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                             sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    assert (first.version, first.key_hint, first.model) == (1, "abcd", "m1")
    kept = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m2", sealed=None, key_hint=None)
    assert (kept.version, kept.model, kept.key_hint) == (2, "m2", "abcd")
    assert cipher.open(user.id, kept.sealed) == SECRET
    with pytest.raises(repo.KeyRequired):
        repo.save_config(url, user_id=user.id, base_url="https://b.example/v1", model="m2", sealed=None, key_hint=None)
    assert repo.get_config(url, user.id).base_url == "https://a.example/v1"


def test_record_test_and_save_clears_it(url):
    user = _user(url, "teacher1")
    cipher = CredentialCipher(ROOT_KEY)
    first = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                             sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    assert repo.record_test(url, user.id, revision=first.revision, ok=False, error_class="auth")
    row = repo.get_config(url, user.id)
    assert (row.last_test_ok, row.last_test_error_class) == (False, "auth") and row.last_test_at
    saved = repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m3", sealed=None, key_hint=None)
    assert saved.last_test_at is None
    assert not repo.record_test(url, user.id, revision=first.revision, ok=True, error_class=None)   # ADR-082 决定 1
    assert repo.get_config(url, user.id).last_test_at is None


def test_binding_is_an_immutable_snapshot(url):
    user = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=user.id)
    cipher = CredentialCipher(ROOT_KEY)
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    task = _task(url, course.id)
    with connect(url) as database:
        assert repo.bind_task(database, task_id=task.id, user_id=user.id) is True
    repo.save_config(url, user_id=user.id, base_url="https://b.example/v1", model="m9",
                     sealed=cipher.seal(user.id, "sk-other-key-000000"), key_hint="0000")
    binding = repo.get_binding(url, task.id)
    assert (binding.base_url, binding.model, binding.config_version) == ("https://a.example/v1", "m1", 1)
    assert cipher.open(binding.user_id, binding.sealed) == SECRET
    assert repo.binding_active(url, task.id) is True


def test_bind_without_config_returns_false(url):
    user = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=user.id)
    task = _task(url, course.id)
    with connect(url) as database:
        assert repo.bind_task(database, task_id=task.id, user_id=user.id) is False
    assert repo.get_binding(url, task.id) is None
    assert repo.binding_active(url, task.id) is False


def test_delete_revokes_only_own_open_bindings(url):
    alice, bob = _user(url, "alice01"), _user(url, "bob0001")
    course = create_course(url, name="课", description=None, creator_id=alice.id)
    cipher = CredentialCipher(ROOT_KEY)
    for user in (alice, bob):
        repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                         sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    task_a, task_b = _task(url, course.id), _task(url, course.id)
    with connect(url) as database:
        repo.bind_task(database, task_id=task_a.id, user_id=alice.id)
        repo.bind_task(database, task_id=task_b.id, user_id=bob.id)
    assert repo.delete_config(url, alice.id) is True
    assert repo.get_config(url, alice.id) is None
    revoked = repo.get_binding(url, task_a.id)
    assert revoked.sealed is None and revoked.scrub_reason == "revoked"
    assert repo.binding_active(url, task_b.id) is True
    assert repo.delete_config(url, alice.id) is False


def test_scrub_terminal_bindings(url):
    user = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=user.id)
    cipher = CredentialCipher(ROOT_KEY)
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=cipher.seal(user.id, SECRET), key_hint="abcd")
    done, running = _task(url, course.id), _task(url, course.id)
    with connect(url) as database:
        repo.bind_task(database, task_id=done.id, user_id=user.id)
        repo.bind_task(database, task_id=running.id, user_id=user.id)
        database.execute("UPDATE processing_tasks SET stage = 'awaiting_review', progress = 1 WHERE id = ?", (done.id,))
    assert repo.scrub_terminal_bindings(url) == 1
    scrubbed = repo.get_binding(url, done.id)
    assert scrubbed.sealed is None and scrubbed.scrub_reason == "terminal"
    assert repo.binding_active(url, running.id) is True
    assert repo.scrub_terminal_bindings(url) == 0


def test_ciphertext_never_contains_plain_key(url):
    user = _user(url, "teacher1")
    repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1",
                     sealed=CredentialCipher(ROOT_KEY).seal(user.id, SECRET), key_hint="abcd")
    with connect(url) as database:
        dump = "\n".join(database.iterdump())
    assert SECRET not in dump
