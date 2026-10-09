"""ADR-094 replaces the ADR-072 empty pre-read shortcut; all cleanup is ordered."""

from __future__ import annotations

import uuid
import time
import threading
from contextlib import contextmanager
from types import SimpleNamespace

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

    @contextmanager
    def persist_write_transaction(self, scope, *, check, remaining):
        check()
        assert remaining() > 0
        self.writes += 1
        if self.fail_read:
            raise RepositoryConnectionError()
        tx = SimpleNamespace(scope=scope, commit_started=False, committed=False)
        def commit(*, started_at):
            assert started_at <= time.monotonic()
            check()
            tx.commit_started = True
            if getattr(self, 'fail_commit', False):
                raise RepositoryConnectionError()
            tx.committed = True
        tx.commit = commit
        yield tx
        assert tx.committed


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


def test_no_pending_work_still_serializes_and_revokes(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=False)
    acquired = []
    real_acquire = course_locks.acquire
    def acquire(*args, **kwargs):
        acquired.append(kwargs['holder'])
        return real_acquire(*args, **kwargs)
    monkeypatch.setattr(course_locks, 'acquire', acquire)
    ordered = []
    monkeypatch.setattr(persist_graph, 'lock_draft', lambda tx: ordered.append('lock'))
    monkeypatch.setattr(persist_graph, 'revoke_task', lambda tx, tid: ordered.append(tid))
    assert persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id,
        holder='w', lock_seconds=60, lock_wait_seconds=0)
    assert acquired == ['w'] and repo.writes == 1
    assert repo.reads == []
    assert ordered == ['lock', task_id]
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


def test_unreadable_graph_leaves_marker_after_course_lock_attempt(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=False, fail_read=True)
    acquired = []
    real_acquire = course_locks.acquire
    def acquire(*args, **kwargs):
        acquired.append(kwargs['holder'])
        return real_acquire(*args, **kwargs)
    monkeypatch.setattr(course_locks, 'acquire', acquire)
    monkeypatch.setattr(persist_graph, 'lock_draft', _explode)
    monkeypatch.setattr(persist_graph, 'revoke_task', _explode)
    assert not persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id,
        holder='w', lock_seconds=60, lock_wait_seconds=0)
    assert acquired == ['w'] and repo.writes == 1
    assert _cleanup_pending(url, task_id) == 1


def test_the_contribution_check_rejects_a_blank_task_id(tmp_path):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=True)
    with pytest.raises(ValueError):
        persist_graph.task_has_contributions(repo, persist_graph.GraphScope(course_id, persist_graph.DRAFT_VERSION,
                                                                            effective_task_ids=()), "  ")


def test_empty_cleanup_waits_for_old_graph_guard(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=False)
    old_guard = threading.Lock()
    entered = threading.Event()
    contributions = set()
    result = []
    def lock(tx):
        entered.set()
        assert old_guard.acquire(timeout=2)
        old_guard.release()
    monkeypatch.setattr(persist_graph, 'lock_draft', lock)
    monkeypatch.setattr(persist_graph, 'revoke_task', lambda tx, tid: contributions.discard(tid))
    old_guard.acquire()
    def cleanup():
        result.append(persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id,
            holder='w', lock_seconds=60, lock_wait_seconds=0))
    thread = threading.Thread(target=cleanup)
    thread.start()
    try:
        assert entered.wait(2)
        assert _cleanup_pending(url, task_id) == 1
        contributions.add(task_id)  # old graph decision after empty observation
    finally:
        old_guard.release()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert result == [True] and contributions == set()
    assert _cleanup_pending(url, task_id) == 0


def test_cleanup_uncertain_ack_keeps_marker_and_preserves_other_contributions(tmp_path, monkeypatch):
    url, task_id, course_id = _failed_task(tmp_path)
    repo = _Recorder(busy=True)
    repo.fail_commit = True
    other = {'other-task', 'manual'}
    values = {task_id} | other
    monkeypatch.setattr(persist_graph, 'lock_draft', lambda tx: None)
    monkeypatch.setattr(persist_graph, 'revoke_task', lambda tx, tid: values.discard(tid))
    assert not persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id,
        holder='w', lock_seconds=60, lock_wait_seconds=0)
    assert _cleanup_pending(url, task_id) == 1
    assert values == other
    repo.fail_commit = False
    assert persist_graph.cleanup_failed_task(url, repo, course_id=course_id, task_id=task_id,
        holder='w', lock_seconds=60, lock_wait_seconds=0)
    assert _cleanup_pending(url, task_id) == 0 and values == other
