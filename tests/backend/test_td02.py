"""TD-02：任务行读取 SQL 迁入 ``repositories/tasks.py``。

只搬迁、不改行为；本文件覆盖新仓储函数（含课程隔离）与分层约束：

- ``get_task_snapshot`` / ``read_task_snapshot``：按 ``id AND course_id`` 读含 ``error_*`` 列的任务行；
- ``mark_cancel_requested``：C10 取消的比较并交换写入，调用方连接、同一事务；
- ``read_leased_task``：D11 按租约令牌读任务行；
- 服务层与 worker 不再直接读 ``processing_tasks``；行 → ``TaskSnapshot`` 映射只有一处；
- 仓储不依赖服务层。
"""

from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

import pytest

from app.repositories import tasks as task_repo
from app.repositories.sqlite import connect, migrate
from app.services import task_cancel, task_events
from app.workers import parse_task

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src/backend/app"
TS = "2026-09-25T00:00:00.000Z"


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


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
            (task_id, course_id, f"doc-{task_id}", f"key-{task_id}", TS, TS),
        )
    return task_id


def _sql(url: str, statement: str, *params: object) -> None:
    with connect(url) as db:
        db.execute(statement, params)


def _row(url: str, task_id: str) -> dict[str, object]:
    with connect(url) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM processing_tasks WHERE id = ?", (task_id,)).fetchone())


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    _insert_task(url, "course-a", "t-a")
    _insert_task(url, "course-b", "t-b")
    return url


# --- get_task_snapshot / read_task_snapshot ------------------------------------------------------


def test_get_task_snapshot_returns_the_row_for_its_own_course(db_url):
    row = task_repo.get_task_snapshot(db_url, "t-a", course_id="course-a")
    assert row == task_repo.TaskSnapshotRow(
        id="t-a", course_id="course-a", document_id="doc-t-a", stage="queued", progress=0.0,
        cancel_requested=False, created_at=TS, updated_at=TS,
        error_code=None, error_message=None, error_details_json=None,
    )
    assert isinstance(row.progress, float) and row.cancel_requested is False


def test_get_task_snapshot_is_isolated_by_course(db_url):
    # 课程隔离：另一课程的任务 ID 与不存在的 ID 同样得到 None，不泄露任何字段。
    assert task_repo.get_task_snapshot(db_url, "t-b", course_id="course-a") is None
    assert task_repo.get_task_snapshot(db_url, "t-a", course_id="course-b") is None
    assert task_repo.get_task_snapshot(db_url, "missing", course_id="course-a") is None
    assert task_repo.get_task_snapshot(db_url, "t-b", course_id="course-b").course_id == "course-b"


def test_get_task_snapshot_carries_raw_error_columns(db_url):
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'failed', error_code = 'DOCUMENT_UNREADABLE',"
        " error_message = '无法读取', error_details = '{\"reason\": \"no_text\"}' WHERE id = ?",
        "t-a",
    )
    row = task_repo.get_task_snapshot(db_url, "t-a", course_id="course-a")
    assert (row.stage, row.error_code, row.error_message) == ("failed", "DOCUMENT_UNREADABLE", "无法读取")
    assert row.error_details_json == '{"reason": "no_text"}'  # 解码留给服务层的唯一映射


def test_read_task_snapshot_uses_the_callers_connection_and_transaction(db_url):
    with connect(db_url) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE processing_tasks SET stage = 'parsing', progress = 0.1 WHERE id = 't-a'")
        seen = task_repo.read_task_snapshot(db, "t-a", course_id="course-a")
        assert task_repo.read_task_snapshot(db, "t-a", course_id="course-b") is None
        db.execute("ROLLBACK")
    assert (seen.stage, seen.progress) == ("parsing", 0.1)  # 看到本事务未提交的写入
    assert task_repo.get_task_snapshot(db_url, "t-a", course_id="course-a").stage == "queued"


# --- mark_cancel_requested -----------------------------------------------------------------------


def test_mark_cancel_requested_is_a_compare_and_swap_scoped_to_the_course(db_url):
    with connect(db_url) as db:
        # 课程不符、阶段不符都不写。
        assert not task_repo.mark_cancel_requested(
            db, task_id="t-a", course_id="course-b", expected_stage="queued", target_stage="cancelled"
        )
        assert not task_repo.mark_cancel_requested(
            db, task_id="t-a", course_id="course-a", expected_stage="parsing", target_stage="parsing"
        )
    assert _row(db_url, "t-a")["cancel_requested"] == 0
    with connect(db_url) as db:
        assert task_repo.mark_cancel_requested(
            db, task_id="t-a", course_id="course-a", expected_stage="queued", target_stage="cancelled"
        )
        # 标志已为真 → 条件不再成立，重复写入 0 行。
        assert not task_repo.mark_cancel_requested(
            db, task_id="t-a", course_id="course-a", expected_stage="cancelled", target_stage="cancelled"
        )
    row = _row(db_url, "t-a")
    assert (row["stage"], row["cancel_requested"]) == ("cancelled", 1)
    assert row["updated_at"] != TS
    assert _row(db_url, "t-b")["cancel_requested"] == 0


def test_mark_cancel_requested_never_writes_uninterruptible_stages(db_url):
    _sql(db_url, "UPDATE processing_tasks SET stage = 'persisting', progress = 0.8 WHERE id = 't-a'")
    with connect(db_url) as db:
        assert not task_repo.mark_cancel_requested(
            db, task_id="t-a", course_id="course-a", expected_stage="persisting", target_stage="persisting"
        )
    assert _row(db_url, "t-a")["cancel_requested"] == 0


# --- read_leased_task ----------------------------------------------------------------------------


def test_read_leased_task_matches_only_the_current_token(db_url):
    token, other = "1" * 32, "2" * 32
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'parsing', progress = 0.05, lease_token = ?,"
        " lease_owner = 'worker-a', lease_expires_at = unixepoch() + 60, cancel_requested = 1 WHERE id = 't-a'",
        token,
    )
    with connect(db_url) as db:
        row = task_repo.read_leased_task(db, "t-a", token)
        assert task_repo.read_leased_task(db, "t-a", other) is None
        assert task_repo.read_leased_task(db, "t-b", token) is None
    assert row == task_repo.LeasedTaskRow(
        course_id="course-a", document_id="doc-t-a", stage="parsing", progress=0.05, cancel_requested=True
    )


# --- 单一映射与分层 ------------------------------------------------------------------------------


def test_services_map_repository_rows_through_one_snapshot_function(db_url):
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'failed', error_code = 'INTERNAL_ERROR',"
        " error_message = 'x', error_details = NULL WHERE id = 't-a'",
    )
    snapshot = task_events.load_task(db_url, "t-a", course_id="course-a")
    assert isinstance(snapshot, task_cancel.TaskSnapshot)
    assert snapshot.error is not None and snapshot.error.details is None
    assert task_events.load_task(db_url, "t-a", course_id="course-b") is None
    assert not hasattr(task_events, "_snapshot_from_row")
    assert task_events.snapshot_from_row is task_cancel.snapshot_from_row
    cancel_source = Path(task_cancel.__file__).read_text(encoding="utf-8")
    events_source = Path(task_events.__file__).read_text(encoding="utf-8")
    assert cancel_source.count("TaskSnapshot(") == 1 and "TaskSnapshot(" not in events_source


@pytest.mark.parametrize("path", ["services/task_cancel.py", "services/task_events.py", "workers/parse_task.py"])
def test_services_and_workers_do_not_read_processing_tasks_directly(path):
    source = (APP / path).read_text(encoding="utf-8")
    assert "FROM processing_tasks" not in source
    assert re.search(r"SELECT\b[^;]*?processing_tasks", source) is None


def test_task_cancel_holds_no_task_sql():
    # C10 的取消写入一并迁入仓储：服务只剩事务边界与判定。
    source = (APP / "services/task_cancel.py").read_text(encoding="utf-8")
    assert "processing_tasks" not in source and "UPDATE" not in source


def test_repository_does_not_depend_on_services():
    tree = ast.parse((APP / "repositories/tasks.py").read_text(encoding="utf-8"))
    imported = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    ] + [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not [name for name in imported if name.startswith("app.services") or name.startswith("app.workers")]


def test_worker_reads_its_row_through_the_repository():
    assert parse_task.read_leased_task is task_repo.read_leased_task
