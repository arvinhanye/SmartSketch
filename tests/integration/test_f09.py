"""F09：教师删除草稿知识点与关系清理（``app.services.graph.delete_node``；ADR-048）。

验收（``docs/atomic-tasks.json`` F09）：只清理同一版本（草稿）的边；已发布快照（SQLite 快照与 Neo4j 版本副本）
不变；不存在、跨课程、并发删除都有明确结果（404 / 409），不会误删、不会静默成功两次。

无服务器用例只检查输入校验。其余连真实 Neo4j 5.26 + 真实 SQLite，只在设置
``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行；每个用例用独立课程并只清理自己的数据。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from app.repositories import course_locks
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.graph_edit import DraftNodeStore
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_read import GraphReader
from app.repositories.graph_relations import derive_rel_id, source_pair
from app.repositories.neo4j import Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.services.access import AccessDenied
from app.services.graph.delete_node import DeletedNode, delete_node
from app.services.graph.edit_node import CourseBusy, EditContext, InvalidEdit, RevisionConflict
from app.services.graph.merge_nodes import merge_nodes

DONE = "t-done"
FAILED = "t-failed"
VERSION_ID = "01JAAAAAAAAAAAAAAAAAAAAAAA"  # 26 位，已提交的 v1
SNAPSHOT = '{"snapshot_format":1}'
DIGEST = "sha256:" + "a" * 64
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
SECRET = "f09-test-signing-key-0123456789abcdefghij"


class _Unreachable:
    def __getattr__(self, name):  # pragma: no cover - must not be reached
        raise AssertionError(f"store.{name} must not be reached")


@pytest.mark.parametrize("revision, reason", [(0, "greater_than_equal"), (-3, "greater_than_equal"),
                                              (True, "int_type"), ("1", "int_type")])
def test_invalid_expected_revision_is_rejected_before_any_lock_or_read(tmp_path, revision, reason):
    ctx = EditContext(f"sqlite:///{tmp_path / 'never.sqlite3'}", _Unreachable(), _Unreachable(), lock_seconds=30,
                      wait_seconds=0)
    with pytest.raises(InvalidEdit) as caught:
        delete_node(ctx, "c1", "kp-a", revision)
    assert caught.value.fields == [{"in": "query", "field": "expected_revision", "reason": reason}]


def test_blank_id_is_not_found_without_reading(tmp_path):
    ctx = EditContext(f"sqlite:///{tmp_path / 'never.sqlite3'}", _Unreachable(), _Unreachable(), lock_seconds=30,
                      wait_seconds=0)
    with pytest.raises(AccessDenied) as caught:
        delete_node(ctx, "c1", "  ")
    assert caught.value.status_code == 404


# --- 真实 Neo4j + SQLite ---------------------------------------------------------------------------

_LIVE = all(os.environ.get(name) for name in (
    "SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD"))
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


def _account(url, name, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def _task(url, course_id, task_id, stage):
    with connect(url) as db:
        if db.execute("SELECT 1 FROM materials WHERE id = ?", ("doc-" + course_id,)).fetchone() is None:
            db.execute("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
                       " VALUES (?, ?, 'a.txt', 'txt', 1, ?, ?)",
                       ("doc-" + course_id, course_id, "sha256:" + uuid.uuid4().hex * 2, "s-" + course_id))
        failed = stage == "failed"
        db.execute("INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key, stage, progress,"
                   " error_code, error_message) VALUES (?, ?, ?, ?, ?, 0.5, ?, ?)",
                   (task_id, course_id, "doc-" + course_id, task_id + course_id, stage,
                    "INTERNAL_ERROR" if failed else None, "失败" if failed else None))


class Graph:
    def __init__(self, q, course):
        self.q, self.course = q, course

    def node(self, kp_id, *, tasks=(DONE,), manual=False, revision=1, version="draft", merged_from=None):
        props = {"kp_id": kp_id, "name": kp_id.upper(), "aliases": [], "type": "concept",
                 "definition": f"{kp_id} 的定义", "confidence": 0.9, "status": "draft", "source": "ai",
                 "locked": False, "revision": revision, "contrib_tasks": list(tasks), "contrib_manual": manual,
                 "level": 0}
        if merged_from is not None:
            props["merged_from"] = list(merged_from)
        self.q("CREATE (n:KnowledgePoint {course_id: $c, version_id: $v}) SET n += $p", c=self.course, v=version,
               p=props)

    def edge(self, type, a, b, *, tasks=(DONE,), version="draft", chunks=()):
        rel_id = derive_rel_id(self.course, type, a, b)
        props = {"course_id": self.course, "version_id": version, "rel_id": rel_id, "confidence": 0.8,
                 "status": "draft", "source": "ai", "contrib_tasks": list(tasks), "contrib_manual": False,
                 "source_pairs": [source_pair(tasks[0] if tasks else None, c) for c in chunks], "revision": 1}
        self.q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $a}}), "
               f"(b:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $b}}) "
               f"CREATE (a)-[r:{type}]->(b) SET r = $p", c=self.course, v=version, a=a, b=b, p=props)
        if version == "draft":
            self.q("CREATE (:RelationIdentity {course_id: $c, version_id: 'draft', rel_id: $r, type: $t, "
                   "from_id: $a, to_id: $b})", c=self.course, r=rel_id, t=type, a=a, b=b)
        return rel_id

    def evidence(self, kp_id, chunk_id, *, task=DONE, version="draft"):
        props = {"chunk_id": chunk_id, "evidence_start": 0, "evidence_end": 5}
        if task is not None:
            props["task_id"] = task
        self.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k}) "
               "MERGE (ch:Chunk {course_id: $c, chunk_id: $ch}) ON CREATE SET ch.document_id = 'doc', "
               "ch.revision_id = 'rev' CREATE (n)-[e:EVIDENCED_BY]->(ch) SET e = $p",
               c=self.course, v=version, k=kp_id, ch=chunk_id, p=props)

    def props(self, kp_id, version="draft"):
        rows = self.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k}) RETURN properties(n) AS p",
                      c=self.course, v=version, k=kp_id)
        return rows[0]["p"] if rows else None

    def edges(self, version="draft"):
        rows = self.q("MATCH (a:KnowledgePoint {course_id: $c, version_id: $v})-[r]->"
                      "(b:KnowledgePoint {course_id: $c, version_id: $v}) RETURN type(r) AS t, a.kp_id AS a, "
                      "b.kp_id AS b ORDER BY t, a, b", c=self.course, v=version)
        return {(r["t"], r["a"], r["b"]) for r in rows}

    def identities(self):
        rows = self.q("MATCH (ri:RelationIdentity {course_id: $c}) RETURN ri.rel_id AS r, ri.version_id AS v",
                      c=self.course)
        return {(r["v"], r["r"]) for r in rows}

    def dump(self, version=None):
        where = "" if version is None else " AND n.version_id = $v"
        nodes = self.q(f"MATCH (n {{course_id: $c}}) WHERE NOT n:DraftWriteGuard{where} "
                       "RETURN labels(n) AS l, properties(n) AS p", c=self.course, v=version)
        rel_where = "" if version is None else " WHERE a.version_id = $v"
        rels = self.q(f"MATCH (a {{course_id: $c}})-[r]->(b {{course_id: $c}}){rel_where} RETURN type(r) AS t, "
                      "properties(r) AS p, coalesce(a.kp_id, a.chunk_id) AS a, coalesce(b.kp_id, b.chunk_id) AS b",
                      c=self.course, v=version)
        key = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)  # noqa: E731
        return sorted(map(key, nodes)), sorted(map(key, rels))


@pytest.fixture
def env(tmp_path):
    neo4j = pytest.importorskip("neo4j")
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    student = _account(url, "student1", "student")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    other = create_course(url, name="操作系统", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    _task(url, course.id, DONE, "completed")
    _task(url, course.id, FAILED, "failed")
    _task(url, other.id, DONE + "-o", "completed")
    driver = neo4j.GraphDatabase.driver(
        os.environ["SMARTSKETCH_TEST_NEO4J_URI"],
        auth=(os.environ["SMARTSKETCH_TEST_NEO4J_USER"], os.environ["SMARTSKETCH_TEST_NEO4J_PASSWORD"]))
    apply_migrations(driver)
    repo = Neo4jRepository(driver)

    def q(query, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    def ctx(wait_seconds=0.0):
        return EditContext(url, DraftNodeStore(repo), GraphReader(repo), lock_seconds=30, wait_seconds=wait_seconds)

    try:
        yield SimpleNamespace(url=url, course=course.id, other=other.id, ctx=ctx(), make_ctx=ctx, q=q,
                              g=Graph(q, course.id), og=Graph(q, other.id), teacher=teacher, student=student)
    finally:
        q("MATCH (n) WHERE n.course_id IN [$a, $b] DETACH DELETE n", a=course.id, b=other.id)
        driver.close()


def _draft_revision(env, course=None):
    with connect(env.url) as db:
        return db.execute("SELECT draft_revision FROM courses WHERE id = ?", (course or env.course,)).fetchone()[0]


def _publish_v1(env):
    """一个已提交的 v1：SQLite 版本行 + 发布指针（内容与 Neo4j 副本由用例另建）。"""
    with connect(env.url) as db:
        db.execute("INSERT INTO graph_versions (version_id, course_id, version, kind, state, expires_at, snapshot_json,"
                   " digest, committed_at, commit_seq) VALUES (?, ?, 1, 'publish', 'committed', 0, ?, ?,"
                   " '2026-09-26T00:00:00Z', 1)", (VERSION_ID, env.course, SNAPSHOT, DIGEST))
        db.execute("UPDATE courses SET published_version_id = ?, published_version = 1,"
                   " published_from_revision = draft_revision WHERE id = ?", (VERSION_ID, env.course))


def _published_state(env):
    with connect(env.url) as db:
        rows = db.execute("SELECT * FROM graph_versions WHERE course_id = ? ORDER BY version_id",
                          (env.course,)).fetchall()
        pointer = db.execute("SELECT published_version_id, published_version, published_from_revision FROM courses"
                             " WHERE id = ?", (env.course,)).fetchone()
    return [tuple(r) for r in rows], tuple(pointer)


# --- 删除与关系清理 --------------------------------------------------------------------------------


@live
def test_delete_removes_the_node_its_draft_edges_identities_and_evidence_only(env):
    g = env.g
    for kp in ("a", "x", "y", "z"):
        g.node(kp)
    g.node("ghost", tasks=(FAILED,))
    ax = g.edge("PREREQUISITE", "a", "x")
    ya = g.edge("RELATED_TO", "y", "a")
    ga = g.edge("EXAMPLE_OF", "ghost", "a", tasks=(FAILED,))  # 不可见的边同样清理
    xy = g.edge("PREREQUISITE", "x", "y")                     # 不相连：保留
    zy = g.edge("CONTAINS", "z", "y")
    g.evidence("a", "ch-1")
    g.evidence("a", "ch-2", task=None)
    g.evidence("x", "ch-1")
    before = _draft_revision(env)

    result = delete_node(env.ctx, env.course, "a")

    assert result == DeletedNode(kp_id="a", relations=3)
    assert g.props("a") is None
    assert g.edges() == {("PREREQUISITE", "x", "y"), ("CONTAINS", "z", "y")}
    assert g.identities() == {("draft", xy), ("draft", zy)}
    assert not {ax, ya, ga} & {r for _, r in g.identities()}
    chunks = env.q("MATCH (c:Chunk {course_id: $c}) RETURN c.chunk_id AS id ORDER BY id", c=env.course)
    assert [c["id"] for c in chunks] == ["ch-1", "ch-2"]  # 共享文本块不删
    assert env.q("MATCH (:KnowledgePoint {course_id: $c, kp_id: 'x'})-[e:EVIDENCED_BY]->() RETURN count(e) AS n",
                 c=env.course)[0]["n"] == 1
    assert g.props("ghost") is not None and g.props("x")["revision"] == 1
    assert _draft_revision(env) == before + 1
    assert course_locks.current_holder(env.url, env.course) is None


@live
def test_published_snapshot_and_version_copies_are_unchanged(env):
    g = env.g
    for kp in ("a", "x"):
        g.node(kp)
        g.node(kp, version=VERSION_ID, tasks=())
    g.edge("PREREQUISITE", "a", "x")
    rel_id = g.edge("PREREQUISITE", "a", "x", version=VERSION_ID)
    env.q("CREATE (:RelationIdentity {course_id: $c, version_id: $v, rel_id: $r, type: 'PREREQUISITE', "
          "from_id: 'a', to_id: 'x'})", c=env.course, v=VERSION_ID, r=rel_id)  # 同 ID 的他版本身份
    g.evidence("a", "ch-1")
    g.evidence("a", "ch-1", task=None, version=VERSION_ID)
    _publish_v1(env)
    published_graph, published_rows = g.dump(VERSION_ID), _published_state(env)

    delete_node(env.ctx, env.course, "a")

    assert g.dump(VERSION_ID) == published_graph
    assert g.props("a", VERSION_ID) is not None and g.edges(VERSION_ID) == {("PREREQUISITE", "a", "x")}
    assert _published_state(env) == published_rows
    assert g.props("a") is None and g.edges() == set()
    assert g.identities() == {(VERSION_ID, rel_id)}
    assert _draft_revision(env) > published_rows[1][2]  # 草稿已改：课程按 V7 为 revising


@live
def test_merged_from_is_dropped_with_the_node(env):
    g = env.g
    g.node("p", merged_from=["old-1", "old-2"])
    delete_node(env.ctx, env.course, "p")
    assert env.q("MATCH (n:KnowledgePoint {course_id: $c}) WHERE 'old-1' IN coalesce(n.merged_from, []) "
                 "RETURN count(n) AS n", c=env.course)[0]["n"] == 0


# --- 明确结果：不存在、跨课、不可见、冲突、并发 ------------------------------------------------------


@pytest.mark.parametrize("where", ["missing", "invisible", "other-course", "published-only"])
@live
def test_node_not_visible_in_this_course_draft_is_404_and_nothing_changes(env, where):
    g = env.g
    g.node("x")
    if where == "invisible":
        g.node("a", tasks=(FAILED,))
    elif where == "other-course":
        env.og.node("a", tasks=(DONE + "-o",))
    elif where == "published-only":
        g.node("a", version=VERSION_ID, tasks=())
    snapshot, other_snapshot, before = g.dump(), env.og.dump(), _draft_revision(env)

    with pytest.raises(AccessDenied) as caught:
        delete_node(env.ctx, env.course, "a")

    assert (caught.value.status_code, caught.value.code) == (404, "NOT_FOUND")
    assert g.dump() == snapshot and env.og.dump() == other_snapshot and _draft_revision(env) == before
    assert course_locks.current_holder(env.url, env.course) is None


@live
def test_stale_expected_revision_is_a_conflict_and_the_right_one_deletes(env):
    g = env.g
    g.node("a", revision=4)
    snapshot, before = g.dump(), _draft_revision(env)

    with pytest.raises(RevisionConflict) as caught:
        delete_node(env.ctx, env.course, "a", 3)

    details = caught.value.details()
    assert (details["kp_id"], details["expected_revision"], details["current_revision"]) == ("a", 3, 4)
    assert g.dump() == snapshot and _draft_revision(env) == before
    assert delete_node(env.ctx, env.course, "a", 4) == DeletedNode("a", 0)


@live
def test_course_lock_held_by_someone_else_is_busy_and_nothing_changes(env):
    env.g.node("a")
    snapshot = env.g.dump()
    lock = course_locks.acquire(env.url, env.course, holder="persisting", lease_seconds=30, wait_seconds=0)
    try:
        with pytest.raises(CourseBusy) as caught:
            delete_node(env.ctx, env.course, "a")
    finally:
        course_locks.release(env.url, lock)
    assert caught.value.holder == "persisting" and env.g.dump() == snapshot


def _race(*calls):
    barrier = threading.Barrier(len(calls))
    results: list[object] = [None] * len(calls)

    def run(i, call):
        barrier.wait()
        try:
            results[i] = call()
        except Exception as exc:  # noqa: BLE001 - the outcome is what is asserted
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return results


@live
def test_concurrent_deletes_of_the_same_node_succeed_exactly_once(env):
    g = env.g
    for kp in ("a", "x"):
        g.node(kp)
    g.edge("PREREQUISITE", "a", "x")
    before = _draft_revision(env)
    ctx = env.make_ctx(wait_seconds=10)

    results = _race(lambda: delete_node(ctx, env.course, "a"), lambda: delete_node(ctx, env.course, "a"))

    assert sum(isinstance(r, DeletedNode) for r in results) == 1
    [lost] = [r for r in results if not isinstance(r, DeletedNode)]
    assert isinstance(lost, AccessDenied) and lost.status_code == 404
    assert _draft_revision(env) == before + 1 and g.props("a") is None and g.edges() == set()


@live
def test_concurrent_delete_and_merge_of_the_same_node_have_one_consistent_outcome(env):
    g = env.g
    for kp in ("p", "a", "x"):
        g.node(kp)
    g.edge("PREREQUISITE", "x", "a")
    ctx = env.make_ctx(wait_seconds=10)

    deleted, merged = _race(lambda: delete_node(ctx, env.course, "a"),
                            lambda: merge_nodes(ctx, env.course, "p", ["a"]))

    assert g.props("a") is None
    if isinstance(deleted, DeletedNode):  # 删除先到：合并看不到 a
        assert isinstance(merged, InvalidEdit) and merged.fields[0]["reason"] == "not_found"
        assert g.edges() == set() and "merged_from" not in g.props("p")
    else:  # 合并先到：删除看不到 a
        assert isinstance(deleted, AccessDenied) and deleted.status_code == 404
        assert merged.id == "p" and g.edges() == {("PREREQUISITE", "x", "p")}


# --- API（真实存储） ------------------------------------------------------------------------------


@pytest.fixture
def api(env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.services.auth import issue_access_token

    monkeypatch.setenv("SQLITE_URL", env.url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("COURSE_LOCK_WAIT_SECONDS", "0")
    from app.main import create_app  # 模块导入时会校验签名密钥，须在设置环境变量之后

    application = create_app()
    application.state.graph_node_store = env.ctx.store
    application.state.graph_reader = env.ctx.reader

    def call(kid, query="", user=None, course=None):
        user = user or env.teacher
        token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                                   issued_at=int(time.time()), ttl_seconds=3600)
        return client.delete(f"/api/v1/courses/{course or env.course}/kp/{kid}{query}",
                             headers={"Authorization": f"Bearer {token}"})

    with TestClient(application) as client:
        yield call


@live
def test_api_delete_results(env, api):
    g = env.g
    g.node("a", revision=2)
    g.node("b")
    env.og.node("c", tasks=(DONE + "-o",))

    assert api("a", user=env.student).status_code == 403
    stale = api("a", "?expected_revision=1")
    assert stale.status_code == 409 and stale.json()["code"] == "REVISION_CONFLICT"
    assert stale.json()["details"]["current_revision"] == 2
    for query in ("?expected_revision=0", "?expected_revision=x"):
        invalid = api("a", query)
        assert invalid.status_code == 422 and invalid.json()["code"] == "VALIDATION_ERROR"

    ok = api("a", "?expected_revision=2")
    assert ok.status_code == 204 and ok.content == b""
    again = api("a")
    assert again.status_code == 404 and again.json()["code"] == "NOT_FOUND"
    assert api("c").status_code == 404  # 他课的知识点经本课路径
    assert api("b").status_code == 204
    assert env.og.props("c") is not None
