"""遗留 3（PR #264 独立审查）：失败任务没有可撤销的贡献时，清理不再空等课程锁（ADR-072）。

鉴别方式：假仓储记录读/写调用，``course_locks.acquire`` 与撤销语句被替换为记录器。
「无工作」必须 0 次取锁、0 次撤销，并清掉 ``cleanup_pending``；「有工作」必须仍取锁并撤销。
"""

from __future__ import annotations

import uuid

import pytest

from app.repositories import course_locks
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.neo4j import RepositoryConnectionError
from app.repositories.sqlite import connect, migrate
from app.workers import persist_graph

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


class _Recorder:
    """只实现清理用到的两个方法：``read``（判断有无贡献）与 ``write_transaction``（撤销）。"""

    def __init__(self, busy: bool, *, fail_read: bool = False) -> None:
        self.busy = busy
        self.fail_read = fail_read
        self.reads: list[tuple[str, dict]] = []
        self.writes = 0

    def read(self, query, scope, *, reader, parameters):
        self.reads.append((reader, dict(parameters)))
        if self.fail_read:
            raise RepositoryConnectionError()
        return [{"busy": self.busy}]

    def write_transaction(self, scope, work):
        self.writes += 1
        return work(object())


def _failed_task(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    task_id = uuid.uuid4().hex
    with connect(url) as database:
        database.execute(
            "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
            " VALUES ('doc1', ?, 'a.txt', 'txt', 1, ?, 'stored')",
            (course.id, "sha256:" + "0" * 64),
        )
        database.execute(
            "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key, stage, progress,"
            " error_code, error_message, cleanup_pending) VALUES (?, ?, 'doc1', ?, 'failed', 1.0,"
            " 'INTERNAL_ERROR', '测试用失败任务', 1)",
            (task_id, course.id, task_id),
        )
    return url, task_id, course.id


def _cleanup_pending(url: str, task_id: str) -> int:
    with connect(url) as database:
        return database.execute("SELECT cleanup_pending FROM processing_tasks WHERE id = ?",
                                (task_id,)).fetchone()[0]


def _explode(*args, **kwargs):
    raise AssertionError("must not run when there is nothing to revoke")


def test_no_pending_work_clears_the_marker_without_taking_the_course_lock(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=False)
    acquired: list[str] = []
    monkeypatch.setattr(course_locks, "acquire", lambda *a, **k: acquired.append(k.get("holder")) or None)
    monkeypatch.setattr(persist_graph, "lock_draft", _explode)
    monkeypatch.setattr(persist_graph, "revoke_task", _explode)

    assert persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id, holder="w",
                                             lock_seconds=60, lock_wait_seconds=30) is True

    assert acquired == [] and repo.writes == 0
    assert repo.reads == [("worker", {"task_id": task_id})]
    assert _cleanup_pending(url, task_id) == 0


def test_pending_work_still_takes_the_lock_and_revokes(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=True)
    acquired: list[str] = []
    real_acquire = course_locks.acquire

    def acquire(*args, **kwargs):
        acquired.append(kwargs.get("holder"))
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(course_locks, "acquire", acquire)
    revoked: list[object] = []
    monkeypatch.setattr(persist_graph, "lock_draft", lambda tx: revoked.append("lock"))
    monkeypatch.setattr(persist_graph, "revoke_task", lambda tx, task_id: revoked.append(task_id))

    assert persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id, holder="w",
                                             lock_seconds=60, lock_wait_seconds=30) is True

    assert acquired == ["w"] and repo.writes == 1
    assert revoked == ["lock", task_id]
    assert _cleanup_pending(url, task_id) == 0


def test_unreadable_graph_leaves_the_marker_and_takes_no_lock(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=False, fail_read=True)
    acquired: list[str] = []
    monkeypatch.setattr(course_locks, "acquire", lambda *a, **k: acquired.append(k.get("holder")) or None)
    monkeypatch.setattr(persist_graph, "lock_draft", _explode)
    monkeypatch.setattr(persist_graph, "revoke_task", _explode)

    assert persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id, holder="w",
                                             lock_seconds=60, lock_wait_seconds=30) is False

    assert acquired == [] and repo.writes == 0
    assert _cleanup_pending(url, task_id) == 1


def test_the_contribution_check_rejects_a_blank_task_id(tmp_path):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=True)
    with pytest.raises(ValueError):
        persist_graph.task_has_contributions(repo, persist_graph.GraphScope(course_id, persist_graph.DRAFT_VERSION,
                                                                            effective_task_ids=()), "  ")
