"""G04 against a real Neo4j and a migrated SQLite: atomic publish and the pointer switch.

Acceptance: validate DAG and sources before switching the pointer; any failed step keeps the old
pointer; concurrent publishes conflict (specs/teacher-review-publish.md V5, PUB-1/2/4/5/6/12/21/22/23/35).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.repositories import course_locks, versions
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course, get_course
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_read import GraphReader
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient
from app.services.versions import publish as publishing
from app.services.versions import reconcile
from app.services.versions.materialize import VerificationError
from app.services.versions.publish import (
    CourseBusy,
    PublishContext,
    PublishFailed,
    PublishInProgress,
    SnapshotBlocked,
    publish,
)

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
live = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV), reason="isolated Neo4j fixture not configured")
pytestmark = live

SPACE = "fake/4"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
REV = "rev_" + "a" * 64
OTHER_REV = "rev_" + "b" * 64
C0, C1 = f"{REV}-0", f"{REV}-1"


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def embedder():
    return EmbeddingAdapter(Settings(EMBEDDING_MODE="fake", EMBEDDING_MODEL="", EMBEDDING_DIMENSIONS=4,
                                     EMBEDDING_BATCH_SIZE=8), FakeEmbeddingClient())


def _sql(url, query, *params):
    with connect(url) as db:
        return db.execute(query, params).fetchall()


@pytest.fixture
def env(tmp_path):
    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id).id

    def sql(query, *params):
        return _sql(url, query, *params)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    sql("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
        "VALUES ('m1', ?, 'a.txt', 'txt', 10, ?, ?)", course, sha("m1"), uuid.uuid4().hex)
    sql("INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
        "VALUES (?, ?, 'm1', ?, 'txt/1+chunk/1')", REV, course, sha("m1"))
    for ordinal in (0, 1):
        sql("INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256, "
            "section_titles, sources) VALUES (?, ?, ?, 'm1', ?, ?, ?, '[]', ?)",
            f"{REV}-{ordinal}", REV, course, ordinal, f"块{ordinal}", sha(f"块{ordinal}"),
            json.dumps([{"block_ordinal": 0, "start": 0, "end": 2, "locator": {"section_titles": [], "paragraph": 1}}]))

    def task(task_id, stage, t6_seq=None, *, revision=REV):
        failed = stage == "failed"
        sql("INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, t6_seq, "
            "error_code, error_message) VALUES (?, ?, 'm1', ?, ?, ?, ?, ?, ?)",
            task_id, course, stage, 0.95 if stage == "awaiting_review" else 0.5, task_id, t6_seq,
            "INTERNAL_ERROR" if failed else None, "失败" if failed else None)
        sql("INSERT INTO task_revisions (task_id, revision_id, course_id, material_id) VALUES (?, ?, ?, 'm1')",
            task_id, revision, course)
        if t6_seq is not None:
            sql("UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", course)

    def node(kp_id, status="approved", *, tasks=("t1",), manual=False, definition="定义", chunk=C0):
        q("CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k, name: $k, type: 'concept', "
          "definition: $d, status: $s, source: 'ai', confidence: 0.9, locked: false, revision: 1, "
          "contrib_manual: $m, contrib_tasks: $t})",
          c=course, k=kp_id, d=definition, s=status, m=manual, t=list(tasks))
        if chunk is not None:
            evidence(kp_id, chunk, tasks[0] if tasks else None)

    def evidence(kp_id, chunk_id, task_id):
        q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k}) "
          "MERGE (ch:Chunk {course_id: $c, chunk_id: $chunk}) ON CREATE SET ch.document_id = 'm1' "
          "CREATE (n)-[e:EVIDENCED_BY {chunk_id: $chunk, evidence_start: 0, evidence_end: 2}]->(ch) "
          "SET e.task_id = $t", c=course, k=kp_id, chunk=chunk_id, t=task_id)

    def rel(kind, a, b, status="approved", *, tasks=("t1",), chunk=C1):
        pairs = [] if chunk is None else [json.dumps([tasks[0] if tasks else None, chunk])]
        q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: 'draft', kp_id: $a}}), "
          f"(b:KnowledgePoint {{course_id: $c, version_id: 'draft', kp_id: $b}}) "
          f"CREATE (a)-[r:{kind}]->(b) SET r += $p",
          c=course, a=a, b=b,
          p={"course_id": course, "version_id": "draft", "rel_id": f"rel_{kind}_{a}_{b}", "status": status,
             "source": "ai", "confidence": 0.8, "contrib_tasks": list(tasks), "contrib_manual": False,
             "source_pairs": pairs, "revision": 1})

    def set_def(kp_id, definition):
        q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k}) SET n.definition = $d",
          c=course, k=kp_id, d=definition)
        sql("UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", course)

    repo = Neo4jRepository(driver)
    ctx = PublishContext(url, repo, embedder(), lambda: SPACE, lease_seconds=15, lock_wait_seconds=0)
    try:
        yield SimpleNamespace(url=url, course=course, teacher=teacher, sql=sql, q=q, task=task, node=node,
                              rel=rel, evidence=evidence, set_def=set_def, repo=repo, ctx=ctx)
    finally:
        q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)
        driver.close()


def base_graph(env):
    """t1 已到 awaiting_review（T6 序号 1）；草稿 3 个 approved 知识点、2 条边。"""
    env.task("t1", "awaiting_review", 1)
    for kp in ("a", "b", "c"):
        env.node(kp)
    env.rel("PREREQUISITE", "a", "b")
    env.rel("RELATED_TO", "b", "c")


def run(env, **overrides):
    ctx = env.ctx if not overrides else PublishContext(**{**env.ctx.__dict__, **overrides})
    return publish(ctx, env.course, created_by=env.teacher.id)


def pointer(env):
    return env.sql("SELECT published_version_id, published_version, published_from_revision, draft_revision "
                   "FROM courses WHERE id = ?", env.course)[0]


def status(env):
    course = get_course(env.url, env.course)
    if course.published_version_id is None:
        return "draft"
    return "published" if course.draft_revision == course.published_from_revision else "revising"


def stage(env, task_id):
    return env.sql("SELECT stage FROM processing_tasks WHERE id = ?", task_id)[0][0]


def graph_versions(env):
    rows = env.q("MATCH (n {course_id: $c}) WHERE n:KnowledgePoint OR n:Chapter "
                 "RETURN DISTINCT n.version_id AS v", c=env.course)
    return {r["v"] for r in rows}


def counts(env, version_id):
    [row] = env.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v}) WITH count(n) AS nodes "
                  "OPTIONAL MATCH ()-[r {course_id: $c, version_id: $v}]->() RETURN nodes, count(r) AS rels",
                  c=env.course, v=version_id)
    return row["nodes"], row["rels"]


def student_names(env, version_id):
    return {p["name"] for p in GraphReader(env.repo).nodes(GraphScope(env.course, version_id), "student")}


def last_attempt(env):
    return versions.list_attempts(env.url, env.course)[-1]


# ---------------------------------------------------------------- 成功路径


def test_first_publish_switches_the_pointer_and_completes_tasks(env):  # PUB-1, PUB-4
    base_graph(env)
    env.task("t2", "persisting")
    assert status(env) == "draft"
    outcome = run(env)
    assert (outcome.version, outcome.unchanged, outcome.node_count, outcome.edge_count) == (1, False, 3, 2)
    assert outcome.excluded == {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0}
    assert pointer(env)[:3] == (outcome.version_id, 1, 1)
    assert status(env) == "published"
    assert counts(env, outcome.version_id) == (3, 2)
    assert student_names(env, outcome.version_id) == {"a", "b", "c"}
    assert (stage(env, "t1"), stage(env, "t2")) == ("completed", "persisting")
    record = versions.get_version(env.url, outcome.version_id)
    assert (record.state, record.task_watermark, record.draft_revision, record.embedding_space) == (
        "committed", 1, 1, SPACE)
    assert record.committed_at == outcome.published_at


def test_edits_after_the_lock_is_released_miss_this_snapshot(env, monkeypatch):  # PUB-4, PUB-22
    base_graph(env)
    env.task("t2", "persisting")
    real = publishing.materialize
    seen = {}

    def during_p8(*args, **kwargs):
        # P5 之后：写锁已释放，编辑与新的 T6 可以立即进行。
        lock = course_locks.try_acquire(env.url, env.course, holder="persisting", lease_seconds=15)
        seen["lock_free"] = lock is not None
        env.node("late", tasks=("t2",))
        env.sql("UPDATE processing_tasks SET stage = 'awaiting_review', progress = 0.95, t6_seq = 2 WHERE id = 't2'")
        env.sql("UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", env.course)
        course_locks.release(env.url, lock)
        return real(*args, **kwargs)

    monkeypatch.setattr(publishing, "materialize", during_p8)
    outcome = run(env)
    assert seen["lock_free"]
    assert student_names(env, outcome.version_id) == {"a", "b", "c"}
    assert (stage(env, "t1"), stage(env, "t2")) == ("completed", "awaiting_review")  # t2 在水位之外
    assert versions.get_version(env.url, outcome.version_id).task_watermark == 1
    assert status(env) == "revising"


def test_republish_after_an_edit_creates_version_two_and_keeps_version_one(env):  # PUB-2
    base_graph(env)
    first = run(env)
    env.set_def("a", "改过的定义")
    assert status(env) == "revising"
    [row] = env.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: 'a'}) RETURN n.definition AS d",
                  c=env.course, v=first.version_id)
    assert row["d"] == "定义"  # 学生仍读 v1
    second = run(env)
    assert (second.version, second.unchanged) == (2, False)
    assert pointer(env)[:2] == (second.version_id, 2)
    assert status(env) == "published"
    assert [v.version for v in versions.list_versions(env.url, env.course)] == [2, 1]
    assert counts(env, first.version_id) == (3, 2) and counts(env, second.version_id) == (3, 2)


@pytest.mark.parametrize("change", ["approve", "touch"])
def test_unchanged_content_takes_the_idempotent_path(env, change):  # PUB-5, PUB-6
    base_graph(env)
    env.node("d", status="draft")
    first = run(env)
    env.task("t3", "awaiting_review", 2)  # 只让状态变 revising，不改内容
    if change == "approve":
        env.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'd'}) SET n.status = 'approved'",
              c=env.course)
    assert status(env) == "revising"
    again = run(env)
    assert (again.version, again.version_id, again.unchanged) == (1, first.version_id, True)
    assert again.published_at == first.published_at
    assert len(versions.list_attempts(env.url, env.course)) == 1  # 尝试行已删除，不占号
    assert graph_versions(env) == {"draft", first.version_id}
    assert status(env) == "published"
    assert stage(env, "t3") == "completed"


# ---------------------------------------------------------------- 阻断与失败：旧指针保留


def test_cycle_blocks_before_the_pointer_moves(env):  # PUB-23
    base_graph(env)
    first = run(env)
    env.rel("PREREQUISITE", "b", "c")
    env.rel("PREREQUISITE", "c", "a")
    env.task("t3", "awaiting_review", 2)
    with pytest.raises(SnapshotBlocked) as caught:
        run(env)
    [reason] = [r for r in caught.value.reasons if r.kind == "cycle"]
    assert reason.cycle[0] == reason.cycle[-1] and set(reason.cycle) == {"a", "b", "c"}
    assert pointer(env)[0] == first.version_id
    attempt = last_attempt(env)
    assert (attempt.state, attempt.failure_reason, attempt.version) == ("failed", "PUBLISH_BLOCKED", None)
    assert graph_versions(env) == {"draft", first.version_id}
    assert stage(env, "t3") == "awaiting_review"  # 发布失败不改任务状态


def test_empty_graph_and_foreign_sources_are_blocked(env):  # PUB-24 via G04
    env.task("t1", "awaiting_review", 1)
    with pytest.raises(SnapshotBlocked) as caught:
        run(env)
    assert [r.kind for r in caught.value.reasons] == ["empty_graph"]
    env.node("a", chunk=f"{OTHER_REV}-0")  # 块不在本课程 SQLite 中
    with pytest.raises(SnapshotBlocked) as caught:
        run(env)
    assert [(r.kind, r.chunk_id) for r in caught.value.reasons] == [("invalid_source_ref", f"{OTHER_REV}-0")]
    assert pointer(env)[0] is None
    assert all(a.state == "failed" for a in versions.list_attempts(env.url, env.course))


def test_invisible_contributions_stay_out_of_the_snapshot(env):  # PUB-35
    base_graph(env)
    env.task("tf", "failed")
    env.task("tr", "extracting")
    env.node("ghost", tasks=("tf",))
    env.node("running", tasks=("tr",))
    env.evidence("a", C1, "tf")  # 共享节点上来自失败任务的来源
    env.rel("RELATED_TO", "a", "c", tasks=("tf",))
    outcome = run(env)
    data = json.loads(versions.read_snapshot(env.url, outcome.version_id))
    assert [n["kp_id"] for n in data["nodes"]] == ["a", "b", "c"]
    assert {n["kp_id"]: n["source_refs"] for n in data["nodes"]}["a"] == [C0]
    assert [e["rel_id"] for e in data["edges"]] == ["rel_PREREQUISITE_a_b", "rel_RELATED_TO_b_c"]
    assert [r["revision_id"] for r in data["revisions"]] == [REV]


def _explode_after(real):
    def wrapped(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("injected")
    return wrapped


@pytest.mark.parametrize("where", ["P8", "P9", "P10", "P11"])
def test_failures_keep_the_old_pointer_and_leave_no_copy(env, monkeypatch, where):  # PUB-12, PUB-18 (G04 part)
    base_graph(env)
    first = run(env)
    env.set_def("a", "新定义")
    env.task("t3", "awaiting_review", 2)
    if where == "P8":
        monkeypatch.setattr(publishing, "materialize", _explode_after(publishing.materialize))
    elif where == "P9":
        def bad_verify(*args, **kwargs):
            raise VerificationError("injected drift")
        monkeypatch.setattr(publishing, "verify", bad_verify)
    elif where == "P10":
        monkeypatch.setattr(versions, "mark_materialized", lambda *a, **k: False)
    else:  # T7 与提交同一事务：T7 失败则提交整体回滚
        def bad_t7(*args, **kwargs):
            raise RuntimeError("injected T7 failure")
        monkeypatch.setattr(versions, "complete_published_tasks", bad_t7)
    with pytest.raises(PublishFailed) as caught:
        run(env)
    assert caught.value.step == where
    assert pointer(env)[:2] == (first.version_id, 1)
    attempt = last_attempt(env)
    assert (attempt.state, attempt.version, attempt.cleanup_pending) == ("failed", None, False)
    assert attempt.failure_reason.startswith(where)
    assert graph_versions(env) == {"draft", first.version_id}
    assert student_names(env, first.version_id) == {"a", "b", "c"}
    assert stage(env, "t3") == "awaiting_review"
    monkeypatch.undo()
    retry = run(env)
    assert (retry.version, retry.unchanged) == (2, False)  # 版本号无空洞
    assert stage(env, "t3") == "completed"


def test_commit_refuses_a_moved_pointer(env, monkeypatch):  # P11 CAS
    base_graph(env)
    first = run(env)
    env.set_def("a", "新定义")
    real = publishing.verify

    def move_pointer(*args, **kwargs):
        real(*args, **kwargs)
        env.sql("UPDATE courses SET published_version_id = NULL, published_version = NULL WHERE id = ?", env.course)

    monkeypatch.setattr(publishing, "verify", move_pointer)
    with pytest.raises(PublishFailed) as caught:
        run(env)
    assert caught.value.step == "P11"
    assert last_attempt(env).state == "failed"
    assert [v.version for v in versions.list_versions(env.url, env.course)] == [1]
    assert graph_versions(env) == {"draft", first.version_id}


def test_error_after_the_commit_point_never_drops_the_committed_copy(env, monkeypatch):  # C1 step 1
    base_graph(env)
    real = versions.immediate
    calls = []

    @contextmanager
    def commit_then_raise(url):
        with real(url) as database:
            yield database
        if not calls and versions.list_versions(env.url, env.course):  # 只在 P11 提交之后注入
            calls.append(url)
            raise RuntimeError("connection lost after COMMIT")

    monkeypatch.setattr(versions, "immediate", commit_then_raise)
    with pytest.raises(PublishFailed):
        run(env)
    [committed] = versions.list_versions(env.url, env.course)
    assert (committed.state, committed.version) == ("committed", 1)
    assert pointer(env)[0] == committed.version_id
    assert counts(env, committed.version_id) == (3, 2)  # 已提交的副本未被 C1 删除


def test_undeletable_copy_is_marked_for_the_sweeper(env, monkeypatch):  # C1 step 3
    base_graph(env)
    monkeypatch.setattr(publishing, "verify", lambda *a, **k: (_ for _ in ()).throw(VerificationError("x")))

    def no_drop(*args, **kwargs):
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(reconcile, "drop_version", no_drop)
    with pytest.raises(PublishFailed):
        run(env)
    attempt = last_attempt(env)
    assert (attempt.state, attempt.cleanup_pending) == ("failed", True)
    assert pointer(env)[0] is None


def test_digest_equal_but_space_changed_is_an_invariant_breach(env):  # V5 P7, V12
    base_graph(env)
    first = run(env)
    env.sql("UPDATE graph_versions SET embedding_space = 'fake/8' WHERE version_id = ?", first.version_id)
    with pytest.raises(PublishFailed) as caught:
        run(env)
    assert caught.value.step == "P7"
    assert pointer(env)[0] == first.version_id
    assert last_attempt(env).state == "failed"
    assert graph_versions(env) == {"draft", first.version_id}


# ---------------------------------------------------------------- 并发


class _GatedEmbedder:
    def __init__(self, inner):
        self.inner, self.space = inner, inner.space
        self.entered, self.release = threading.Event(), threading.Event()

    def embed(self, texts):
        self.entered.set()
        assert self.release.wait(10)
        return self.inner.embed(texts)


def test_concurrent_publishes_conflict(env):  # PUB-21
    base_graph(env)
    gated = _GatedEmbedder(embedder())
    result = {}

    def first():
        try:
            result["a"] = run(env, embedder=gated)
        except Exception as error:  # pragma: no cover - surfaced by the assertion below
            result["a"] = error

    worker = threading.Thread(target=first)
    worker.start()
    try:
        assert gated.entered.wait(10)
        before = len(versions.list_attempts(env.url, env.course))
        with pytest.raises(PublishInProgress):
            run(env)
        assert len(versions.list_attempts(env.url, env.course)) == before  # 冲突方不留行
    finally:
        gated.release.set()
        worker.join(10)
    assert result["a"].version == 1 and pointer(env)[1] == 1

    versions.begin_attempt(env.url, env.course, kind="rollback", created_by=env.teacher.id, lease_seconds=15,
                           source_version=1)
    with pytest.raises(PublishInProgress):  # 发布与回滚同样互斥
        run(env)


def test_course_busy_names_the_holder_and_keeps_nothing(env):  # PUB-22 (publish side)
    base_graph(env)
    lock = course_locks.try_acquire(env.url, env.course, holder="persisting", lease_seconds=15)
    try:
        with pytest.raises(CourseBusy) as caught:
            run(env)
    finally:
        course_locks.release(env.url, lock)
    assert caught.value.details() == {"holder": "persisting"}
    attempt = last_attempt(env)
    assert (attempt.state, attempt.failure_reason) == ("failed", "COURSE_BUSY")
    assert pointer(env)[0] is None and stage(env, "t1") == "awaiting_review"
    assert run(env).version == 1


def test_heartbeat_extends_the_attempt_lease(env):
    attempt = versions.begin_attempt(env.url, env.course, kind="publish", created_by=None, lease_seconds=3)
    ctx = PublishContext(**{**env.ctx.__dict__, "lease_seconds": 3})
    with publishing._heartbeat(ctx, attempt.version_id):
        threading.Event().wait(2.2)
    assert versions.get_version(env.url, attempt.version_id).expires_at > attempt.expires_at
