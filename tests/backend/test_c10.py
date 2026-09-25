"""C10：任务取消服务与 API（specs/task-processing.md §4、§8.2；specs/identity-access.md §4.1）。

- 服务层 ``app.services.task_cancel.cancel_task``：queued → cancelled（T3）；运行中置持久标志；
  重复取消幂等且不写；persisting / awaiting_review / 终态按契约拒绝，任务不变；按 course_id 隔离。
- 竞争：取消的条件更新与 C09 的领取、令牌写入（worker 的 T5）同处 SQLite ``BEGIN IMMEDIATE``
  写入序列，两个连接交错时结论确定（TASK-6、TASK-8）。
- 端点 ``POST /api/v1/tasks/{tid}/cancel``：授权矩阵 401 / 403 / 404，200 与 409 的响应体按契约
  JSON Schema（``Task``、``TaskNotCancellableError``）校验。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import sys
import threading
import uuid
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import task_leases
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services import task_cancel
from app.services.auth import issue_access_token
from app.services.task_cancel import TaskNotCancellable, TaskNotFound, cancel_task

ROOT = Path(__file__).resolve().parents[2]
SECRET = "c10-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
T0 = 1_900_000_000
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
SNAPSHOT_KEYS = {"id", "course_id", "document_id", "stage", "progress", "cancel_requested"}


# --- 契约校验（与 tests/contracts/test_b10.py 同法）-------------------------------------------

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
    spec = importlib.util.spec_from_file_location("c10_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATED = _generated()


# --- 数据准备 ------------------------------------------------------------------------------------


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _sql(url: str, statement: str, *params: object) -> None:
    with connect(url) as database:
        database.execute(statement, params)


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


def _claim(url: str, owner: str = "worker-a"):
    return task_leases.claim_next(url, owner=owner, lease_seconds=LEASE_SECONDS, max_attempts=MAX_ATTEMPTS)


def _running(url: str, task_id: str, stage: str, progress: float):
    """Claim ``task_id`` (the only queued one) and move it to ``stage`` under the lease."""
    lease = _claim(url)
    assert lease is not None and lease.task_id == task_id
    _sql(url, "UPDATE processing_tasks SET stage = ?, progress = ? WHERE id = ?", stage, progress, task_id)
    return lease


def _set_stage(url: str, task_id: str, stage: str, progress: float, *, cancel_requested: int = 0) -> None:
    if stage == "failed":
        _sql(
            url,
            "UPDATE processing_tasks SET stage = 'failed', progress = ?, cancel_requested = ?,"
            " error_code = 'INTERNAL_ERROR', error_message = '内部错误', error_details = NULL WHERE id = ?",
            progress, cancel_requested, task_id,
        )
    else:
        _sql(
            url,
            "UPDATE processing_tasks SET stage = ?, progress = ?, cancel_requested = ? WHERE id = ?",
            stage, progress, cancel_requested, task_id,
        )


def _worker_t5(database: sqlite3.Connection, task_id: str, token: str) -> int:
    """worker 的 T5（merging → persisting），带令牌与 ``cancel_requested = 0`` 条件（§4 竞争裁决）。"""
    return database.execute(
        "UPDATE processing_tasks SET stage = 'persisting', progress = 0.8"
        " WHERE id = ? AND lease_token = ? AND stage = 'merging' AND cancel_requested = 0",
        (task_id, token),
    ).rowcount


def _worker_t8(database: sqlite3.Connection, task_id: str, token: str) -> int:
    """worker 在检查点看到标志后转 cancelled（T8），同样带令牌条件。"""
    return database.execute(
        "UPDATE processing_tasks SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL,"
        " lease_expires_at = NULL WHERE id = ? AND lease_token = ?"
        " AND stage IN ('parsing', 'extracting', 'merging') AND cancel_requested = 1",
        (task_id, token),
    ).rowcount


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    return url


@pytest.fixture
def new_task(db_url):
    counter = iter(range(10**6))

    def _make(course_id: str = "course-a") -> str:
        return _insert_task(db_url, course_id, f"task-{next(counter)}")

    return _make


# --- 服务层：queued / 运行中 / 重复取消 ---------------------------------------------------------


def test_queued_cancel_goes_straight_to_cancelled_and_is_never_claimed(db_url, new_task):
    # TASK-3：200 语义 → stage = cancelled、cancel_requested = true；worker 此后不会领取。
    task_id = new_task()
    before = _row(db_url, task_id)
    outcome = cancel_task(db_url, task_id, course_id="course-a")

    assert outcome.changed is True
    assert outcome.sse_event == "cancelled"
    assert (outcome.task.stage, outcome.task.progress, outcome.task.cancel_requested) == ("cancelled", 0.0, True)
    assert outcome.task.error is None
    row = _row(db_url, task_id)
    assert (row["stage"], row["progress"], row["cancel_requested"]) == ("cancelled", 0, 1)
    assert row["lease_token"] is None and row["attempt"] == 0
    assert row["updated_at"] != before["updated_at"]
    assert outcome.task.updated_at == row["updated_at"]

    assert _claim(db_url) is None
    reclaimed = task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS)
    assert reclaimed.cancelled == () and reclaimed.failed == ()
    assert _row(db_url, task_id) == row


@pytest.mark.parametrize(
    ("stage", "progress"), [("parsing", 0.05), ("extracting", 0.34), ("merging", 0.7)]
)
def test_running_cancel_persists_the_intent_without_killing_the_worker(db_url, new_task, stage, progress):
    # TASK-4：运行中取消 → 当前 stage 不变、cancel_requested = true；租约不动，worker 在检查点收尾。
    task_id = new_task()
    lease = _running(db_url, task_id, stage, progress)
    before = _row(db_url, task_id)

    outcome = cancel_task(db_url, task_id, course_id="course-a")

    assert outcome.changed is True and outcome.sse_event == "stage"
    assert (outcome.task.stage, outcome.task.progress, outcome.task.cancel_requested) == (stage, progress, True)
    after = _row(db_url, task_id)
    assert after["cancel_requested"] == 1 and after["stage"] == stage and after["progress"] == progress
    for column in ("lease_token", "lease_owner", "lease_expires_at", "attempt", "not_before"):
        assert after[column] == before[column], column

    # 不强杀：worker 的令牌写入仍然成功，随后在检查点转 cancelled（T8）。
    with task_leases.leased_transaction(db_url, task_id, lease.token) as database:
        assert _worker_t8(database, task_id, lease.token) == 1
    final = _row(db_url, task_id)
    assert (final["stage"], final["cancel_requested"]) == ("cancelled", 1)


def test_repeated_cancel_while_cancelling_is_idempotent_and_writes_nothing(db_url, new_task):
    # TASK-5 前半：取消中再次取消 → 200，快照相同，不推新事件，不写任何数据。
    task_id = new_task()
    _running(db_url, task_id, "extracting", 0.3)
    first = cancel_task(db_url, task_id, course_id="course-a")
    row = _row(db_url, task_id)

    with connect(db_url) as database:
        before_version = database.execute("PRAGMA data_version").fetchone()[0]
        second = cancel_task(db_url, task_id, course_id="course-a")
        after_version = database.execute("PRAGMA data_version").fetchone()[0]

    assert second.changed is False and second.sse_event is None
    assert second.task == first.task
    assert _row(db_url, task_id) == row
    assert after_version == before_version  # 其他连接没有提交任何写入


def test_cancel_after_queued_cancel_is_rejected_as_already_terminal(db_url, new_task):
    # TASK-5 后半：已 cancelled 后再取消 → 409，reason = already_terminal、stage = cancelled。
    task_id = new_task()
    cancel_task(db_url, task_id, course_id="course-a")
    row = _row(db_url, task_id)
    with pytest.raises(TaskNotCancellable) as caught:
        cancel_task(db_url, task_id, course_id="course-a")
    assert (caught.value.stage, caught.value.reason) == ("cancelled", "already_terminal")
    assert caught.value.details == {"stage": "cancelled", "reason": "already_terminal"}
    assert _row(db_url, task_id) == row


# --- 服务层：不可取消的阶段 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "progress", "flag", "reason"),
    [
        ("persisting", 0.85, 0, "persisting_uninterruptible"),
        ("awaiting_review", 0.95, 0, "processing_finished"),
        ("completed", 1.0, 0, "already_terminal"),
        ("failed", 0.4, 0, "already_terminal"),
        ("failed", 0.4, 1, "already_terminal"),  # TASK-7：取消中失败，标志保持 true
        ("cancelled", 0.3, 1, "already_terminal"),
    ],
)
def test_uncancellable_stages_are_rejected_and_leave_the_task_unchanged(
    db_url, new_task, stage, progress, flag, reason
):
    # TASK-12、I3：终态不可变；persisting 不可中断；awaiting_review 不可取消。
    task_id = new_task()
    _set_stage(db_url, task_id, stage, progress, cancel_requested=flag)
    row = _row(db_url, task_id)
    with pytest.raises(TaskNotCancellable) as caught:
        cancel_task(db_url, task_id, course_id="course-a")
    assert (caught.value.stage, caught.value.reason) == (stage, reason)
    assert _row(db_url, task_id) == row


def test_cancel_is_scoped_to_the_course(db_url, new_task):
    # I7：跨课程取消查不到任务，不改变任务，也不给出快照。
    task_id = new_task("course-a")
    row = _row(db_url, task_id)
    with pytest.raises(TaskNotFound):
        cancel_task(db_url, task_id, course_id="course-b")
    with pytest.raises(TaskNotFound):
        cancel_task(db_url, "missing", course_id="course-a")
    assert _row(db_url, task_id) == row


# --- 竞争：与 C09 领取、令牌写入同一写入序列 ---------------------------------------------------------


def test_cancel_first_then_worker_t5_affects_zero_rows_and_task_ends_cancelled(db_url, new_task):
    # TASK-6 顺序一：标志先写 → worker 的 T5 影响 0 行，转 cancelled。
    task_id = new_task()
    lease = _running(db_url, task_id, "merging", 0.75)
    cancel_task(db_url, task_id, course_id="course-a")
    with task_leases.leased_transaction(db_url, task_id, lease.token) as database:
        assert _worker_t5(database, task_id, lease.token) == 0
        assert _worker_t8(database, task_id, lease.token) == 1
    assert _row(db_url, task_id)["stage"] == "cancelled"


def test_worker_t5_first_then_cancel_is_rejected_as_persisting(db_url, new_task):
    # TASK-6 顺序二：worker 先进入 persisting → 取消得 409 persisting_uninterruptible。
    task_id = new_task()
    lease = _running(db_url, task_id, "merging", 0.75)
    with task_leases.leased_transaction(db_url, task_id, lease.token) as database:
        assert _worker_t5(database, task_id, lease.token) == 1
    with pytest.raises(TaskNotCancellable) as caught:
        cancel_task(db_url, task_id, course_id="course-a")
    assert caught.value.reason == "persisting_uninterruptible"
    row = _row(db_url, task_id)
    assert (row["stage"], row["cancel_requested"], row["lease_token"]) == ("persisting", 0, lease.token)


def test_cancel_waits_for_an_open_worker_write_and_then_sees_its_result(db_url, new_task):
    # 两个连接交错：worker 已在 BEGIN IMMEDIATE 中完成 T5 但未提交；取消必须排在其后，结论确定为 409。
    task_id = new_task()
    lease = _running(db_url, task_id, "merging", 0.75)
    outcome: dict[str, object] = {}
    started = threading.Event()

    def cancel() -> None:
        started.set()
        try:
            outcome["result"] = cancel_task(db_url, task_id, course_id="course-a")
        except BaseException as exc:
            outcome["error"] = exc

    with task_leases.leased_transaction(db_url, task_id, lease.token) as database:
        assert _worker_t5(database, task_id, lease.token) == 1
        thread = threading.Thread(target=cancel)
        thread.start()
        assert started.wait(5)
        thread.join(0.5)
        assert thread.is_alive(), "取消必须等待 worker 的写事务，而不是读到未提交前的 merging"
    thread.join(10)
    assert not thread.is_alive()
    error = outcome.get("error")
    assert isinstance(error, TaskNotCancellable) and error.reason == "persisting_uninterruptible"
    assert _row(db_url, task_id)["cancel_requested"] == 0


def test_worker_waits_for_an_open_cancel_write_and_then_its_t5_loses(db_url, new_task, monkeypatch):
    # 反向交错：取消事务已写标志未提交时，worker 的令牌事务被串行到其后，T5 影响 0 行。
    task_id = new_task()
    lease = _running(db_url, task_id, "merging", 0.75)
    in_cancel = threading.Event()
    release = threading.Event()
    real_write = task_cancel._write_cancel

    def slow_write(database, snapshot, target):
        changed = real_write(database, snapshot, target)
        in_cancel.set()
        assert release.wait(10)
        return changed

    monkeypatch.setattr(task_cancel, "_write_cancel", slow_write)
    results: dict[str, object] = {}

    def cancel() -> None:
        results["cancel"] = cancel_task(db_url, task_id, course_id="course-a")

    def worker() -> None:
        with task_leases.leased_transaction(db_url, task_id, lease.token) as database:
            results["t5"] = _worker_t5(database, task_id, lease.token)
            if results["t5"] == 0:
                results["t8"] = _worker_t8(database, task_id, lease.token)

    canceller = threading.Thread(target=cancel)
    canceller.start()
    assert in_cancel.wait(5)
    runner = threading.Thread(target=worker)
    runner.start()
    runner.join(0.5)
    assert runner.is_alive(), "worker 的令牌写入必须等待取消事务"
    release.set()
    canceller.join(10)
    runner.join(10)
    assert results["cancel"].task.cancel_requested is True
    assert results["t5"] == 0 and results["t8"] == 1
    assert _row(db_url, task_id)["stage"] == "cancelled"


def test_stale_read_cannot_overwrite_a_newer_stage(db_url, new_task, monkeypatch):
    # 条件更新是比较并交换：即使判定用的读是旧的（merging），写入也不得落到已是 persisting 的行上。
    task_id = new_task()
    lease = _running(db_url, task_id, "merging", 0.75)
    real_read = task_cancel._read_task
    calls = {"n": 0}

    def read_then_race(database, tid, course_id):
        snapshot = real_read(database, tid, course_id)
        calls["n"] += 1
        if calls["n"] == 1:
            # 模拟判定之后、条件写之前，行已被推进到 persisting（绕过本事务直接改写同一连接上的行）。
            database.execute(
                "UPDATE processing_tasks SET stage = 'persisting', progress = 0.8 WHERE id = ?", (tid,)
            )
        return snapshot

    monkeypatch.setattr(task_cancel, "_read_task", read_then_race)
    with pytest.raises(TaskNotCancellable) as caught:
        cancel_task(db_url, task_id, course_id="course-a")
    assert caught.value.reason == "persisting_uninterruptible"
    assert calls["n"] == 2  # 条件写落空后重读、按新阶段重新判定
    # 拒绝回滚整个取消事务（连同模拟写入），标志从未落到该行上。
    row = _row(db_url, task_id)
    assert (row["stage"], row["cancel_requested"], row["lease_token"]) == ("merging", 0, lease.token)


def test_cancel_and_claim_race_on_two_connections_has_exactly_one_winner(db_url, new_task):
    # TASK-8：两个连接并发，恰好一方先写成功；领取赢 → 置标志；取消赢 → worker 领不到。
    outcomes = set()
    for _ in range(12):
        task_id = new_task()
        barrier = threading.Barrier(2)
        results: dict[str, object] = {}
        errors: list[BaseException] = []

        def claimer() -> None:
            try:
                barrier.wait()
                results["lease"] = _claim(db_url)
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        def canceller(tid: str = task_id) -> None:
            try:
                barrier.wait()
                results["cancel"] = cancel_task(db_url, tid, course_id="course-a")
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=claimer), threading.Thread(target=canceller)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        row = _row(db_url, task_id)
        cancelled = results["cancel"].task
        if results["lease"] is None:
            assert cancelled.stage == "cancelled" and results["cancel"].sse_event == "cancelled"
            assert (row["stage"], row["cancel_requested"], row["attempt"]) == ("cancelled", 1, 0)
            outcomes.add("cancel_won")
        else:
            assert results["lease"].task_id == task_id
            assert (cancelled.stage, cancelled.cancel_requested) == ("parsing", True)
            assert results["cancel"].sse_event == "stage"
            assert (row["stage"], row["cancel_requested"], row["lease_token"]) == (
                "parsing", 1, results["lease"].token,
            )
            outcomes.add("claim_won")
            # 置标志后结束本任务，免得下一轮 claim 领到它（C 要求 cancel_requested = 0，本就领不到）。
            assert _claim(db_url) is None
            _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", task_id)
            assert [t.task_id for t in task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS).cancelled] == [task_id]
    assert outcomes <= {"cancel_won", "claim_won"}


@pytest.mark.parametrize("first", ["claim", "cancel"])
def test_cancel_vs_claim_both_orders_are_deterministic(db_url, new_task, first):
    task_id = new_task()
    if first == "claim":
        lease = _claim(db_url)
        outcome = cancel_task(db_url, task_id, course_id="course-a")
        assert (outcome.task.stage, outcome.task.cancel_requested) == ("parsing", True)
        assert _row(db_url, task_id)["lease_token"] == lease.token
    else:
        outcome = cancel_task(db_url, task_id, course_id="course-a")
        assert outcome.task.stage == "cancelled"
        assert _claim(db_url) is None


def test_flag_then_worker_failure_keeps_the_flag_and_blocks_further_cancel(db_url, new_task):
    # TASK-7：标志已置、检查点前 worker 失败 → failed，cancel_requested 仍为 true；再取消 409。
    task_id = new_task()
    lease = _running(db_url, task_id, "extracting", 0.3)
    _sql(db_url, "UPDATE processing_tasks SET attempt = ? WHERE id = ?", MAX_ATTEMPTS, task_id)
    cancel_task(db_url, task_id, course_id="course-a")
    released = task_leases.release_after_transient_failure(
        db_url, task_id, lease.token, code="STORAGE_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
    )
    assert released.status == "failed"
    row = _row(db_url, task_id)
    assert (row["stage"], row["cancel_requested"]) == ("failed", 1)
    with pytest.raises(TaskNotCancellable) as caught:
        cancel_task(db_url, task_id, course_id="course-a")
    assert (caught.value.stage, caught.value.reason) == ("failed", "already_terminal")
    assert _row(db_url, task_id) == row


def test_expired_lease_with_cancel_intent_is_finished_by_the_reclaimer(db_url, new_task):
    # LEASE-8（C10 一侧）：API 写入的持久意图在 worker 崩溃后由回收者代行检查点。
    task_id = new_task()
    _running(db_url, task_id, "extracting", 0.3)
    cancel_task(db_url, task_id, course_id="course-a")
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", task_id)
    result = task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS)
    assert [t.task_id for t in result.cancelled] == [task_id]
    assert _row(db_url, task_id)["stage"] == "cancelled"
    assert _claim(db_url) is None


# --- 端点：授权矩阵与响应体 -------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)

    def account(name: str, role: str):
        return insert_account(
            url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role
        )

    teacher = account("teacher1", "teacher")
    student = account("student1", "student")
    outsider = account("teacher2", "teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    other = create_course(url, name="B", description=None, creator_id=outsider.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    for tid in ("q1", "run1", "persist1", "review1", "done1", "failed1", "cancelled1"):
        _insert_task(url, course.id, tid)
    _insert_task(url, other.id, "task-b")

    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    application = create_app()
    application.state.auth_clock = lambda: T0
    with TestClient(application) as client:
        yield {
            "client": client, "url": url, "teacher": teacher, "student": student,
            "outsider": outsider, "course": course, "other": other,
        }


def bearer(user) -> str:
    return issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=T0, ttl_seconds=3600
    )


def post_cancel(client, tid: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(f"/api/v1/tasks/{tid}/cancel", headers=headers)


def test_api_queued_cancel_returns_a_contract_valid_cancelled_snapshot(api):
    response = post_cancel(api["client"], "q1", bearer(api["teacher"]))
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "cancelled" and body["cancel_requested"] is True
    assert body["progress"] == 0 and body["id"] == "q1" and body["course_id"] == api["course"].id
    assert body["document_id"] == "doc-q1"
    assert "error" not in body or body["error"] is None
    # B10F-R01：生成模型对缺 cancel_requested 的取消快照过于宽松，响应体必须显式带上它。
    assert "cancel_requested" in body
    assert _schema_valid("Task", body)
    assert GENERATED.Task.model_validate(body).root.stage == "cancelled"
    assert _row(api["url"], "q1")["stage"] == "cancelled"


def test_api_running_cancel_returns_the_real_stage_with_the_flag(api):
    url = api["url"]
    _sql(url, "UPDATE processing_tasks SET not_before = unixepoch() + 3600 WHERE id != 'run1'")
    _running(url, "run1", "extracting", 0.34)
    token = bearer(api["teacher"])
    first = post_cancel(api["client"], "run1", token)
    assert first.status_code == 200
    body = first.json()
    assert (body["stage"], body["progress"], body["cancel_requested"]) == ("extracting", 0.34, True)
    assert _schema_valid("Task", body)
    row = _row(url, "run1")

    second = post_cancel(api["client"], "run1", token)
    assert second.status_code == 200 and second.json() == body
    assert _row(url, "run1") == row


@pytest.mark.parametrize(
    ("tid", "stage", "progress", "flag", "reason"),
    [
        ("persist1", "persisting", 0.85, 0, "persisting_uninterruptible"),
        ("review1", "awaiting_review", 0.95, 0, "processing_finished"),
        ("done1", "completed", 1.0, 0, "already_terminal"),
        ("failed1", "failed", 0.4, 1, "already_terminal"),
        ("cancelled1", "cancelled", 0.2, 1, "already_terminal"),
    ],
)
def test_api_uncancellable_returns_409_with_closed_details(api, tid, stage, progress, flag, reason):
    url = api["url"]
    _set_stage(url, tid, stage, progress, cancel_requested=flag)
    row = _row(url, tid)
    response = post_cancel(api["client"], tid, bearer(api["teacher"]))
    assert response.status_code == 409
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == "TASK_NOT_CANCELLABLE"
    assert body["details"] == {"stage": stage, "reason": reason}
    assert body["message"].strip()
    assert _schema_valid("TaskNotCancellableError", body)
    GENERATED.TaskNotCancellableError.model_validate(body)
    assert _row(url, tid) == row


def test_api_authorization_matrix(api):
    url, client = api["url"], api["client"]
    before = {tid: _row(url, tid) for tid in ("q1", "task-b")}

    assert post_cancel(client, "q1", None).status_code == 401
    assert post_cancel(client, "q1", "not-a-jwt").json()["code"] == "UNAUTHENTICATED"

    student = post_cancel(client, "q1", bearer(api["student"]))
    assert student.status_code == 403 and student.json()["code"] == "ROLE_FORBIDDEN"

    # IAM-18 / TASK-19：非成员教师与不存在的 tid 同为 404，响应体一致且不含快照字段。
    foreign = post_cancel(client, "q1", bearer(api["outsider"]))
    missing = post_cancel(client, "no-such-task", bearer(api["outsider"]))
    cross = post_cancel(client, "task-b", bearer(api["teacher"]))
    for response in (foreign, missing, cross):
        assert response.status_code == 404
        assert response.json() == {"code": "NOT_FOUND", "message": missing.json()["message"]}
        assert not (SNAPSHOT_KEYS & set(response.json()))

    assert {tid: _row(url, tid) for tid in before} == before


def test_api_disabled_teacher_is_unauthenticated(api):
    url = api["url"]
    _sql(url, "UPDATE users SET disabled_at = '2026-09-25T00:00:00Z' WHERE id = ?", api["teacher"].id)
    response = post_cancel(api["client"], "q1", bearer(api["teacher"]))
    assert response.status_code == 401
    assert _row(url, "q1")["stage"] == "queued"


def test_route_is_the_contract_operation():
    from app.main import app

    schema = app.openapi()
    operation = schema["paths"]["/api/v1/tasks/{tid}/cancel"]["post"]
    assert operation["operationId"] == "cancelTask"
    assert {"200", "401", "403", "404", "409"} <= set(operation["responses"])
    # 路由只做协议转换：不含 SQL。
    source = (ROOT / "src/backend/app/api/task_cancel.py").read_text(encoding="utf-8")
    for token in ("UPDATE ", "SELECT ", "BEGIN", "connect("):
        assert token not in source
    assert json.dumps(operation, ensure_ascii=False)
