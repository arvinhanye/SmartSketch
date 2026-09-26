"""G07 统一发布版本解析器，连真实迁移后的 SQLite（specs/teacher-review-publish.md V8，PUB-13/14）。

验收：无发布版返回明确状态；请求开始时解析一次得到固定 ``version_id``，其后提交的新版本不混入；
图谱、推荐、问答用同一个解析结果（Neo4j 作用域、``graph_version``、修订列表）。
"""

from __future__ import annotations

import dataclasses
import sqlite3
import uuid

import pytest

from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.neo4j import GraphScope
from app.repositories.sqlite import connect, migrate
from app.services.access import AccessDenied
from app.services.versions import resolver
from app.services.versions.resolver import PublishedVersion, VersionIntegrityError, resolve_published
from app.services.versions.snapshot import DraftGraph, DraftNode, Revision, build_snapshot

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
LEASE = 60
EXCLUDED = {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0}


@pytest.fixture(autouse=True)
def fresh_cache():
    resolver.clear_cache()
    yield
    resolver.clear_cache()


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    other = create_course(url, name="B", description=None, creator_id=teacher.id)
    return url, teacher, course.id, other.id


def revision(tag):
    return Revision(f"rev-{tag}", f"mat-{tag}", "sha256:" + "a" * 64, "txt/1+chunk/1@1500-200")


def snapshot_for(course_id, *tags):
    revisions = [revision(t) for t in tags]
    node = DraftNode(kp_id="kp-1", name="栈", type="concept", definition="后进先出", status="approved",
                     source_refs=(f"ch-{tags[0]}",))
    draft = DraftGraph(course_id, revisions, [], [node], [], {f"ch-{t}": f"rev-{t}" for t in tags})
    return build_snapshot(draft).snapshot


def pointer_id(url, course_id):
    with connect(url) as db:
        return db.execute("SELECT published_version_id FROM courses WHERE id = ?", (course_id,)).fetchone()[0]


def publish(url, course_id, teacher, *tags, revision_no=1):
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    snap = snapshot_for(course_id, *tags)
    assert versions.record_snapshot(url, attempt.version_id, snapshot=snap.canonical, digest=snap.digest,
                                    node_count=1, edge_count=0, excluded=EXCLUDED, draft_revision=revision_no,
                                    task_watermark=0, embedding_space="bge-m3@1024")
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer_id(url, course_id),
                                       published_from_revision=revision_no)


def rollback(url, course_id, teacher, source_version):
    attempt = versions.begin_attempt(url, course_id, kind="rollback", created_by=teacher.id, lease_seconds=LEASE,
                                     source_version=source_version)
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer_id(url, course_id),
                                       published_from_revision=1)


def denied(call):
    with pytest.raises(AccessDenied) as caught:
        call()
    return caught.value.status_code, caught.value.code


def unfreeze(url, statement, *params):
    """模拟数据损坏：去掉已提交行的不可变触发器后改写（生产代码不会这样做）。"""
    with connect(url) as db:
        db.execute("DROP TRIGGER graph_versions_committed_frozen")
        db.execute(statement, params)


# --- 无发布版 ---------------------------------------------------------------------------------


def test_never_published_course_is_graph_not_published(env):
    url, _, course, _ = env
    assert denied(lambda: resolve_published(url, course)) == (404, "GRAPH_NOT_PUBLISHED")


def test_never_published_wins_over_an_explicit_version(env):
    url, _, course, _ = env
    assert denied(lambda: resolve_published(url, course, version=1)) == (404, "GRAPH_NOT_PUBLISHED")


def test_in_progress_or_failed_attempts_do_not_count_as_published(env):
    url, teacher, course, _ = env
    failed = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    assert versions.fail_attempt(url, failed.version_id, "validation")
    versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    assert denied(lambda: resolve_published(url, course)) == (404, "GRAPH_NOT_PUBLISHED")


def test_unknown_course_is_not_found(env):
    url, *_ = env
    assert denied(lambda: resolve_published(url, "no-such-course")) == (404, "NOT_FOUND")


# --- 解析结果 ---------------------------------------------------------------------------------


def test_resolves_the_pointer_to_a_fixed_version_with_its_revisions(env):
    url, teacher, course, _ = env
    v1 = publish(url, course, teacher, "a", "b")
    resolved = resolve_published(url, course)
    assert resolved == PublishedVersion(course_id=course, version_id=v1.version_id, version=1,
                                        revision_ids=frozenset({"rev-a", "rev-b"}))
    assert resolved.graph_version == 1


def test_result_is_immutable(env):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    resolved = resolve_published(url, course)
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.version_id = "other"  # type: ignore[misc]
    assert isinstance(resolved.revision_ids, frozenset)


def test_pub13_a_request_bound_to_v1_keeps_v1_after_v2_commits(env):
    url, teacher, course, _ = env
    v1 = publish(url, course, teacher, "a")
    bound = resolve_published(url, course)
    v2 = publish(url, course, teacher, "a", "c", revision_no=2)
    assert (bound.version_id, bound.version, bound.revision_ids) == (v1.version_id, 1, frozenset({"rev-a"}))
    assert bound.graph_scope() == GraphScope(course, v1.version_id)
    assert not bound.covers_revision("rev-c")
    fresh = resolve_published(url, course)
    assert (fresh.version_id, fresh.version, fresh.revision_ids) == (v2.version_id, 2,
                                                                     frozenset({"rev-a", "rev-c"}))


def test_rollback_resolves_to_the_new_version_with_the_source_revisions(env):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    publish(url, course, teacher, "b", revision_no=2)
    v3 = rollback(url, course, teacher, source_version=1)
    resolved = resolve_published(url, course)
    assert (resolved.version_id, resolved.version, resolved.revision_ids) == (v3.version_id, 3,
                                                                              frozenset({"rev-a"}))


def test_courses_are_isolated(env):
    url, teacher, course, other = env
    publish(url, course, teacher, "a")
    assert denied(lambda: resolve_published(url, other)) == (404, "GRAPH_NOT_PUBLISHED")
    theirs = publish(url, other, teacher, "z")
    assert resolve_published(url, other).version_id == theirs.version_id
    assert resolve_published(url, course).revision_ids == frozenset({"rev-a"})


# --- ?version=n（PUB-14） ---------------------------------------------------------------------


def test_pub14_explicit_committed_version_is_readable_while_pointer_is_elsewhere(env):
    url, teacher, course, _ = env
    v1 = publish(url, course, teacher, "a")
    v2 = publish(url, course, teacher, "b", revision_no=2)
    assert resolve_published(url, course, version=1) == PublishedVersion(course, v1.version_id, 1,
                                                                         frozenset({"rev-a"}))
    assert resolve_published(url, course, version=2).version_id == v2.version_id
    assert resolve_published(url, course).version_id == v2.version_id


@pytest.mark.parametrize("number", [99, 0, -1, 3])
def test_pub14_missing_version_numbers_are_not_found(env, number):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    publish(url, course, teacher, "b", revision_no=2)
    assert denied(lambda: resolve_published(url, course, version=number)) == (404, "NOT_FOUND")


def test_another_courses_version_number_is_not_readable(env):
    url, teacher, course, other = env
    publish(url, course, teacher, "a")
    publish(url, other, teacher, "z")
    publish(url, other, teacher, "y", revision_no=2)
    assert denied(lambda: resolve_published(url, course, version=2)) == (404, "NOT_FOUND")
    assert resolve_published(url, course, version=1).revision_ids == frozenset({"rev-a"})


@pytest.mark.parametrize("bad", [True, 1.0, "1", None.__class__])
def test_version_must_be_an_int(env, bad):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    with pytest.raises(TypeError):
        resolve_published(url, course, version=bad)  # type: ignore[arg-type]


# --- 复用：图谱 / 推荐 / 问答 -------------------------------------------------------------------


def test_one_result_serves_graph_path_and_qa(env):
    url, teacher, course, _ = env
    v1 = publish(url, course, teacher, "a", "b")
    bound = resolve_published(url, course)
    # 图谱与推荐：Neo4j 读版本副本，不带 V（副本已是发布集合）
    scope = bound.graph_scope()
    assert (scope.course_id, scope.version_id, scope.effective_task_ids) == (course, v1.version_id, None)
    # 问答：文本块只保留修订属于该版本的；不按 material_id
    chunks = [("c1", "rev-a"), ("c2", "rev-new"), ("c3", "rev-b")]
    assert [c for c, rev in chunks if bound.covers_revision(rev)] == ["c1", "c3"]
    # 响应带回 graph_version
    assert bound.graph_version == 1


def test_revision_list_is_cached_per_committed_version(env, monkeypatch):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    calls = []
    real = resolver.load_snapshot
    monkeypatch.setattr(resolver, "load_snapshot", lambda raw: calls.append(1) or real(raw))
    first = resolve_published(url, course)
    second = resolve_published(url, course)
    assert first == second and len(calls) == 1
    publish(url, course, teacher, "b", revision_no=2)
    assert resolve_published(url, course).revision_ids == frozenset({"rev-b"})
    assert len(calls) == 2


def test_the_pointer_is_re_read_on_every_call_even_when_cached(env):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    resolve_published(url, course)
    v2 = publish(url, course, teacher, "b", revision_no=2)
    assert resolve_published(url, course).version_id == v2.version_id


# --- 完整性：已提交版本损坏时报错，不回退到草稿或别的版本（V9 第 5 条） ----------------------------


def test_pointer_to_a_non_committed_row_is_an_integrity_error(env):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    pending = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    with connect(url) as db:
        db.execute("UPDATE courses SET published_version_id = ? WHERE id = ?", (pending.version_id, course))
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)


def test_pointer_to_another_courses_version_is_an_integrity_error(env):
    url, teacher, course, other = env
    publish(url, course, teacher, "a")
    theirs = publish(url, other, teacher, "z")
    with connect(url) as db:
        db.execute("UPDATE courses SET published_version_id = ? WHERE id = ?", (theirs.version_id, course))
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)


def test_pointer_to_another_courses_cached_version_is_still_an_integrity_error(env):
    """修订列表缓存只按 version_id；课程归属必须在读缓存前按版本行判断。"""
    url, teacher, course, other = env
    publish(url, course, teacher, "a")
    theirs = publish(url, other, teacher, "z")
    resolve_published(url, other)
    with connect(url) as db:
        db.execute("UPDATE courses SET published_version_id = ? WHERE id = ?", (theirs.version_id, course))
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)


def test_pointer_number_disagreeing_with_the_row_is_an_integrity_error(env):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    with connect(url) as db:
        db.execute("UPDATE courses SET published_version = 7 WHERE id = ?", (course,))
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)


@pytest.mark.parametrize("corrupt", [
    ("UPDATE graph_versions SET snapshot_json = '{}' || snapshot_json WHERE course_id = ?", "unparseable"),
    ("UPDATE graph_versions SET digest = 'sha256:' || printf('%064d', 0) WHERE course_id = ?", "digest"),
])
def test_corrupt_snapshot_is_an_integrity_error(env, corrupt):
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    unfreeze(url, corrupt[0], course)
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)


def test_snapshot_of_another_course_is_an_integrity_error(env):
    url, teacher, course, other = env
    publish(url, course, teacher, "a")
    snap = snapshot_for(other, "a")
    unfreeze(url, "UPDATE graph_versions SET snapshot_json = ?, digest = ? WHERE course_id = ?",
             snap.canonical.decode(), snap.digest, course)
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)


def test_integrity_errors_are_not_cached(env):
    url, teacher, course, _ = env
    v1 = publish(url, course, teacher, "a")
    with connect(url) as db:
        good = db.execute("SELECT snapshot_json FROM graph_versions WHERE version_id = ?",
                          (v1.version_id,)).fetchone()[0]
    unfreeze(url, "UPDATE graph_versions SET snapshot_json = 'x' || snapshot_json WHERE course_id = ?", course)
    with pytest.raises(VersionIntegrityError):
        resolve_published(url, course)
    with connect(url) as db:
        db.execute("UPDATE graph_versions SET snapshot_json = ? WHERE version_id = ?", (good, v1.version_id))
    assert resolve_published(url, course).version_id == v1.version_id


def test_integrity_error_is_a_public_internal_error_without_details():
    error = VersionIntegrityError("snapshot digest mismatch for version 01ABC")
    assert error.code == "INTERNAL_ERROR"
    assert issubclass(VersionIntegrityError, RuntimeError)


def test_committed_rows_are_actually_frozen_in_the_schema(env):
    """前提：完整性用例需先去触发器，证明正常路径下已提交行无法被改写。"""
    url, teacher, course, _ = env
    publish(url, course, teacher, "a")
    with pytest.raises(sqlite3.IntegrityError):
        with connect(url) as db:
            db.execute("UPDATE graph_versions SET snapshot_json = 'x' WHERE course_id = ?", (course,))
