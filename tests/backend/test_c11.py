"""C11：任务查询与 GET SSE（specs/task-processing.md §7；specs/identity-access.md §4、§5）。

- ``GET /api/v1/tasks/{tid}``：C03 访问矩阵（非成员与不存在同形 404、不含快照），``failed`` 仍 200；
  响应体按契约 JSON Schema ``Task`` 与生成的 ``Task`` 模型双重校验。
- ``GET /api/v1/tasks/{tid}/events``：只认 C16 一次性票据（核销即作废、过期拒绝、须匹配该任务），
  核销后按 §5.2 重新授权，全部通过才开流。
- 事件来源是轮询 SQLite 任务行（API 与 worker 不同进程）：建连先补快照；进入新阶段、阶段内进度上升、
  ``cancel_requested`` 由 false 变 true 推 ``stage``；``awaiting_review`` 与终态推送后关流，每个连接恰好
  一条结束事件；``:ping`` 心跳；多订阅者各自先收快照；客户端断开释放监听器。
- 每一帧都按契约 ``TaskEvent``（JSON Schema + 生成模型）校验。

SSE 请求一律不用 TestClient（它会等整个响应结束才返回，永不关流的缺陷会让测试挂死），而用下面的
最小 ASGI 驱动逐帧读取（每步带超时），并能在任意时刻模拟客户端断开；轮询与心跳间隔由测试注入，
worker 写入在另一线程执行。
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from urllib.parse import urlencode

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from app.main import create_app
from app.repositories import event_tickets
from app.repositories.accounts import insert_account, set_disabled
from app.repositories.courses import add_member, create_course, remove_member
from app.repositories.sqlite import connect, migrate
from app.services import task_events
from app.services.auth import issue_access_token
from app.services.task_cancel import TaskSnapshot, cancel_task
from app.services.task_events import (
    DEFAULT_HEARTBEAT_SECONDS,
    EventDiffer,
    TaskEventStreams,
    snapshot_event,
    task_body,
)
from app.services.task_state import TaskError

ROOT = Path(__file__).resolve().parents[2]
SECRET = "c11-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
T0 = 1_900_000_000
SNAPSHOT_KEYS = {"id", "course_id", "document_id", "stage", "progress", "cancel_requested", "error"}
EVENT_SCHEMAS = {
    "stage": "TaskStageEvent",
    "done": "TaskDoneEvent",
    "error": "TaskErrorEvent",
    "cancelled": "TaskCancelledEvent",
}
END_EVENTS = {"done", "error", "cancelled"}
FAST = {"poll_seconds": 0.005, "heartbeat_seconds": 3600.0}
PROCESSING = ("queued", "parsing", "extracting", "merging", "persisting", "awaiting_review")


# --- 契约校验（与 tests/contracts/test_b10.py、test_c10.py 同法）--------------------------------

_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {
            key: (value.replace("#/components/schemas/", "#/$defs/")
                  if key == "$ref" and isinstance(value, str) else _rewrite(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def _schema_valid(name: str, instance) -> bool:
    schema = {"$defs": _DEFS, "$ref": f"#/$defs/{name}"}
    return jsonschema.Draft202012Validator(schema).is_valid(instance)


def _generated():
    path = ROOT / "src/contracts/v1/generated/python/models.py"
    spec = importlib.util.spec_from_file_location("c11_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATED = _generated()


def parse_frame(frame: str) -> tuple[str, dict | None]:
    """One SSE frame → (event, data). Validates wire shape and the contract ``TaskEvent``."""
    assert frame.endswith("\n\n"), frame
    if frame == ":ping\n\n":
        return "ping", None
    lines = frame[:-2].split("\n")
    assert len(lines) == 2, frame  # 恰好 event 行 + 单行 data
    assert lines[0].startswith("event: ") and lines[1].startswith("data: "), frame
    event, raw = lines[0][len("event: "):], lines[1][len("data: "):]
    data = json.loads(raw)
    assert json.dumps(data, ensure_ascii=False, separators=(",", ":")) == raw  # 单行紧凑 JSON
    assert event in EVENT_SCHEMAS, event
    assert _schema_valid("TaskEvent", data), data
    assert _schema_valid(EVENT_SCHEMAS[event], data), data
    parsed = GENERATED.TaskEvent.model_validate(data).root
    assert type(parsed).__name__ == EVENT_SCHEMAS[event]
    return event, data


# --- 数据准备 ------------------------------------------------------------------------------------


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _row(url: str, task_id: str) -> dict[str, object]:
    with connect(url) as database:
        database.row_factory = sqlite3.Row
        row = database.execute("SELECT * FROM processing_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)


def _insert_task(url: str, course_id: str, task_id: str) -> str:
    with connect(url) as db:
        db.execute(
            "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash,"
            " storage_name) VALUES (?, ?, 'a.txt', 'txt', 1, ?, ?)",
            (f"doc-{task_id}", course_id, "sha256:" + "a" * 64, f"stored-{task_id}"),
        )
        db.execute(
            "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, course_id, f"doc-{task_id}", f"key-{task_id}",
             "2026-09-25T00:00:00.000Z", "2026-09-25T00:00:00.000Z"),
        )
    return task_id


def set_task(url: str, task_id: str, stage: str, progress: float, *, cancel: int = 0,
             error: tuple[str, str, str | None] | None = None) -> None:
    """Worker-side write on its own connection (stands in for the worker process)."""
    if stage == "failed":
        code, message, details = error or ("INTERNAL_ERROR", "内部错误", None)
        statement = (
            "UPDATE processing_tasks SET stage = 'failed', progress = ?, cancel_requested = ?,"
            " error_code = ?, error_message = ?, error_details = ?,"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?"
        )
        params = (progress, cancel, code, message, details, task_id)
    else:
        statement = (
            "UPDATE processing_tasks SET stage = ?, progress = ?, cancel_requested = ?,"
            " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?"
        )
        params = (stage, progress, cancel, task_id)
    with connect(url) as database:
        database.execute(statement, params)


def _snap(stage: str, progress: float, cancel: bool = False, error: TaskError | None = None,
          task_id: str = "t1") -> TaskSnapshot:
    return TaskSnapshot(
        id=task_id, course_id="c1", document_id="d1", stage=stage, progress=progress,
        cancel_requested=cancel, created_at="2026-09-25T00:00:00.000Z",
        updated_at="2026-09-25T00:00:00.000Z", error=error,
    )


def _failed_error() -> TaskError:
    return TaskError(
        code="EXTRACTION_INCOMPLETE", message="抽取失败的块超过阈值",
        details={"chunks_failed": 3, "chunks_total": 10, "threshold": 0.2},
    )


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def env(tmp_path, monkeypatch):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)

    def account(name: str, role: str):
        return insert_account(
            url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role
        )

    teacher = account("teacher1", "teacher")
    student = account("student1", "student")
    outsider = account("teacher2", "teacher")
    cohost = account("teacher3", "teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    other = create_course(url, name="B", description=None, creator_id=outsider.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    add_member(url, course_id=course.id, user_id=cohost.id, role="teacher", added_by=teacher.id)
    for tid in ("t1", "t2", "t3"):
        _insert_task(url, course.id, tid)
    _insert_task(url, other.id, "task-b")

    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    application = create_app()
    clock = Clock(T0)
    application.state.auth_clock = clock
    streams = TaskEventStreams(**FAST)
    application.state.task_event_streams = streams
    return {
        "app": application, "url": url, "clock": clock, "streams": streams,
        "teacher": teacher, "student": student, "outsider": outsider, "cohost": cohost,
        "course": course, "other": other,
    }


@pytest.fixture
def client(env):
    with TestClient(env["app"]) as test_client:
        yield test_client


def bearer(user) -> str:
    return issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=T0, ttl_seconds=3600
    )


def ticket_for(env, user, task_id: str) -> str:
    """Issue a ticket in the repository directly (the POST endpoint is C16's, tested there)."""
    return event_tickets.issue_ticket(env["url"], user_id=user.id, task_id=task_id, now=env["clock"]())


def get_task(client, tid: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.get(f"/api/v1/tasks/{tid}", headers=headers)


def frames_of(body: str) -> list[str]:
    assert body.endswith("\n\n") or body == ""
    return [part + "\n\n" for part in body.split("\n\n")[:-1]]


# --- 最小 ASGI 驱动：逐帧读取、随时断开 ------------------------------------------------------------


class Stream:
    """Drive one ``GET /events`` request against the ASGI app without buffering the body.

    ``spec`` selects Starlette's disconnect path: ``"2.3"`` listens for ``http.disconnect``;
    ``"2.4"`` notices the client only when a send fails (as uvicorn signals with ``OSError``).
    """

    def __init__(self, app, path: str, query: str, *, spec: str = "2.3",
                 headers: dict[str, str] | None = None) -> None:
        self.app, self.path, self.query, self.spec = app, path, query, spec
        self.request_headers = [(b"host", b"testserver")] + [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ]
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.ended = False

    async def open(self) -> "Stream":
        self.queue: asyncio.Queue = asyncio.Queue()
        self.gone = asyncio.Event()
        self._requested = False
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": self.spec},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": self.path, "raw_path": self.path.encode(), "root_path": "",
            "query_string": self.query.encode(), "headers": self.request_headers,
            "client": ("testclient", 50000), "server": ("testserver", 80),
        }
        self.task = asyncio.create_task(self.app(scope, self._receive, self._send))
        start = await asyncio.wait_for(self.queue.get(), 5)
        assert start["type"] == "http.response.start"
        self.status = start["status"]
        self.headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        return self

    async def _receive(self):
        if not self._requested:
            self._requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self.gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message):
        if self.gone.is_set() and self.spec == "2.4" and message["type"] == "http.response.body":
            raise OSError("client went away")
        await self.queue.put(message)

    async def frame(self, timeout: float = 5.0) -> str | None:
        """Next body chunk as text; ``None`` once the server closed the stream."""
        while not self.ended:
            message = await asyncio.wait_for(self.queue.get(), timeout)
            body = message.get("body", b"")
            if not message.get("more_body", False):
                self.ended = True
            if body:
                return body.decode("utf-8")
        return None

    async def event(self, timeout: float = 5.0) -> tuple[str, dict | None]:
        """Next non-ping event, parsed and contract-validated (overall deadline, pings included)."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("no event before the deadline")
            frame = await self.frame(remaining)
            assert frame is not None, "stream closed while an event was expected"
            parsed = parse_frame(frame)
            if parsed[0] != "ping":
                return parsed

    async def closes(self, timeout: float = 5.0) -> None:
        """The server ends the stream next (only pings may come first) and the app returns."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("stream still open after the deadline")
            frame = await self.frame(remaining)
            if frame is None:
                break
            assert parse_frame(frame)[0] == "ping", f"unexpected frame after end event: {frame!r}"
        await asyncio.wait_for(self.task, timeout)

    async def silent(self, seconds: float = 0.1) -> None:
        """No event arrives for ``seconds`` (the poller ran many times meanwhile)."""
        await asyncio.sleep(seconds)
        while not self.queue.empty():
            message = self.queue.get_nowait()
            body = message.get("body", b"").decode()
            assert body == "" or parse_frame(body)[0] == "ping", f"unexpected frame: {body!r}"
            assert message.get("more_body", False), "stream closed unexpectedly"

    async def disconnect(self, timeout: float = 5.0) -> None:
        self.gone.set()
        try:
            await asyncio.wait_for(self.task, timeout)
        except ClientDisconnect:
            pass  # 2.4 路径：Starlette 把发送失败（OSError）转成 ClientDisconnect 上抛，由服务器吞掉


async def open_stream(env, task_id: str, *, user=None, spec: str = "2.3") -> Stream:
    ticket = ticket_for(env, user or env["teacher"], task_id)
    stream = await Stream(env["app"], f"/api/v1/tasks/{task_id}/events", f"ticket={ticket}",
                          spec=spec).open()
    assert stream.status == 200
    return stream


class SseResponse:
    """A whole ``GET /events`` exchange; unlike TestClient it fails (times out) on a stream
    that never ends instead of hanging the test run."""

    def __init__(self, status_code: int, headers: dict[str, str], text: str) -> None:
        self.status_code, self.headers, self.text = status_code, headers, text

    def json(self):
        return json.loads(self.text)


def sse_get(env, task_id: str, *, params: dict[str, str] | None = None,
            headers: dict[str, str] | None = None, timeout: float = 5.0) -> SseResponse:
    async def exchange() -> SseResponse:
        stream = await Stream(env["app"], f"/api/v1/tasks/{task_id}/events",
                              urlencode(params or {}), headers=headers).open()
        chunks = []
        deadline = asyncio.get_running_loop().time() + timeout
        while (chunk := await stream.frame(max(0.001, deadline - asyncio.get_running_loop().time()))) is not None:
            chunks.append(chunk)
        await asyncio.wait_for(stream.task, timeout)
        return SseResponse(stream.status, stream.headers, "".join(chunks))

    return asyncio.run(exchange())


async def worker(env, task_id: str, stage: str, progress: float, **kwargs) -> None:
    await asyncio.to_thread(set_task, env["url"], task_id, stage, progress, **kwargs)


# --- 服务层：快照事件与差分 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "progress", "cancel", "name", "final"),
    [
        ("queued", 0.0, False, "stage", False),
        ("parsing", 0.05, False, "stage", False),
        ("extracting", 0.34, True, "stage", False),
        ("merging", 0.7, False, "stage", False),
        ("persisting", 0.85, False, "stage", False),
        ("awaiting_review", 0.95, False, "stage", True),
        ("completed", 1.0, False, "done", True),
        ("failed", 0.42, True, "error", True),
        ("cancelled", 0.2, True, "cancelled", True),
    ],
)
def test_snapshot_event_per_stage_matches_the_contract(stage, progress, cancel, name, final):
    error = _failed_error() if stage == "failed" else None
    event = snapshot_event(_snap(stage, progress, cancel, error))
    assert (event.name, event.final) == (name, final)
    kind, data = parse_frame(event.encode().decode("utf-8"))
    assert kind == name and data == event.data
    assert data["task_id"] == "t1" and data["stage"] == stage
    assert "course_id" not in data  # TaskEvent 各分支 additionalProperties: false
    if stage == "failed":
        assert data["error"] == {
            "code": "EXTRACTION_INCOMPLETE", "message": "抽取失败的块超过阈值",
            "details": {"chunks_failed": 3, "chunks_total": 10, "threshold": 0.2},
        }
        assert data["cancel_requested"] is True  # TASK-7：取消中失败保持 true
    if stage == "completed":
        assert data == {"task_id": "t1", "stage": "completed", "progress": 1}


@pytest.mark.parametrize("stage", ["queued", "parsing", "awaiting_review", "completed", "failed", "cancelled"])
def test_task_body_is_a_contract_task(stage):
    progress = {"queued": 0.0, "parsing": 0.05, "awaiting_review": 0.95, "completed": 1.0,
                "failed": 0.42, "cancelled": 0.2}[stage]
    error = _failed_error() if stage == "failed" else None
    body = task_body(_snap(stage, progress, stage in {"failed", "cancelled"}, error))
    assert _schema_valid("Task", body), body
    assert GENERATED.Task.model_validate(body).root.stage == stage
    assert "cancel_requested" in body  # B10F-R01：不依赖生成模型的默认值
    assert ("error" in body) == (stage == "failed")


def test_differ_pushes_only_real_changes_and_never_regresses():
    differ = EventDiffer(_snap("parsing", 0.05))
    assert differ.next(_snap("parsing", 0.05)) is None  # 无变化
    assert differ.next(_snap("parsing", 0.02)) is None  # 进度回退不推（I2）
    event = differ.next(_snap("parsing", 0.08))
    assert (event.name, event.data["progress"], event.final) == ("stage", 0.08, False)
    event = differ.next(_snap("extracting", 0.1))
    assert (event.data["stage"], event.data["progress"]) == ("extracting", 0.1)
    assert differ.next(_snap("parsing", 0.09)) is None  # 阶段回退不推（I1）
    event = differ.next(_snap("extracting", 0.1, cancel=True))  # 标志 false → true
    assert event.data["cancel_requested"] is True and event.data["progress"] == 0.1
    assert differ.next(_snap("extracting", 0.1, cancel=True)) is None  # 重复取消不推
    event = differ.next(_snap("awaiting_review", 0.95))
    assert (event.name, event.final, event.data["progress"]) == ("stage", True, 0.95)


def test_differ_ends_with_awaiting_review_even_if_polling_missed_it():
    # 两次轮询之间任务经 awaiting_review 被发布：处理期连接仍以 awaiting_review 收尾，不发 done（§7）。
    event = EventDiffer(_snap("persisting", 0.9)).next(_snap("completed", 1.0))
    assert (event.name, event.final) == ("stage", True)
    assert event.data == {"task_id": "t1", "stage": "awaiting_review", "progress": 0.95,
                          "cancel_requested": False}


@pytest.mark.parametrize(("stage", "name"), [("failed", "error"), ("cancelled", "cancelled")])
def test_differ_terminal_is_a_final_event(stage, name):
    error = _failed_error() if stage == "failed" else None
    event = EventDiffer(_snap("extracting", 0.3, True)).next(_snap(stage, 0.3, True, error))
    assert (event.name, event.final) == (name, True)


def test_default_intervals():
    streams = TaskEventStreams()
    assert DEFAULT_HEARTBEAT_SECONDS == 15
    assert streams.heartbeat_seconds == 15
    assert 0 < streams.poll_seconds <= 1


# --- GET /api/v1/tasks/{tid} ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "progress", "cancel"),
    [("queued", 0.0, 0), ("extracting", 0.34, 1), ("awaiting_review", 0.95, 0),
     ("completed", 1.0, 0), ("failed", 0.42, 1), ("cancelled", 0.3, 1)],
)
def test_get_task_returns_the_contract_snapshot(env, client, stage, progress, cancel):
    if stage != "queued":
        set_task(env["url"], "t1", stage, progress, cancel=cancel,
                 error=("EXTRACTION_INCOMPLETE", "抽取失败的块超过阈值",
                        '{"chunks_failed":3,"chunks_total":10,"threshold":0.2}'))
    row = _row(env["url"], "t1")
    response = get_task(client, "t1", bearer(env["teacher"]))
    assert response.status_code == 200  # failed 是领域状态，不是 HTTP 错误
    body = response.json()
    assert _schema_valid("Task", body), body
    assert GENERATED.Task.model_validate(body).root.stage == stage
    assert (body["id"], body["course_id"], body["document_id"]) == ("t1", env["course"].id, "doc-t1")
    assert (body["stage"], body["progress"], body["cancel_requested"]) == (stage, progress, bool(cancel))
    assert body["created_at"] == row["created_at"] and body["updated_at"] == row["updated_at"]
    if stage == "failed":
        assert body["error"] == {
            "code": "EXTRACTION_INCOMPLETE", "message": "抽取失败的块超过阈值",
            "details": {"chunks_failed": 3, "chunks_total": 10, "threshold": 0.2},
        }
    else:
        assert body.get("error") is None
    assert _row(env["url"], "t1") == row  # 只读


def test_get_task_authorization_matrix(env, client):
    assert get_task(client, "t1", None).status_code == 401
    assert get_task(client, "t1", "not-a-jwt").json()["code"] == "UNAUTHENTICATED"

    student = get_task(client, "t1", bearer(env["student"]))
    assert student.status_code == 403 and student.json()["code"] == "ROLE_FORBIDDEN"
    assert not (SNAPSHOT_KEYS & set(student.json()))

    # TASK-19 / IAM-18：非成员、不存在、跨课程三者同形 404，且不含快照字段。
    foreign = get_task(client, "t1", bearer(env["outsider"]))
    missing = get_task(client, "no-such-task", bearer(env["outsider"]))
    cross = get_task(client, "task-b", bearer(env["teacher"]))
    for response in (foreign, missing, cross):
        assert response.status_code == 404
        assert response.json() == missing.json() == {"code": "NOT_FOUND", "message": missing.json()["message"]}
        assert not (SNAPSHOT_KEYS & set(response.json()))

    cohost = get_task(client, "t1", bearer(env["cohost"]))
    assert cohost.status_code == 200 and cohost.json()["id"] == "t1"


# --- SSE 鉴权：票据与重新授权（TestClient，流在快照后即结束）---------------------------------------


def test_sse_full_flow_with_a_ticket_from_the_c16_endpoint(env, client):
    set_task(env["url"], "t1", "awaiting_review", 0.95)
    issued = client.post("/api/v1/tasks/t1/event-ticket",
                         headers={"Authorization": f"Bearer {bearer(env['teacher'])}"})
    assert issued.status_code == 200
    response = sse_get(env, "t1", params={"ticket": issued.json()["ticket"]})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    frames = frames_of(response.text)
    assert [parse_frame(f) for f in frames] == [
        ("stage", {"task_id": "t1", "stage": "awaiting_review", "progress": 0.95, "cancel_requested": False})
    ]
    assert env["streams"].subscribers("t1") == 0


@pytest.mark.parametrize(
    ("stage", "progress", "cancel", "name"),
    [("completed", 1.0, 0, "done"), ("failed", 0.42, 1, "error"), ("cancelled", 0.3, 1, "cancelled")],
)
def test_sse_on_a_terminal_task_sends_one_terminal_event_and_closes(env, client, stage, progress, cancel, name):
    # TASK-11 / TASK-20：终态后建连 → 对应终态事件作为首条快照，随后关流。
    set_task(env["url"], "t1", stage, progress, cancel=cancel)
    response = sse_get(env, "t1", params={"ticket": ticket_for(env, env["teacher"], "t1")})
    assert response.status_code == 200
    parsed = [parse_frame(f) for f in frames_of(response.text)]
    assert [kind for kind, _ in parsed] == [name]
    assert parsed[0][1]["stage"] == stage


def test_sse_ticket_is_single_use(env, client):
    set_task(env["url"], "t1", "awaiting_review", 0.95)
    ticket = ticket_for(env, env["teacher"], "t1")
    first = sse_get(env, "t1", params={"ticket": ticket})
    assert first.status_code == 200 and len(frames_of(first.text)) == 1
    again = sse_get(env, "t1", params={"ticket": ticket})
    assert again.status_code == 401 and again.json()["code"] == "UNAUTHENTICATED"
    assert not (SNAPSHOT_KEYS & set(again.json()))


def test_sse_rejects_every_non_ticket_credential_with_401(env, client):
    set_task(env["url"], "t1", "awaiting_review", 0.95)
    set_task(env["url"], "t2", "awaiting_review", 0.95)
    token = bearer(env["teacher"])

    cases = {
        "missing ticket, valid bearer header": sse_get(env, "t1", headers={"Authorization": f"Bearer {token}"}),
        "garbage": sse_get(env, "t1", params={"ticket": "x" * 43}),
        "empty": sse_get(env, "t1", params={"ticket": ""}),
        "access token as ticket": sse_get(env, "t1", params={"ticket": token}),
        "access token as token": sse_get(env, "t1", params={"token": token}),
    }
    other_task_ticket = ticket_for(env, env["teacher"], "t2")
    cases["ticket for another task"] = sse_get(env, "t1", params={"ticket": other_task_ticket})
    expired = ticket_for(env, env["teacher"], "t1")
    env["clock"].now = T0 + 60
    cases["expired"] = sse_get(env, "t1", params={"ticket": expired})
    env["clock"].now = T0

    for label, response in cases.items():
        assert response.status_code == 401, label
        assert response.json() == {"code": "UNAUTHENTICATED", "message": response.json()["message"]}, label
        assert response.headers["content-type"].startswith("application/json"), label

    # 跨任务核销失败不消耗 t2 的票据。
    still_valid = sse_get(env, "t2", params={"ticket": other_task_ticket})
    assert still_valid.status_code == 200 and parse_frame(frames_of(still_valid.text)[0])[1]["task_id"] == "t2"


def test_sse_reauthorizes_the_ticket_owner_before_streaming(env, client):
    set_task(env["url"], "t1", "awaiting_review", 0.95)
    url = env["url"]
    missing_shape = get_task(client, "no-such-task", bearer(env["teacher"])).json()

    # IAM-13 / IAM-22：申领后、连接前被移出课程 → 404，与不存在同形。
    removed = ticket_for(env, env["cohost"], "t1")
    assert remove_member(url, env["course"].id, env["cohost"].id)
    response = sse_get(env, "t1", params={"ticket": removed})
    assert response.status_code == 404 and response.json() == missing_shape

    # 课程内角色不是教师 → 403 ROLE_FORBIDDEN（票据直接写入仓储，模拟角色在申领后变化）。
    student = sse_get(env, "t1", params={"ticket": ticket_for(env, env["student"], "t1")})
    assert student.status_code == 403 and student.json()["code"] == "ROLE_FORBIDDEN"

    # 跨课程：票据指向别的课程的任务 → 404，不含快照。
    cross = sse_get(env, "task-b", params={"ticket": ticket_for(env, env["teacher"], "task-b")})
    assert cross.status_code == 404 and cross.json() == missing_shape

    # 账号已停用 → 401。
    disabled = ticket_for(env, env["teacher"], "t1")
    set_disabled(url, "teacher1", True)
    response = sse_get(env, "t1", params={"ticket": disabled})
    assert response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"

    for denied in (student, cross, response):
        assert not (SNAPSHOT_KEYS & set(denied.json()))
    assert env["streams"].subscribers("t1") == 0


# --- SSE 推送（逐帧驱动）-------------------------------------------------------------------------------


def test_sse_task1_full_processing_sequence(env):
    # TASK-1：按序推 stage，progress 单调不减；无变化、回退都不推；awaiting_review 后服务端关流。
    async def scenario():
        stream = await open_stream(env, "t1")
        assert await stream.event() == ("stage", {"task_id": "t1", "stage": "queued", "progress": 0,
                                                  "cancel_requested": False})
        steps = [("parsing", 0.0), ("parsing", 0.05), ("extracting", 0.1), ("extracting", 0.34),
                 ("merging", 0.6), ("merging", 0.7), ("persisting", 0.85)]
        seen = []
        for stage, progress in steps:
            await worker(env, "t1", stage, progress)
            kind, data = await stream.event()
            assert (kind, data["stage"], data["progress"]) == ("stage", stage, progress)
            seen.append(data["progress"])
            if (stage, progress) == ("extracting", 0.34):
                await worker(env, "t1", "extracting", 0.34)  # 只改 updated_at：不推
                await stream.silent()
                await worker(env, "t1", "extracting", 0.2)  # 进度回退：不推
                await stream.silent()
                await worker(env, "t1", "extracting", 0.34)
        assert seen == sorted(seen)
        assert env["streams"].subscribers("t1") == 1
        await worker(env, "t1", "awaiting_review", 0.95)
        assert await stream.event() == ("stage", {"task_id": "t1", "stage": "awaiting_review",
                                                  "progress": 0.95, "cancel_requested": False})
        await stream.closes()
        assert env["streams"].subscribers("t1") == 0

    asyncio.run(scenario())


def test_sse_running_cancel_pushes_the_flag_once_then_cancelled_closes(env):
    # TASK-4：取消中推同阶段 stage（cancel_requested: true），重复取消不推；检查点后推 cancelled 并关流。
    set_task(env["url"], "t1", "extracting", 0.3)

    async def scenario():
        stream = await open_stream(env, "t1")
        assert (await stream.event())[1]["cancel_requested"] is False
        outcome = await asyncio.to_thread(cancel_task, env["url"], "t1", course_id=env["course"].id)
        assert outcome.sse_event == "stage"
        assert await stream.event() == ("stage", {"task_id": "t1", "stage": "extracting", "progress": 0.3,
                                                  "cancel_requested": True})
        repeat = await asyncio.to_thread(cancel_task, env["url"], "t1", course_id=env["course"].id)
        assert repeat.sse_event is None
        await stream.silent()
        await worker(env, "t1", "cancelled", 0.3, cancel=1)
        assert await stream.event() == ("cancelled", {"task_id": "t1", "stage": "cancelled", "progress": 0.3,
                                                      "cancel_requested": True})
        await stream.closes()

    asyncio.run(scenario())


def test_sse_queued_cancel_pushes_cancelled_and_closes(env):
    # TASK-3
    async def scenario():
        stream = await open_stream(env, "t1")
        assert (await stream.event())[1]["stage"] == "queued"
        outcome = await asyncio.to_thread(cancel_task, env["url"], "t1", course_id=env["course"].id)
        assert outcome.sse_event == "cancelled"
        kind, data = await stream.event()
        assert (kind, data["stage"], data["cancel_requested"]) == ("cancelled", "cancelled", True)
        await stream.closes()

    asyncio.run(scenario())


def test_sse_failure_while_cancelling_pushes_exactly_one_error(env):
    # TASK-7：标志已置、检查点前失败 → 只推一次 error，cancel_requested 保持 true。
    set_task(env["url"], "t1", "extracting", 0.42, cancel=1)

    async def scenario():
        stream = await open_stream(env, "t1")
        assert (await stream.event())[1]["cancel_requested"] is True
        await worker(env, "t1", "failed", 0.42, cancel=1,
                     error=("LLM_UNAVAILABLE", "模型服务不可用", None))
        kind, data = await stream.event()
        assert kind == "error" and data["cancel_requested"] is True
        assert data["error"] == {"code": "LLM_UNAVAILABLE", "message": "模型服务不可用"}
        await stream.closes()

    asyncio.run(scenario())


def test_sse_heartbeat_while_the_worker_is_idle(env):
    # worker 崩溃或空闲：任务停在原阶段，连接只收心跳，不产生新事件。
    env["app"].state.task_event_streams = TaskEventStreams(poll_seconds=0.005, heartbeat_seconds=0.05)
    set_task(env["url"], "t1", "extracting", 0.3)

    async def scenario():
        stream = await open_stream(env, "t1")
        assert (await stream.event())[0] == "stage"
        for _ in range(3):
            assert await stream.frame(timeout=2) == ":ping\n\n"
        assert not stream.ended
        await stream.disconnect()

    asyncio.run(scenario())
    assert env["app"].state.task_event_streams.subscribers("t1") == 0


@pytest.mark.parametrize("spec", ["2.3", "2.4"])
def test_sse_disconnect_releases_the_listener(env, spec):
    # 两种 Starlette 断开路径（监听 http.disconnect / 发送失败）都要释放轮询协程与订阅计数。
    env["app"].state.task_event_streams = TaskEventStreams(poll_seconds=0.005, heartbeat_seconds=0.02)
    streams = env["app"].state.task_event_streams
    set_task(env["url"], "t1", "parsing", 0.02)

    async def scenario():
        first = await open_stream(env, "t1", spec=spec)
        second = await open_stream(env, "t1", spec=spec)
        assert (await first.event())[0] == (await second.event())[0] == "stage"
        assert streams.subscribers("t1") == 2 and streams.total() == 2
        await first.disconnect()
        assert first.task.done()
        assert streams.subscribers("t1") == 1
        await worker(env, "t1", "parsing", 0.06)
        assert (await second.event())[1]["progress"] == 0.06
        await second.disconnect()
        assert second.task.done()
        assert streams.subscribers("t1") == 0 and streams.total() == 0

    asyncio.run(scenario())


def test_sse_each_subscriber_gets_its_own_snapshot_then_broadcasts(env):
    set_task(env["url"], "t1", "parsing", 0.02)

    async def scenario():
        early = await open_stream(env, "t1")
        assert (await early.event())[1]["progress"] == 0.02
        await worker(env, "t1", "extracting", 0.2)
        assert (await early.event())[1]["stage"] == "extracting"
        late = await open_stream(env, "t1")
        assert await late.event() == ("stage", {"task_id": "t1", "stage": "extracting", "progress": 0.2,
                                                "cancel_requested": False})
        await worker(env, "t1", "extracting", 0.4)
        for stream in (early, late):
            assert (await stream.event())[1]["progress"] == 0.4
        await worker(env, "t1", "failed", 0.4, error=("INTERNAL_ERROR", "内部错误", None))
        for stream in (early, late):
            assert (await stream.event())[0] == "error"
            await stream.closes()
        assert env["streams"].subscribers("t1") == 0

    asyncio.run(scenario())


def test_sse_task20_subscription_before_publish(env, client):
    # TASK-20：extracting 时订阅 → awaiting_review 后被关流；随后发布，该连接不再收到任何事件；
    # GET 返回 completed；发布后新建的连接首条即 done 并被关流。
    set_task(env["url"], "t1", "extracting", 0.5)

    async def scenario():
        stream = await open_stream(env, "t1")
        assert (await stream.event())[1]["stage"] == "extracting"
        await worker(env, "t1", "awaiting_review", 0.95)
        assert (await stream.event())[1]["stage"] == "awaiting_review"
        await stream.closes()
        await worker(env, "t1", "completed", 1.0)
        assert stream.queue.empty()

    asyncio.run(scenario())
    assert get_task(client, "t1", bearer(env["teacher"])).json()["stage"] == "completed"
    response = sse_get(env, "t1", params={"ticket": ticket_for(env, env["teacher"], "t1")})
    assert [parse_frame(f)[0] for f in frames_of(response.text)] == ["done"]


def test_sse_publish_between_polls_still_ends_with_awaiting_review(env):
    # 轮询间隔内任务经 awaiting_review 被发布：连接仍以 awaiting_review 收尾，不发 done。
    set_task(env["url"], "t1", "persisting", 0.9)

    async def scenario():
        stream = await open_stream(env, "t1")
        assert (await stream.event())[1]["stage"] == "persisting"
        await worker(env, "t1", "completed", 1.0)
        assert await stream.event() == ("stage", {"task_id": "t1", "stage": "awaiting_review",
                                                  "progress": 0.95, "cancel_requested": False})
        await stream.closes()

    asyncio.run(scenario())


def test_sse_reconnect_starts_from_a_snapshot_not_lower_than_before(env):
    # TASK-11：断线 → 重新申领票据 → 新连接首条为当前快照，progress 不小于断线前。
    set_task(env["url"], "t1", "extracting", 0.3)

    async def scenario():
        first = await open_stream(env, "t1")
        before = (await first.event())[1]["progress"]
        await first.disconnect()
        await worker(env, "t1", "extracting", 0.45)
        second = await open_stream(env, "t1")
        kind, data = await second.event()
        assert kind == "stage" and data["progress"] == 0.45 >= before
        await second.disconnect()
        assert env["streams"].subscribers("t1") == 0

    asyncio.run(scenario())


def test_event_source_is_the_database_not_an_in_process_bus():
    # API 与 worker 是不同进程（§8.1）：事件流只能从 SQLite 行得出。
    source = Path(task_events.__file__).read_text(encoding="utf-8")
    assert "processing_tasks" in source
    for forbidden in ("asyncio.Queue", "Condition(", "publish(", "notify("):
        assert forbidden not in source
