"""F10：教师合并重复知识点与重接边（``app.services.graph.merge_nodes``；ADR-047）。

验收（``docs/atomic-tasks.json`` F10）：迁移入边与出边后去重并验环；课程写锁被占、修订号冲突、成环或写入
中途失败时不部分提交；来源不丢。

无服务器用例只检查输入校验（不取锁、不碰数据库）。其余连真实 Neo4j 5.26 + 真实 SQLite，只在设置
``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行；每个用例用独立课程并只清理自己的数据。
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
import yaml

from app.repositories import course_locks
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.graph_edit import DraftNodeStore
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_read import GraphReader
from app.repositories.graph_relations import derive_rel_id, source_pair
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.services.graph.edit_node import CourseBusy, EditContext, InvalidEdit, RevisionConflict
from app.services.graph.merge_nodes import merge_nodes
from app.services.graph.relations import CycleDetectedError

ROOT = Path(__file__).resolve().parents[2]
DONE = "t-done"      # 在 V 中
FAILED = "t-failed"  # 不在 V 中（失败任务留下、待清理的贡献）
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
SECRET = "f10-test-signing-key-0123456789abcdefghij"

_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {k: (v.replace("#/components/schemas/", "#/$defs/") if k == "$ref" and isinstance(v, str)
                    else _rewrite(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite(i) for i in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def assert_schema(name, instance):
    jsonschema.Draft202012Validator({"$defs": _DEFS, "$ref": f"#/$defs/{name}"}).validate(instance)


class _Unreachable:
    """任何存储访问都算失败：输入校验必须在取锁、读库之前完成。"""

    def __getattr__(self, name):  # pragma: no cover - must not be reached
        raise AssertionError(f"store.{name} must not be reached")


def _offline_ctx(tmp_path):
    return EditContext(f"sqlite:///{tmp_path / 'never-created.sqlite3'}", _Unreachable(), _Unreachable(),
                       lock_seconds=30, wait_seconds=0)


# --- 无服务器：输入校验 ----------------------------------------------------------------------------


@pytest.mark.parametrize("primary, merged, expected, field, reason", [
    ("a", [], None, "merged_ids", "too_short"),
    ("a", ["a", "b"], None, "merged_ids.0", "contains_primary"),
    ("a", ["b", "b"], None, "merged_ids.1", "duplicate"),
    ("  ", ["b"], None, "primary_id", "blank"),
    ("a", ["b", " "], None, "merged_ids.1", "blank"),
    ("a", ["b"], {"z": 1}, "expected_revisions.z", "not_in_merge"),
    ("a", ["b"], {"a": 0}, "expected_revisions.a", "greater_than_equal"),
    ("a", ["b"], {"b": True}, "expected_revisions.b", "int_type"),
])
def test_invalid_input_is_rejected_before_any_lock_or_read(tmp_path, primary, merged, expected, field, reason):
    with pytest.raises(InvalidEdit) as caught:
        merge_nodes(_offline_ctx(tmp_path), "c1", primary, merged, expected)
    assert {"in": "body", "field": field, "reason": reason} in caught.value.fields


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
    """一门课程的草稿种子数据与观察方法（直接写 Cypher，属性与 F04/F06/F08 写入的一致）。"""

    def __init__(self, q, course):
        self.q, self.course = q, course

    def node(self, kp_id, *, name=None, tasks=(DONE,), manual=False, revision=1, aliases=(), merged_from=None,
             locked=False, status="draft", version="draft", source="ai"):
        props = {"kp_id": kp_id, "name": name or kp_id.upper(), "aliases": list(aliases), "type": "concept",
                 "definition": f"{kp_id} 的定义", "confidence": 0.9, "status": status, "source": source,
                 "locked": locked, "revision": revision, "contrib_tasks": list(tasks), "contrib_manual": manual,
                 "level": 0}
        if merged_from is not None:
            props["merged_from"] = list(merged_from)
        self.q("CREATE (n:KnowledgePoint {course_id: $c, version_id: $v}) SET n += $p", c=self.course, v=version,
               p=props)

    def edge(self, type, a, b, *, tasks=(DONE,), manual=False, status="draft", confidence=0.8, chunks=(),
             source="ai", revision=1, version="draft", rel_id=None, extra=None):
        rel_id = rel_id or derive_rel_id(self.course, type, a, b)
        contributor = None if manual and not tasks else (tasks[0] if tasks else None)
        props = {"course_id": self.course, "version_id": version, "rel_id": rel_id, "confidence": confidence,
                 "status": status, "source": source, "contrib_tasks": list(tasks), "contrib_manual": manual,
                 "source_pairs": [source_pair(contributor, c) for c in chunks], "revision": revision,
                 **(extra or {})}
        self.q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $a}}), "
               f"(b:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $b}}) "
               f"CREATE (a)-[r:{type}]->(b) SET r = $p", c=self.course, v=version, a=a, b=b, p=props)
        if version == "draft":
            self.q("CREATE (:RelationIdentity {course_id: $c, version_id: 'draft', rel_id: $r, type: $t, "
                   "from_id: $a, to_id: $b})", c=self.course, r=rel_id, t=type, a=a, b=b)
        return rel_id

    def evidence(self, kp_id, chunk_id, *, task=DONE, start=0, end=5, version="draft"):
        props = {"chunk_id": chunk_id, "evidence_start": start, "evidence_end": end}
        if task is not None:
            props["task_id"] = task
        self.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k}) "
               "MERGE (ch:Chunk {course_id: $c, chunk_id: $ch}) ON CREATE SET ch.document_id = 'doc', "
               "ch.revision_id = 'rev' CREATE (n)-[e:EVIDENCED_BY]->(ch) SET e = $p",
               c=self.course, v=version, k=kp_id, ch=chunk_id, p=props)

    # --- observation
    def props(self, kp_id, version="draft"):
        rows = self.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k}) RETURN properties(n) AS p",
                      c=self.course, v=version, k=kp_id)
        return rows[0]["p"] if rows else None

    def edges(self, version="draft"):
        rows = self.q("MATCH (a:KnowledgePoint {course_id: $c, version_id: $v})-[r]->"
                      "(b:KnowledgePoint {course_id: $c, version_id: $v}) "
                      "RETURN type(r) AS t, a.kp_id AS a, b.kp_id AS b, properties(r) AS p ORDER BY t, a, b",
                      c=self.course, v=version)
        return {(r["t"], r["a"], r["b"]): r["p"] for r in rows}

    def identities(self):
        rows = self.q("MATCH (ri:RelationIdentity {course_id: $c, version_id: 'draft'}) RETURN properties(ri) AS p",
                      c=self.course)
        return {r["p"]["rel_id"]: (r["p"]["type"], r["p"]["from_id"], r["p"]["to_id"]) for r in rows}

    def evidence_of(self, kp_id, version="draft"):
        rows = self.q("MATCH (:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k})-[e:EVIDENCED_BY]->(ch:Chunk) "
                      "RETURN ch.chunk_id AS chunk, e.task_id AS task, e.evidence_start AS s, e.evidence_end AS e",
                      c=self.course, v=version, k=kp_id)
        return sorted((r["chunk"], r["task"], r["s"], r["e"]) for r in rows)

    def dump(self):
        """整门课的全部节点与关系（含版本副本、守卫以外的一切），用于「什么都没变」的断言。"""
        nodes = self.q("MATCH (n {course_id: $c}) WHERE NOT n:DraftWriteGuard "
                       "RETURN labels(n) AS l, properties(n) AS p", c=self.course)
        rels = self.q("MATCH (a {course_id: $c})-[r]->(b {course_id: $c}) RETURN type(r) AS t, properties(r) AS p, "
                      "coalesce(a.kp_id, a.chunk_id) AS a, coalesce(b.kp_id, b.chunk_id) AS b", c=self.course)
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

    ctx = EditContext(url, DraftNodeStore(repo), GraphReader(repo), lock_seconds=30, wait_seconds=0)
    try:
        yield SimpleNamespace(url=url, course=course.id, other=other.id, ctx=ctx, repo=repo, q=q, g=Graph(q, course.id),
                              og=Graph(q, other.id), teacher=teacher, student=student)
    finally:
        q("MATCH (n) WHERE n.course_id IN [$a, $b] DETACH DELETE n", a=course.id, b=other.id)
        driver.close()


def _draft_revision(env):
    with connect(env.url) as db:
        return db.execute("SELECT draft_revision FROM courses WHERE id = ?", (env.course,)).fetchone()[0]


# --- 重接边、去重与节点字段 --------------------------------------------------------------------------


@live
def test_merge_rewires_incoming_and_outgoing_edges_and_updates_the_primary(env):
    g = env.g
    g.node("p", name="栈", aliases=["stack"])
    g.node("a", name="堆栈", aliases=["Stack", "LIFO 表"], merged_from=["old"])
    g.node("x")
    g.node("y")
    g.edge("PREREQUISITE", "x", "a", chunks=("ch-1",))   # 入边
    g.edge("EXAMPLE_OF", "a", "y", chunks=("ch-2",))     # 出边
    before = _draft_revision(env)

    kp = merge_nodes(env.ctx, env.course, "p", ["a"])

    body = kp.model_dump(mode="json", exclude_none=True)
    assert_schema("KnowledgePoint", body)
    assert body["id"] == "p" and body["name"] == "栈" and body["locked"] is True and body["revision"] == 2
    assert body["aliases"] == ["stack", "堆栈", "Stack", "LIFO 表"]
    assert g.props("a") is None
    p = g.props("p")
    assert p["merged_from"] == ["a", "old"] and p["contrib_manual"] is True and p["locked"] is True
    edges = g.edges()
    assert set(edges) == {("PREREQUISITE", "x", "p"), ("EXAMPLE_OF", "p", "y")}
    moved = edges[("PREREQUISITE", "x", "p")]
    assert moved["rel_id"] == derive_rel_id(env.course, "PREREQUISITE", "x", "p")
    assert moved["contrib_tasks"] == [DONE] and moved["source_pairs"] == [source_pair(DONE, "ch-1")]
    assert moved["revision"] == 2 and moved["contrib_manual"] is False and moved["status"] == "draft"
    assert g.identities() == {
        derive_rel_id(env.course, "PREREQUISITE", "x", "p"): ("PREREQUISITE", "x", "p"),
        derive_rel_id(env.course, "EXAMPLE_OF", "p", "y"): ("EXAMPLE_OF", "p", "y"),
    }
    assert _draft_revision(env) == before + 1
    assert course_locks.current_holder(env.url, env.course) is None


@live
def test_duplicate_edges_are_collapsed_keeping_the_primary_fields_and_all_contributions(env):
    g = env.g
    for kp in ("p", "a", "b", "x", "y"):
        g.node(kp)
    g.edge("RELATED_TO", "p", "x", status="draft", confidence=0.6, chunks=("ch-p",), manual=True, tasks=())
    g.edge("RELATED_TO", "a", "x", status="approved", confidence=0.95, chunks=("ch-a",), revision=3)
    g.edge("PREREQUISITE", "a", "y", status="draft", confidence=0.7, chunks=("ch-1",))
    g.edge("PREREQUISITE", "b", "y", status="approved", confidence=0.5, chunks=("ch-2",), tasks=(FAILED, DONE))
    g.edge("RELATED_TO", "p", "a")        # 合并后成自环：丢弃
    g.edge("EXAMPLE_OF", "a", "b")        # 两端都被合并：丢弃

    merge_nodes(env.ctx, env.course, "p", ["a", "b"])

    edges = g.edges()
    assert set(edges) == {("RELATED_TO", "p", "x"), ("PREREQUISITE", "p", "y")}
    px = edges[("RELATED_TO", "p", "x")]  # 主节点原有的边胜出：字段不变，贡献与来源取并集
    assert (px["status"], px["confidence"], px["contrib_manual"]) == ("draft", 0.6, True)
    assert px["contrib_tasks"] == [DONE] and px["revision"] == 4
    assert sorted(px["source_pairs"]) == sorted([source_pair(None, "ch-p"), source_pair(DONE, "ch-a")])
    py = edges[("PREREQUISITE", "p", "y")]  # 仅由迁移而来：状态优先级 approved 胜出
    assert (py["status"], py["confidence"]) == ("approved", 0.5)
    assert sorted(py["contrib_tasks"]) == sorted([DONE, FAILED])
    assert sorted(py["source_pairs"]) == sorted([source_pair(DONE, "ch-1"), source_pair(FAILED, "ch-2")])
    assert set(g.identities()) == {derive_rel_id(env.course, "RELATED_TO", "p", "x"),
                                   derive_rel_id(env.course, "PREREQUISITE", "p", "y")}
    assert g.props("p")["merged_from"] == ["a", "b"]


@live
def test_invisible_edges_move_with_their_contributions_and_stay_invisible(env):
    g = env.g
    for kp in ("p", "a", "x"):
        g.node(kp)
    g.node("ghost", tasks=(FAILED,))
    g.edge("RELATED_TO", "a", "x", tasks=(FAILED,), chunks=("ch-f",))
    g.edge("PREREQUISITE", "ghost", "a", tasks=(FAILED,))

    merge_nodes(env.ctx, env.course, "p", ["a"])

    edges = g.edges()
    assert set(edges) == {("RELATED_TO", "p", "x"), ("PREREQUISITE", "ghost", "p")}
    assert edges[("RELATED_TO", "p", "x")]["contrib_tasks"] == [FAILED]
    assert edges[("RELATED_TO", "p", "x")]["contrib_manual"] is False
    scope_edges = GraphReader(env.repo).edges(_scope(env), "teacher")
    assert scope_edges == []  # 仍不可见，待失败任务清理时撤销


@live
def test_downgraded_relation_keeps_the_prerequisite_derived_id_convention(env):
    g = env.g
    for kp in ("p", "a", "x"):
        g.node(kp)
    g.edge("RELATED_TO", "a", "x", status="low_confidence", rel_id=derive_rel_id(env.course, "PREREQUISITE", "a", "x"),
           extra={"downgraded_from_type": "PREREQUISITE", "downgrade_cycle": ["a", "x", "a"]})

    merge_nodes(env.ctx, env.course, "p", ["a"])

    moved = g.edges()[("RELATED_TO", "p", "x")]
    assert moved["rel_id"] == derive_rel_id(env.course, "PREREQUISITE", "p", "x")
    assert moved["downgraded_from_type"] == "PREREQUISITE" and moved["status"] == "low_confidence"
    assert g.identities() == {moved["rel_id"]: ("RELATED_TO", "p", "x")}


def _scope(env):
    return GraphScope(env.course, "draft", (DONE,))


# --- 来源不丢 --------------------------------------------------------------------------------------


@live
def test_every_source_of_the_merged_nodes_ends_up_on_the_primary(env):
    g = env.g
    for kp in ("p", "a", "b"):
        g.node(kp)
    g.evidence("p", "ch-1", start=0, end=5)
    g.evidence("a", "ch-1", start=0, end=5)                # 与主节点完全相同：去重
    g.evidence("a", "ch-2", start=1, end=4)
    g.evidence("a", "ch-3", task=None, start=0, end=9)     # 人工来源（无 task_id）
    g.evidence("b", "ch-4", task=FAILED, start=2, end=3)   # 不可见任务的来源：保留原 task_id
    g.evidence("b", "ch-2", task=DONE, start=1, end=4)     # 两个被合并节点共有：去重

    merge_nodes(env.ctx, env.course, "p", ["a", "b"])

    assert g.evidence_of("p") == [("ch-1", DONE, 0, 5), ("ch-2", DONE, 1, 4), ("ch-3", None, 0, 9),
                                  ("ch-4", FAILED, 2, 3)]
    visible = GraphReader(env.repo).evidence(_scope(env), "teacher", ["p"])
    assert sorted((e.chunk_id, e.evidence_start) for e in visible) == [("ch-1", 0), ("ch-2", 1), ("ch-3", 0)]
    chunks = env.q("MATCH (c:Chunk {course_id: $c}) RETURN count(c) AS n", c=env.course)[0]["n"]
    assert chunks == 4  # 共享文本块一个不删


@live
def test_published_copies_are_untouched(env):
    g = env.g
    for kp in ("p", "a", "x"):
        g.node(kp)
        g.node(kp, version="ver-1", tasks=())
    g.edge("PREREQUISITE", "x", "a")
    g.edge("PREREQUISITE", "x", "a", version="ver-1")
    g.evidence("a", "ch-1", version="ver-1", task=None)
    published = (g.props("a", "ver-1"), g.edges("ver-1"), g.evidence_of("a", "ver-1"))

    merge_nodes(env.ctx, env.course, "p", ["a"])

    assert (g.props("a", "ver-1"), g.edges("ver-1"), g.evidence_of("a", "ver-1")) == published
    assert set(g.edges()) == {("PREREQUISITE", "x", "p")}


# --- 验环 ----------------------------------------------------------------------------------------


@live
def test_merge_that_would_close_a_prerequisite_cycle_is_rejected_without_any_change(env):
    g = env.g
    for kp in ("p", "b", "c"):
        g.node(kp)
    g.edge("PREREQUISITE", "p", "b")
    g.edge("PREREQUISITE", "b", "c")
    snapshot, before = g.dump(), _draft_revision(env)

    with pytest.raises(CycleDetectedError) as caught:
        merge_nodes(env.ctx, env.course, "p", ["c"])

    assert caught.value.cycle == ("b", "p", "b")
    assert g.dump() == snapshot and _draft_revision(env) == before
    assert course_locks.current_holder(env.url, env.course) is None


@live
def test_rejected_and_invisible_prerequisites_do_not_block_the_merge(env):
    g = env.g
    for kp in ("p", "b", "c", "d"):
        g.node(kp)
    g.edge("PREREQUISITE", "p", "b")
    g.edge("PREREQUISITE", "b", "c", status="rejected")
    g.edge("PREREQUISITE", "p", "d")
    g.edge("PREREQUISITE", "d", "c", tasks=(FAILED,))

    merge_nodes(env.ctx, env.course, "p", ["c"])

    assert set(g.edges()) == {("PREREQUISITE", "p", "b"), ("PREREQUISITE", "b", "p"), ("PREREQUISITE", "p", "d"),
                              ("PREREQUISITE", "d", "p")}


@live
def test_existing_cycle_in_the_draft_blocks_the_merge(env):
    g = env.g
    for kp in ("p", "a", "x", "y"):
        g.node(kp)
    g.edge("PREREQUISITE", "x", "y")
    g.edge("PREREQUISITE", "y", "x")  # 草稿不变量已被破坏
    snapshot = g.dump()
    with pytest.raises(CycleDetectedError) as caught:
        merge_nodes(env.ctx, env.course, "p", ["a"])
    assert caught.value.edge is None and g.dump() == snapshot


# --- 锁、冲突与原子性 --------------------------------------------------------------------------------


@live
def test_course_lock_held_by_someone_else_changes_nothing(env):
    g = env.g
    for kp in ("p", "a"):
        g.node(kp)
    snapshot, before = g.dump(), _draft_revision(env)
    lock = course_locks.acquire(env.url, env.course, holder="publish", lease_seconds=30, wait_seconds=0)
    try:
        with pytest.raises(CourseBusy) as caught:
            merge_nodes(env.ctx, env.course, "p", ["a"])
    finally:
        course_locks.release(env.url, lock)
    assert caught.value.holder == "publish"
    assert g.dump() == snapshot and _draft_revision(env) == before


@live
def test_stale_expected_revision_is_a_conflict_and_nothing_is_written(env):
    g = env.g
    g.node("p", revision=3)
    g.node("a", revision=2)
    g.edge("RELATED_TO", "a", "p")
    snapshot, before = g.dump(), _draft_revision(env)

    with pytest.raises(RevisionConflict) as caught:
        merge_nodes(env.ctx, env.course, "p", ["a"], {"p": 3, "a": 1})

    details = caught.value.details()
    assert details["kp_id"] == "a" and details["expected_revision"] == 1 and details["current_revision"] == 2
    assert g.dump() == snapshot and _draft_revision(env) == before

    merge_nodes(env.ctx, env.course, "p", ["a"], {"p": 3, "a": 2})
    assert g.props("p")["revision"] == 4 and g.props("a") is None


@pytest.mark.parametrize("where", ["missing", "invisible", "other-course"])
@live
def test_unknown_or_invisible_nodes_are_not_found_and_nothing_changes(env, where):
    g = env.g
    g.node("p")
    if where == "invisible":
        g.node("a", tasks=(FAILED,))
    elif where == "other-course":
        env.og.node("a", tasks=(DONE + "-o",))
    snapshot, before = g.dump(), _draft_revision(env)

    with pytest.raises(InvalidEdit) as caught:
        merge_nodes(env.ctx, env.course, "p", ["a"])

    assert caught.value.fields == [{"in": "body", "field": "merged_ids.0", "reason": "not_found"}]
    assert g.dump() == snapshot and _draft_revision(env) == before
    if where == "other-course":
        assert env.og.props("a") is not None


@live
def test_failure_in_the_middle_of_the_write_rolls_back_every_statement(env, monkeypatch):
    import app.repositories.graph_edit as graph_edit

    g = env.g
    for kp in ("p", "a", "x"):
        g.node(kp)
    g.edge("PREREQUISITE", "x", "a")
    g.evidence("a", "ch-1")
    snapshot = g.dump()
    real = graph_edit.delete_merged_nodes

    def boom(tx, kp_ids):
        real(tx, kp_ids)  # 前面的语句（主节点、来源、关系）都已在事务里执行
        raise RuntimeError("injected failure after the last statement")

    monkeypatch.setattr(graph_edit, "delete_merged_nodes", boom)
    with pytest.raises(RuntimeError):
        merge_nodes(env.ctx, env.course, "p", ["a"])

    assert g.dump() == snapshot
    assert course_locks.current_holder(env.url, env.course) is None


@live
def test_locked_nodes_can_be_merged_by_the_teacher(env):
    g = env.g
    g.node("p", locked=True, manual=True, tasks=(), source="manual")
    g.node("a", locked=True)
    merged = merge_nodes(env.ctx, env.course, "p", ["a"])
    assert merged.locked is True and g.props("a") is None


@live
def test_merged_from_stays_flat_across_chained_merges(env):
    g = env.g
    for kp in ("a", "b", "c"):
        g.node(kp)
    merge_nodes(env.ctx, env.course, "b", ["a"])
    merge_nodes(env.ctx, env.course, "c", ["b"])
    assert g.props("c")["merged_from"] == ["a", "b"]
    assert g.props("a") is None and g.props("b") is None


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

    def call(body, user=None):
        user = user or env.teacher
        token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                                   issued_at=int(time.time()), ttl_seconds=3600)
        return client.post(f"/api/v1/courses/{env.course}/kp/merge", json=body,
                           headers={"Authorization": f"Bearer {token}"})

    with TestClient(application) as client:
        yield call


@live
def test_api_merge_returns_the_primary(env, api):
    env.g.node("p")
    env.g.node("a", name="甲")
    response = api({"primary_id": "p", "merged_ids": ["a"], "expected_revisions": {"a": 1}})
    assert response.status_code == 200, response.text
    assert_schema("KnowledgePoint", response.json())
    assert response.json()["aliases"] == ["甲"]


@live
def test_api_merge_reports_cycle_conflict_and_validation(env, api):
    g = env.g
    for kp in ("p", "b", "c"):
        g.node(kp)
    g.edge("PREREQUISITE", "p", "b")
    g.edge("PREREQUISITE", "b", "c")

    cycle = api({"primary_id": "p", "merged_ids": ["c"]})
    assert cycle.status_code == 409 and cycle.json()["code"] == "CYCLE_DETECTED"
    assert_schema("Error", cycle.json())
    assert cycle.json()["details"]["cycle"] == ["b", "p", "b"]

    stale = api({"primary_id": "p", "merged_ids": ["b"], "expected_revisions": {"b": 7}})
    assert stale.status_code == 409 and stale.json()["code"] == "REVISION_CONFLICT"

    for body in ({"primary_id": "p", "merged_ids": ["p"]}, {"primary_id": "p", "merged_ids": []},
                 {"primary_id": "p", "merged_ids": ["zz"]}, {"primary_id": "p", "merged_ids": ["b"], "x": 1},
                 {"primary_id": "p", "merged_ids": ["b"], "expected_revisions": {"b": 0}}):
        invalid = api(body)
        assert invalid.status_code == 422, body
        assert invalid.json()["code"] == "VALIDATION_ERROR"

    assert api({"primary_id": "p", "merged_ids": ["b"]}, user=env.student).status_code == 403
    assert set(g.edges()) == {("PREREQUISITE", "p", "b"), ("PREREQUISITE", "b", "c")}
