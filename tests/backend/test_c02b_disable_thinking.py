"""方案 B（ADR-090）：个人模型配置的「关闭模型思考」开关。

开启时该用户全部生成调用（问答、抽取、连接测试）请求体追加且只追加 ``thinking: {"type": "disabled"}``（C02b 探测在
DeepSeek 上唯一有效的写法）；关闭时请求体与现状完全相同。开关随配置保存（省略保留已存值），任务创建时快照，
中途改开关不影响进行中的任务；改开关是一次保存，问答模型缓存随 revision 失效。
"""

from __future__ import annotations

import json
import sqlite3
import shutil
import uuid

import pytest

from app.repositories import model_configs as repo
from app.repositories.courses import create_course
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.services.ai.client import Message, ModelRequest
from app.services.ai.compatible import THINKING_DISABLED, CompatibleModelClient
from app.services.credentials import CredentialCipher
from app.services.qa.user_models import UserChatModels
from app.workers.toolkits import TaskToolkits
from test_l06 import BASE, FakeTransport, _auth, env  # noqa: F401  (env 是夹具)
from test_l07 import ROOT_KEY, _bound_task, _call, _lease, _settings, _user


class BodyTransport:
    """记录每次请求体；照常回答。"""

    def __init__(self):
        self.bodies: list[dict] = []

    def open(self, url, body, headers, timeout):
        self.bodies.append(json.loads(body))
        return FakeTransport().open(url, body, headers, timeout)


def _request() -> ModelRequest:
    return ModelRequest(purpose="answer_with_context", model="m1", messages=(Message("user", "q"),), max_output_tokens=8)


# ---------------------------------------------------------------- 兼容客户端


def test_extra_body_is_merged_and_absent_by_default():
    transport = BodyTransport()
    CompatibleModelClient("https://a.example/v1", "sk-1", transport=transport).complete(_request())
    CompatibleModelClient("https://a.example/v1", "sk-1", transport=transport,
                          extra_body=THINKING_DISABLED).complete(_request())
    plain, disabled = transport.bodies
    assert "thinking" not in plain
    assert disabled["thinking"] == {"type": "disabled"}
    assert {k: v for k, v in disabled.items() if k != "thinking"} == plain     # 只多这一个字段


def test_extra_body_cannot_override_core_fields():
    for key in ("model", "messages", "max_tokens", "stream", "stream_options", "response_format"):
        with pytest.raises(ValueError):
            CompatibleModelClient("https://a.example/v1", "sk-1", transport=BodyTransport(), extra_body={key: 1})


def test_extra_body_is_copied_at_construction():
    extra = {"thinking": {"type": "disabled"}}
    transport = BodyTransport()
    client = CompatibleModelClient("https://a.example/v1", "sk-1", transport=transport, extra_body=extra)
    extra["thinking"]["type"] = "enabled"
    client.complete(_request())
    assert transport.bodies[0]["thinking"] == {"type": "disabled"}


# ---------------------------------------------------------------- 仓储与迁移 018


@pytest.fixture
def url(tmp_path):
    value = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(value)
    return value


def _save(url, user, *, key: str | None = "sk-aaaa-1111", disable_thinking=None):
    sealed = None if key is None else CredentialCipher(ROOT_KEY).seal(user.id, key)
    return repo.save_config(url, user_id=user.id, base_url="https://a.example/v1", model="m1", sealed=sealed,
                            key_hint=None if key is None else key[-4:], disable_thinking=disable_thinking)


def test_migration_018_adds_the_flag_to_configs_and_task_bindings(url):
    with connect(url) as database:
        for table in ("user_model_configs", "task_model_bindings"):
            columns = {row[1]: row for row in database.execute(f"PRAGMA table_info({table})")}
            assert columns["disable_thinking"][3] == 1 and columns["disable_thinking"][4] == "0"


def test_flag_defaults_off_is_saved_and_omission_keeps_it(url):
    teacher = _user(url, "teacher1")
    assert _save(url, teacher).disable_thinking is False
    first = _save(url, teacher, disable_thinking=True)
    assert first.disable_thinking is True
    kept = _save(url, teacher, key=None)                    # 只改模型、不带开关：保留已存值
    assert kept.disable_thinking is True and kept.revision != first.revision
    assert _save(url, teacher, key=None, disable_thinking=False).disable_thinking is False


def test_task_binding_snapshots_the_flag(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _save(url, teacher, disable_thinking=True)
    task = _bound_task(url, course.id, teacher)
    _save(url, teacher, key=None, disable_thinking=False)   # 任务创建后改开关
    assert repo.get_binding(url, task.id).disable_thinking is True


# ---------------------------------------------------------------- 抽取与问答都按开关发请求


def test_extraction_uses_the_task_snapshot_flag(url):
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    _save(url, teacher, disable_thinking=True)
    on = _bound_task(url, course.id, teacher)
    _save(url, teacher, key=None, disable_thinking=False)
    off = _bound_task(url, course.id, teacher)
    transport = BodyTransport()
    toolkits = TaskToolkits(_settings(url), transport=transport)
    _call(toolkits.for_lease(_lease(on)), _lease(on))
    _call(toolkits.for_lease(_lease(off)), _lease(off))
    assert transport.bodies[0]["thinking"] == {"type": "disabled"} and "thinking" not in transport.bodies[1]


def test_chat_models_follow_the_flag_and_cache_refreshes_on_change(url):
    student = _user(url, "student1", role="student")
    _save(url, student, disable_thinking=True)
    transport = BodyTransport()
    models = UserChatModels(_settings(url), transport=transport)

    def ask():
        _, generator = models.for_user(student.id)
        from app.services.ai.policy import CallAttribution
        client = generator._policy.bind(CallAttribution(course_id="c1", request_id=uuid.uuid4().hex, user_id=student.id))
        client.complete(_request())

    ask()
    _save(url, student, key=None, disable_thinking=False)
    ask()
    assert transport.bodies[0]["thinking"] == {"type": "disabled"} and "thinking" not in transport.bodies[1]


# ---------------------------------------------------------------- 接口与连接测试


def test_api_reports_saves_and_keeps_the_flag(env):  # noqa: F811
    body = {"base_url": "https://api.example.com/v1", "model": "m1", "api_key": "sk-live-AAAABBBBCCCC1234"}
    assert env.client.put(BASE, json={**body, "disable_thinking": True}, headers=_auth(env.alice)).json()["disable_thinking"] is True
    kept = env.client.put(BASE, json={"base_url": body["base_url"], "model": "m2"}, headers=_auth(env.alice)).json()
    assert kept["disable_thinking"] is True
    assert env.client.get(BASE, headers=_auth(env.alice)).json()["disable_thinking"] is True


def test_connection_test_sends_the_same_request_shape(env):  # noqa: F811
    transport = env.app.state.model_transport
    body = {"base_url": "https://api.example.com/v1", "model": "m1", "api_key": "sk-live-AAAABBBBCCCC1234"}
    env.client.post(f"{BASE}/test", json={**body, "disable_thinking": True}, headers=_auth(env.alice))
    env.client.post(f"{BASE}/test", json=body, headers=_auth(env.alice))
    env.client.put(BASE, json={**body, "disable_thinking": True}, headers=_auth(env.alice))
    env.client.post(f"{BASE}/test", headers=_auth(env.alice))                  # 测已存配置：用已存值
    sent = [request[1] for request in transport.requests]
    assert sent[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in sent[1]
    assert sent[2]["thinking"] == {"type": "disabled"}


def test_upgrade_from_017_preserves_existing_config_and_task(tmp_path):
    """018 must upgrade an existing encrypted config/task, not merely create an empty DB."""
    older = tmp_path / "migrations-through-017"
    older.mkdir()
    for path in MIGRATIONS_DIR.glob("*.sql"):
        if path.name[:3] <= "017":
            shutil.copyfile(path, older / path.name)
    url = f"sqlite:///{tmp_path / 'upgrade.sqlite3'}"
    migrate(url, older)
    teacher = _user(url, "teacher1")
    course = create_course(url, name="课", description=None, creator_id=teacher.id)
    sealed = CredentialCipher(ROOT_KEY).seal(teacher.id, "sk-legacy-1111")
    with connect(url) as db:
        db.execute("INSERT INTO user_model_configs (user_id,base_url,model,key_ciphertext,key_nonce,key_hint,version,revision)"
                   " VALUES (?,?,?,?,?,?,?,?)", (teacher.id,"https://a.example/v1","m1",sealed.ciphertext,sealed.nonce,"1111",3,"legacy-revision"))
    # Construct the pre-018 task with the old binding SQL; new repository readers require 018.
    from test_l07 import _stored
    from app.repositories.tasks import create_material_task
    task = create_material_task(url, course_id=course.id, stored_file=_stored(),
                                idempotency_key=uuid.uuid4().hex, created_by=teacher.id, bind_model_config=False).task
    with connect(url) as db:
        db.execute("INSERT INTO task_model_bindings (task_id,user_id,config_version,base_url,model,key_ciphertext,key_nonce)"
                   " VALUES (?,?,?,?,?,?,?)", (task.id,teacher.id,3,"https://a.example/v1","m1",sealed.ciphertext,sealed.nonce))
    assert migrate(url) == ["018"]
    assert migrate(url) == []
    config = repo.get_config(url, teacher.id)
    binding = repo.get_binding(url, task.id)
    assert config.disable_thinking is False and binding.disable_thinking is False
    assert config.revision == "legacy-revision" and config.version == binding.config_version == 3
    cipher = CredentialCipher(ROOT_KEY)
    assert cipher.open(teacher.id, config.sealed) == cipher.open(teacher.id, binding.sealed) == "sk-legacy-1111"
    for table in ("user_model_configs", "task_model_bindings"):
        with connect(url) as db, pytest.raises(sqlite3.IntegrityError):
            db.execute(f"UPDATE {table} SET disable_thinking=2")
    assert list((tmp_path / "backups").glob("*-before-018.sqlite"))


def test_stream_preserves_thinking_switch_and_output_guardrails():
    from test_e03 import ScriptedResponse, ScriptedTransport, SSE_HEADERS, sse
    response = {"model":"m1", "choices":[{"index":0,"delta":{"content":"答[1]。"},"finish_reason":"stop"}],
                "usage":{"prompt_tokens":3,"completion_tokens":4}}
    transport = ScriptedTransport(ScriptedResponse(200, sse(response, "[DONE]"), headers=SSE_HEADERS))
    client = CompatibleModelClient("https://a.example/v1", "sk-1", transport=transport, extra_body=THINKING_DISABLED)
    events = list(client.stream(_request()))
    body = json.loads(transport.calls[0]["body"])
    assert body["thinking"] == {"type":"disabled"}
    assert body["stream"] is True and body["stream_options"] == {"include_usage":True}
    assert body["max_tokens"] == 8
    assert events[-1].result.text == "答[1]。"
