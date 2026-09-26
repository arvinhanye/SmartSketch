"""G06 against a real Neo4j and a migrated SQLite: rollback rolls a past version forward.

Acceptance: missing or foreign versions are refused; rolling back to the current content is
idempotent; history is kept (specs/teacher-review-publish.md V6, PUB-3/7/15/16/25/26).
"""

from __future__ import annotations

import pytest

from app.repositories import course_locks, versions
from app.repositories.courses import create_course
from app.repositories.graph_migrations import vector_property
from app.repositories.versions import VersionNotFound
from app.services.versions.publish import PublishContext, PublishFailed, PublishInProgress
from app.services.versions.rollback import rollback
from test_g04 import SPACE, base_graph, counts, embedder, env, graph_versions, live, pointer, run, stage, status

pytestmark = live
__all__ = ["env"]  # 夹具取自 test_g04


class SpyEmbedder:
    def __init__(self):
        self.inner = embedder()
        self.space = self.inner.space
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return self.inner.embed(texts)


def ctx(env, **overrides):
    return PublishContext(**{**env.ctx.__dict__, **overrides})


def roll(env, version, **overrides):
    return rollback(ctx(env, **overrides), env.course, version, created_by=env.teacher.id)


def definition(env, version_id, kp_id="a"):
    [row] = env.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k}) RETURN n.definition AS d",
                  c=env.course, v=version_id, k=kp_id)
    return row["d"]


def five_versions(env):
    base_graph(env)
    published = [run(env)]
    for n in range(2, 6):
        env.set_def("a", f"第{n}版")
        published.append(run(env))
    return published


def test_rollback_rolls_forward_as_a_new_version(env):  # PUB-3
    published = five_versions(env)
    spy = SpyEmbedder()
    outcome = roll(env, 3, embedder=spy)
    assert (outcome.version, outcome.unchanged, outcome.node_count, outcome.edge_count) == (6, False, 3, 2)
    assert spy.calls == 0  # 向量随副本复制，不调用模型
    record = versions.get_version(env.url, outcome.version_id)
    source = versions.get_version(env.url, published[2].version_id)
    assert (record.kind, record.source_version, record.digest) == ("rollback", 3, source.digest)
    assert pointer(env)[:2] == (outcome.version_id, 6)
    assert definition(env, outcome.version_id) == "第3版"
    assert counts(env, outcome.version_id) == (3, 2)
    [row] = env.q(f"MATCH (n:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: 'a'}}) "
                  f"RETURN size(n.{vector_property(SPACE)}) AS dims", c=env.course, v=outcome.version_id)
    assert row["dims"] == 4
    assert [v.version for v in versions.list_versions(env.url, env.course)] == [6, 5, 4, 3, 2, 1]
    for old in published:  # v1～v5 不变
        assert old.version_id in graph_versions(env)
    assert definition(env, published[4].version_id) == "第5版"


def test_rollback_to_current_or_identical_content_is_idempotent(env):  # PUB-7
    base_graph(env)
    v1 = run(env)
    env.set_def("a", "改")
    v2 = run(env)
    env.set_def("a", "定义")  # 草稿内容回到 v1
    v3 = run(env)
    for target in (3, 1):  # 当前版本；与当前摘要相同的旧版本
        outcome = roll(env, target)
        assert (outcome.version, outcome.version_id, outcome.unchanged) == (3, v3.version_id, True)
    assert len(versions.list_attempts(env.url, env.course)) == 3
    assert graph_versions(env) == {"draft", v1.version_id, v2.version_id, v3.version_id}


def test_rollback_never_touches_the_draft_and_derives_status(env):  # PUB-15
    base_graph(env)
    run(env)
    env.set_def("a", "二版")
    run(env)
    env.set_def("a", "草稿里的三版")  # 未发布的修改
    outcome = roll(env, 1)
    assert outcome.version == 3
    [row] = env.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'a'}) RETURN n.definition AS d",
                  c=env.course)
    assert row["d"] == "草稿里的三版"
    assert status(env) == "revising" and pointer(env)[2] == -1

    env.set_def("a", "二版")
    run(env)  # v4 = 二版
    env.set_def("a", "定义")  # 草稿改回与 v1 相同
    back = roll(env, 1)
    assert back.version == 5 and status(env) == "published"
    assert pointer(env)[2] == pointer(env)[3]


def test_lock_timeout_in_r6_still_rolls_back_then_publish_corrects(env):  # PUB-16
    base_graph(env)
    run(env)
    env.set_def("a", "二版")
    run(env)
    env.set_def("a", "定义")  # 草稿与 v1 相同
    lock = course_locks.try_acquire(env.url, env.course, holder="edit", lease_seconds=30)
    try:
        outcome = roll(env, 1)
    finally:
        course_locks.release(env.url, lock)
    assert outcome.version == 3 and status(env) == "revising"  # d 未知
    again = run(env)
    assert (again.version, again.unchanged) == (3, True)
    assert status(env) == "published"


def test_rollback_does_not_complete_tasks(env):  # A03 §3：回滚不执行 T7
    base_graph(env)
    run(env)
    env.set_def("a", "二版")
    run(env)
    env.task("t9", "awaiting_review", 2)
    roll(env, 1)
    assert stage(env, "t9") == "awaiting_review"


def test_missing_failed_or_foreign_versions_are_not_found(env):  # PUB-25
    base_graph(env)
    run(env)
    other = create_course(env.url, name="他课", description=None, creator_id=env.teacher.id).id
    attempt = versions.begin_attempt(env.url, env.course, kind="publish", created_by=None, lease_seconds=60)
    versions.fail_attempt(env.url, attempt.version_id, "x")
    before = versions.list_attempts(env.url, env.course)
    for target in (2, 99):
        with pytest.raises(VersionNotFound):
            roll(env, target)
    with pytest.raises(VersionNotFound):
        rollback(env.ctx, other, 1, created_by=env.teacher.id)
    assert versions.list_attempts(env.url, env.course) == before


@pytest.mark.parametrize("problem", ["missing_copy", "foreign_space"])
def test_broken_source_fails_without_re_embedding(env, problem):  # PUB-26, V12
    base_graph(env)
    v1 = run(env)
    env.set_def("a", "二版")
    v2 = run(env)
    if problem == "missing_copy":
        env.q("MATCH (n {course_id: $c, version_id: $v}) DETACH DELETE n", c=env.course, v=v1.version_id)
    else:
        env.sql("UPDATE graph_versions SET embedding_space = 'fake/8' WHERE version_id = ?", v1.version_id)
    spy = SpyEmbedder()
    with pytest.raises(PublishFailed) as caught:
        roll(env, 1, embedder=spy)
    assert caught.value.step == "R5" and spy.calls == 0
    assert pointer(env)[:2] == (v2.version_id, 2)
    failed = versions.list_attempts(env.url, env.course)[-1]
    assert (failed.kind, failed.state) == ("rollback", "failed")
    assert failed.version_id not in graph_versions(env)


def test_rollback_and_publish_exclude_each_other(env):
    base_graph(env)
    run(env)
    env.set_def("a", "二版")
    run(env)
    versions.begin_attempt(env.url, env.course, kind="publish", created_by=None, lease_seconds=60)
    with pytest.raises(PublishInProgress):
        roll(env, 1)
