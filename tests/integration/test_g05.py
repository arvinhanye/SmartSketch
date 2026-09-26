"""G05 against a real Neo4j and a migrated SQLite: publish compensation (C1) and the sweeper (V9).

Acceptance: failures injected at every SQLite/Neo4j stage leave the old pointer and no copy behind
(or a ``cleanup_pending`` row the sweeper finishes); compensation is idempotent; the sweeper never
removes a version that can still be read (specs/teacher-review-publish.md V5 C1, V9, PUB-18/19/20).
"""

from __future__ import annotations

import logging

import pytest

from app.repositories import versions
from app.repositories.courses import create_course
from app.repositories.versions import CommitRejected
from app.services.versions import publish as publishing
from app.services.versions import reconcile
from app.services.versions.materialize import VerificationError
from app.services.versions.publish import PublishFailed
from app.services.versions.reconcile import LEASE_EXPIRED, compensate, sweep, sweep_course
from test_g04 import base_graph, counts, env, graph_versions, last_attempt, live, pointer, run, stage, student_names

pytestmark = live
__all__ = ["env"]  # 夹具取自 test_g04


class _Crash(BaseException):
    """模拟进程被杀：不被发布流程的 ``except Exception`` 捕获，尝试行停在进行中。"""


def expire(env, version_id):
    env.sql("UPDATE graph_versions SET expires_at = unixepoch() - 1 WHERE version_id = ?", version_id)


def published_v1_then_edit(env):
    base_graph(env)
    first = run(env)
    env.set_def("a", "新定义")
    env.task("t3", "awaiting_review", 2)
    return first


def crash_after(monkeypatch, target, name):
    real = getattr(target, name)

    def crashing(*args, **kwargs):
        real(*args, **kwargs)
        raise _Crash()

    monkeypatch.setattr(target, name, crashing)


def assert_old_version_intact(env, first):
    assert pointer(env)[:2] == (first.version_id, 1)
    assert student_names(env, first.version_id) == {"a", "b", "c"}
    assert stage(env, "t3") == "awaiting_review"


# ---------------------------------------------------------------- PUB-18：各阶段失败


@pytest.mark.parametrize("mode", ["raise", "refused"])
def test_p7_snapshot_write_failure_keeps_the_old_pointer(env, monkeypatch, mode):
    first = published_v1_then_edit(env)
    if mode == "raise":
        def broken(*args, **kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(versions, "record_snapshot", broken)
    else:
        monkeypatch.setattr(versions, "record_snapshot", lambda *a, **k: False)
    with pytest.raises(PublishFailed) as caught:
        run(env)
    assert caught.value.step == "P7"
    attempt = last_attempt(env)
    assert (attempt.state, attempt.cleanup_pending) == ("failed", False)
    assert graph_versions(env) == {"draft", first.version_id}
    assert_old_version_intact(env, first)


def test_neo4j_cleanup_failure_is_finished_by_the_sweeper(env, monkeypatch):
    first = published_v1_then_edit(env)

    def bad_verify(*args, **kwargs):
        raise VerificationError("drift")

    def no_drop(*args, **kwargs):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(publishing, "verify", bad_verify)
    monkeypatch.setattr(reconcile, "drop_version", no_drop)
    with pytest.raises(PublishFailed):
        run(env)
    failed = last_attempt(env)
    assert (failed.state, failed.cleanup_pending) == ("failed", True)
    assert failed.version_id in graph_versions(env)  # 副本残留，等待清扫
    report = sweep_course(env.url, env.repo, env.course)
    assert report.pending == [failed.version_id] and report.dropped == []  # Neo4j 仍不可用：标记保留
    monkeypatch.undo()

    report = sweep_course(env.url, env.repo, env.course)
    assert (report.dropped, report.pending, report.expired) == ([failed.version_id], [], [])
    assert versions.get_version(env.url, failed.version_id).cleanup_pending is False
    assert graph_versions(env) == {"draft", first.version_id}
    again = sweep_course(env.url, env.repo, env.course)
    assert not again.changed and again.pending == []  # 幂等
    assert_old_version_intact(env, first)


def test_sqlite_failure_during_c1_is_finished_after_the_lease_expires(env, monkeypatch):
    first = published_v1_then_edit(env)

    def bad_verify(*args, **kwargs):
        raise VerificationError("drift")

    def sqlite_down(*args, **kwargs):
        raise OSError("database is locked")

    monkeypatch.setattr(publishing, "verify", bad_verify)
    monkeypatch.setattr(versions, "fail_attempt", sqlite_down)
    with pytest.raises(PublishFailed):
        run(env)
    monkeypatch.undo()
    stuck = last_attempt(env)
    assert stuck.state == "preparing" and stuck.version_id in graph_versions(env)
    assert not sweep_course(env.url, env.repo, env.course).changed  # 租约未到期：不动
    expire(env, stuck.version_id)
    report = sweep_course(env.url, env.repo, env.course)
    assert report.expired == [stuck.version_id]
    record = versions.get_version(env.url, stuck.version_id)
    assert (record.state, record.failure_reason, record.cleanup_pending) == ("failed", LEASE_EXPIRED, False)
    assert graph_versions(env) == {"draft", first.version_id}
    assert_old_version_intact(env, first)


# ---------------------------------------------------------------- PUB-19：P8 之后崩溃


@pytest.mark.parametrize("where", ["materialize", "verify", "mark_materialized"])
def test_crash_between_p8_and_p11_is_swept_and_publishing_resumes(env, monkeypatch, where):
    first = published_v1_then_edit(env)
    crash_after(monkeypatch, versions if where == "mark_materialized" else publishing, where)
    with pytest.raises(_Crash):
        run(env)
    monkeypatch.undo()
    crashed = last_attempt(env)
    assert crashed.state in ("preparing", "materialized") and crashed.version_id in graph_versions(env)
    with pytest.raises(versions.PublishInProgress):  # 租约内仍占着课程
        run(env)
    expire(env, crashed.version_id)
    assert sweep_course(env.url, env.repo, env.course).expired == [crashed.version_id]
    assert graph_versions(env) == {"draft", first.version_id}
    assert_old_version_intact(env, first)
    retry = run(env)
    assert (retry.version, retry.unchanged) == (2, False)
    assert stage(env, "t3") == "completed"


def test_publish_reclaims_an_expired_attempt_without_waiting_for_the_sweeper(env, monkeypatch):
    first = published_v1_then_edit(env)
    crash_after(monkeypatch, publishing, "materialize")
    with pytest.raises(_Crash):
        run(env)
    monkeypatch.undo()
    crashed = last_attempt(env)
    expire(env, crashed.version_id)
    retry = run(env)  # 清扫尚未运行：发布自己先回收
    assert (retry.version, retry.unchanged) == (2, False)
    record = versions.get_version(env.url, crashed.version_id)
    assert (record.state, record.failure_reason) == ("failed", LEASE_EXPIRED)
    assert graph_versions(env) == {"draft", first.version_id, retry.version_id}


def test_copy_written_after_the_sweeper_failed_the_attempt_is_dropped(env, monkeypatch):
    first = published_v1_then_edit(env)
    real = publishing.materialize

    def swept_meanwhile(repo, snapshot, version_id, *args, **kwargs):
        assert versions.fail_attempt(env.url, version_id, LEASE_EXPIRED)  # 清扫已判失败并删过副本
        return real(repo, snapshot, version_id, *args, **kwargs)  # 本进程随后才写入副本

    monkeypatch.setattr(publishing, "materialize", swept_meanwhile)
    with pytest.raises(PublishFailed) as caught:
        run(env)
    assert caught.value.step == "P10"
    assert last_attempt(env).failure_reason == LEASE_EXPIRED
    assert graph_versions(env) == {"draft", first.version_id}  # 不留孤儿副本
    assert_old_version_intact(env, first)


# ---------------------------------------------------------------- PUB-20：提交与清扫竞争


def materialized_attempt(env, monkeypatch):
    first = published_v1_then_edit(env)
    crash_after(monkeypatch, versions, "mark_materialized")
    with pytest.raises(_Crash):
        run(env)
    monkeypatch.undo()
    attempt = last_attempt(env)
    assert attempt.state == "materialized"
    return first, attempt


def commit(env, attempt, first):
    with versions.immediate(env.url) as database:
        versions.commit_attempt(database, attempt.version_id, expected_pointer=first.version_id,
                                published_from_revision=attempt.draft_revision)
        versions.complete_published_tasks(database, env.course, attempt.task_watermark)


def test_sweeper_wins_once_the_lease_expired(env, monkeypatch):
    first, attempt = materialized_attempt(env, monkeypatch)
    expire(env, attempt.version_id)
    with pytest.raises(CommitRejected):  # P11 在租约过期后必然失败并整体回滚
        commit(env, attempt, first)
    assert sweep_course(env.url, env.repo, env.course).expired == [attempt.version_id]
    with pytest.raises(CommitRejected):
        commit(env, attempt, first)
    assert graph_versions(env) == {"draft", first.version_id}
    assert_old_version_intact(env, first)


def test_commit_wins_while_the_lease_holds_and_the_copy_survives(env, monkeypatch):
    first, attempt = materialized_attempt(env, monkeypatch)
    commit(env, attempt, first)
    expire_row = env.sql("SELECT expires_at < unixepoch() FROM graph_versions WHERE version_id = ?",
                         attempt.version_id)
    assert expire_row == [(0,)]
    report = sweep_course(env.url, env.repo, env.course)
    assert not report.changed and report.missing_copies == []
    assert not compensate(env.url, env.repo, env.course, attempt.version_id, "late C1")  # 0 行：不碰 Neo4j
    assert pointer(env)[:2] == (attempt.version_id, 2)
    assert counts(env, attempt.version_id) == (3, 2)
    assert stage(env, "t3") == "completed"


# ---------------------------------------------------------------- 不清仍被读的版本；告警项


def test_sweeper_only_removes_failed_copies(env, monkeypatch):
    base_graph(env)
    v1 = run(env)
    env.set_def("a", "二版")
    v2 = run(env)
    env.set_def("a", "三版")
    crash_after(monkeypatch, publishing, "materialize")
    with pytest.raises(_Crash):
        run(env)
    monkeypatch.undo()
    abandoned = last_attempt(env)
    versions.fail_attempt(env.url, abandoned.version_id, "C1 step 2 never ran")  # 第 3 步的情形
    # 另一个进行中的尝试（租约内），已写入部分副本。
    active = versions.begin_attempt(env.url, env.course, kind="publish", created_by=None, lease_seconds=60)
    env.q("CREATE (:KnowledgePoint {course_id: $c, version_id: $v, kp_id: 'x', name: 'x'})",
          c=env.course, v=active.version_id)

    report = sweep_course(env.url, env.repo, env.course)
    assert (report.dropped, report.expired, report.orphans) == ([abandoned.version_id], [], [])
    assert graph_versions(env) == {"draft", v1.version_id, v2.version_id, active.version_id}
    assert student_names(env, v1.version_id) == {"a", "b", "c"} == student_names(env, v2.version_id)
    assert versions.get_version(env.url, active.version_id).state == "preparing"
    assert not sweep_course(env.url, env.repo, env.course).changed


def test_orphans_and_missing_copies_are_only_reported(env, caplog):
    base_graph(env)
    v1 = run(env)
    env.q("CREATE (:KnowledgePoint {course_id: $c, version_id: 'ver-restored-elsewhere', kp_id: 'x', name: 'x'})",
          c=env.course)
    with caplog.at_level(logging.WARNING, logger=reconcile.__name__):
        report = sweep_course(env.url, env.repo, env.course)
    assert report.orphans == ["ver-restored-elsewhere"] and report.missing_copies == []
    assert "ver-restored-elsewhere" in graph_versions(env)  # 只告警，不删除

    env.q("MATCH (n {course_id: $c, version_id: $v}) DETACH DELETE n", c=env.course, v=v1.version_id)
    with caplog.at_level(logging.ERROR, logger=reconcile.__name__):
        report = sweep_course(env.url, env.repo, env.course)
    assert report.missing_copies == [v1.version_id]
    assert any(v1.version_id in r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    assert versions.get_version(env.url, v1.version_id).state == "committed" and pointer(env)[0] == v1.version_id


def test_sweep_isolates_courses(env, monkeypatch, caplog):
    base_graph(env)
    other = create_course(env.url, name="另一门课", description=None, creator_id=env.teacher.id).id
    stuck = versions.begin_attempt(env.url, env.course, kind="publish", created_by=None, lease_seconds=60)
    expire(env, stuck.version_id)
    real = reconcile.stored_version_ids

    def broken_for_other(repo, course_id):
        if course_id == other:
            raise RuntimeError("neo4j hiccup")
        return real(repo, course_id)

    monkeypatch.setattr(reconcile, "stored_version_ids", broken_for_other)
    with caplog.at_level(logging.ERROR, logger=reconcile.__name__):
        reports = sweep(env.url, env.repo)
    assert [r.course_id for r in reports] == [env.course]
    assert reports[0].expired == [stuck.version_id]
    assert any(other in r.getMessage() for r in caplog.records)
