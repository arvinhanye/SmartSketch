"""G04 SQLite pieces without Neo4j: the P4 draft-state read, T7 and the lock holder for COURSE_BUSY.

The full publish flow runs against a real Neo4j in ``tests/integration/test_g04.py``.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.repositories import course_locks, versions
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
REV_A, REV_B = "rev_" + "a" * 64, "rev_" + "b" * 64


def sha(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 's.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id).id
    other = create_course(url, name="B", description=None, creator_id=teacher.id).id

    def sql(query, *params):
        with connect(url) as db:
            return db.execute(query, params).fetchall()

    for cid, material in ((course, "m1"), (other, "m2")):
        sql("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
            "VALUES (?, ?, 'a.txt', 'txt', 1, ?, ?)", material, cid, sha(material), uuid.uuid4().hex)
    for rev, cid, material in ((REV_A, course, "m1"), (REV_B, other, "m2")):
        sql("INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
            "VALUES (?, ?, ?, ?, 'txt/1+chunk/1')", rev, cid, material, sha(rev))

    def task(task_id, stage, t6_seq=None, *, cid=course, material="m1", rev=REV_A):
        failed = stage == "failed"
        sql("INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, t6_seq, "
            "error_code, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            task_id, cid, material, stage, 0.95 if stage == "awaiting_review" else 1 if stage == "completed" else 0.5,
            task_id, t6_seq, "INTERNAL_ERROR" if failed else None, "x" if failed else None)
        sql("INSERT INTO task_revisions (task_id, revision_id, course_id, material_id) VALUES (?, ?, ?, ?)",
            task_id, rev, cid, material)

    return url, course, other, sql, task


def test_draft_state_reads_v_watermark_and_revisions_of_this_course_only(env):
    url, course, other, sql, task = env
    task("t-done", "completed", 1)
    task("t-review", "awaiting_review", 2)
    task("t-running", "extracting")
    task("t-failed", "failed")
    task("t-other", "awaiting_review", 7, cid=other, material="m2", rev=REV_B)
    sql("UPDATE courses SET draft_revision = 4 WHERE id = ?", course)
    state = versions.read_draft_state(url, course)
    assert state == versions.DraftState(course, 4, None, 2, ("t-done", "t-review"),
                                        ((REV_A, "m1", sha(REV_A), "txt/1+chunk/1"),))
    fresh = create_course(url, name="C", description=None, creator_id=sql("SELECT teacher_id FROM courses")[0][0])
    empty = versions.read_draft_state(url, fresh.id)
    assert (empty.task_watermark, empty.effective_task_ids, empty.revisions) == (0, (), ())
    with pytest.raises(LookupError):
        versions.read_draft_state(url, "missing")


def test_t7_completes_only_tasks_within_the_watermark(env):
    url, course, other, sql, task = env
    task("t1", "awaiting_review", 1)
    task("t2", "awaiting_review", 3)
    task("t-other", "awaiting_review", 1, cid=other, material="m2", rev=REV_B)
    with pytest.raises(RuntimeError):
        with connect(url) as db:
            versions.complete_published_tasks(db, course, 1)  # 必须在调用方事务里
    with versions.immediate(url) as db:
        assert versions.complete_published_tasks(db, course, 2) == 1
    assert dict(sql("SELECT id, stage FROM processing_tasks")) == {
        "t1": "completed", "t2": "awaiting_review", "t-other": "awaiting_review"}
    assert sql("SELECT progress FROM processing_tasks WHERE id = 't1'") == [(1.0,)]


def test_current_holder_reports_live_locks_only(env):
    url, course, *_ = env
    assert course_locks.current_holder(url, course) is None
    lock = course_locks.try_acquire(url, course, holder="edit", lease_seconds=30)
    assert course_locks.current_holder(url, course) == "edit"
    course_locks.release(url, lock)
    course_locks.try_acquire(url, course, holder="persisting", lease_seconds=30)
    with connect(url) as db:
        db.execute("UPDATE course_locks SET expires_at = unixepoch() - 1 WHERE course_id = ?", (course,))
    assert course_locks.current_holder(url, course) is None
