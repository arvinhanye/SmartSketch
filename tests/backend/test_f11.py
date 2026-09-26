"""F11：审核队列与单项处理（``app.services.graph.review``、``app.api.review``；ADR-060）。

验收（``docs/atomic-tasks.json`` F11）：低置信度 / 疑似重复 / 孤立三类分类正确；通过、拒绝、合并后队列相应
变化；分页稳定。

分类、游标与分页是纯函数，无服务器即可运行；单项处理与接口连真实 Neo4j 5.26 + 真实 SQLite，只在设置
``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行，每个用例用独立课程并只清理自己的数据。
"""

from __future__ import annotations

import copy
import json
import os
import random
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest
import yaml

from app.repositories import course_locks
from app.repositories.sqlite import connect, migrate
from app.services.graph.review import (
    InvalidCursor,
    classify,
    decode_cursor,
    encode_cursor,
    isolated_key,
    page,
    relation_key,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "src/backend/migrations"
DONE = "t-done"
FAILED = "t-failed"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
SECRET = "f11-test-signing-key-0123456789abcdefghij"

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


# --- 纯函数：分类 -----------------------------------------------------------------------------------


def n(kp_id, name=None, status="draft", aliases=(), **extra):
    return {"kp_id": kp_id, "name": name or kp_id, "type": "concept", "status": status, "aliases": list(aliases),
            **extra}


def e(a, b, status="draft", confidence=0.8, type="PREREQUISITE", rel_id=None):
    return {"type": type, "from_id": a, "to_id": b,
            "p": {"rel_id": rel_id or f"r-{a}-{b}", "status": status, "confidence": confidence}}


def ids(nodes):
    return [p["kp_id"] for p in nodes]


def pairs(c):
    return [(d.left["kp_id"], d.right["kp_id"], d.reason, d.similarity) for d in c.duplicates]


def test_low_confidence_relations_are_listed_by_confidence_then_id():
    nodes = [n("a"), n("b"), n("c"), n("x", status="rejected")]
    edges = [e("a", "b", "low_confidence", 0.5, rel_id="r2"), e("b", "c", "low_confidence", 0.3, rel_id="r9"),
             e("a", "c", "low_confidence", 0.5, rel_id="r1"), e("c", "a", "approved", 0.1, rel_id="r0"),
             e("a", "x", "low_confidence", 0.1, rel_id="r-x"),            # 端点已拒绝：发布时连带排除，不列
             e("b", "a", "low_confidence", 0.4, type="RELATED_TO", rel_id="r-d")]  # 降级而来的关系照列
    c = classify(nodes, edges)
    assert [r["p"]["rel_id"] for r in c.relations] == ["r9", "r-d", "r1", "r2"]


def test_suspected_duplicates_use_name_normalization_and_stored_aliases():
    nodes = [
        n("k1", "二叉 树"), n("k2", "二叉树"),                   # same_key（空白归一）
        n("k3", "栈", aliases=["Stack"]), n("k4", "stack"),     # 已存别名 → alias
        n("k5", "快速排序"), n("k6", "快速排序算法"),             # containment，有效字符比 4/6
        n("k7", "图"), n("k8", "图灵机"),                         # 单字不参与包含
        n("k9", "队列（Queue）"), n("k10", "queue"),             # 名称中的括号别名 → alias
        n("k11", "二叉树", status="rejected"),                    # 已拒绝不参与
    ]
    c = classify(nodes, [])
    assert pairs(c) == [
        ("k1", "k2", "same_key", 1.0),
        ("k10", "k9", "alias", 1.0),
        ("k3", "k4", "alias", 1.0),
        ("k5", "k6", "containment", pytest.approx(4 / 6)),
    ]


def test_containment_upgrades_to_alias_when_stored_aliases_match():
    c = classify([n("a", "快速排序", aliases=["快排"]), n("b", "快速排序算法", aliases=["快排"])], [])
    assert pairs(c) == [("a", "b", "alias", 1.0)]


def test_isolated_nodes_have_no_edge_that_would_be_published():
    nodes = [n("a", "甲"), n("b", "乙"), n("c", "丙"), n("d", "丁"), n("r", "戊", status="rejected"),
             n("e", "己"), n("f", "庚")]
    edges = [e("a", "b"),                       # a、b 相连
             e("c", "d", status="rejected"),    # 被拒绝的边不算
             e("e", "r"),                       # 另一端已拒绝，发布时连带排除，也不算
             e("f", "a", status="low_confidence")]  # 低置信度的边仍算相连
    c = classify(nodes, edges)
    assert ids(c.isolated) == ["d", "c", "e"]  # 按名称（码点序）再按 ID；已拒绝的 r 不列


def test_dismissals_remove_items_and_totals_follow():
    nodes = [n("a", "栈"), n("b", "栈"), n("c", "队列")]
    before = classify(nodes, [])
    assert before.totals() == {"low_confidence_relations": 0, "suspected_duplicates": 1, "isolated_nodes": 3}
    after = classify(nodes, [], dismissed_pairs=[("b", "a")], dismissed_isolated=["c"])
    assert after.totals() == {"low_confidence_relations": 0, "suspected_duplicates": 0, "isolated_nodes": 2}


def test_classification_does_not_depend_on_input_order():
    nodes = [n(f"k{i}", name) for i, name in enumerate(["栈", "栈", "队列", "队列", "树", "图", "堆", "堆"])]
    edges = [e("k0", "k2", "low_confidence", 0.4), e("k2", "k4", "low_confidence", 0.4)]
    expected = classify(nodes, edges)
    for seed in range(5):
        rng = random.Random(seed)
        shuffled_nodes, shuffled_edges = nodes[:], edges[:]
        rng.shuffle(shuffled_nodes)
        rng.shuffle(shuffled_edges)
        again = classify(shuffled_nodes, shuffled_edges)
        assert pairs(again) == pairs(expected)
        assert ids(again.isolated) == ids(expected.isolated)
        assert [r["p"]["rel_id"] for r in again.relations] == [r["p"]["rel_id"] for r in expected.relations]


# --- 纯函数：游标与分页 ------------------------------------------------------------------------------


def _walk(items, key, limit, kind, between=None):
    """逐页读完；``between(seen)`` 在两页之间模拟教师处理条目（返回新的完整列表）。"""
    seen, after = [], None
    while True:
        chosen, last = page(items, key, after, limit)
        seen.extend(chosen)
        if last is None:
            return seen
        after = decode_cursor(kind, encode_cursor(kind, last))
        if between is not None:
            items = between(seen, items)


def test_pages_cover_every_item_once_in_order():
    nodes = [n(f"k{i:02d}", f"名{i % 7}") for i in range(23)]
    c = classify(nodes, [])
    for limit in (1, 4, 23, 50):
        assert _walk(c.isolated, isolated_key, limit, "isolated_node") == c.isolated


def test_paging_is_stable_while_items_are_processed():
    nodes = [n(f"k{i:02d}", f"名{i:02d}") for i in range(10)]
    full = classify(nodes, []).isolated

    def process_first_seen(seen, items):  # 每翻一页，就处理掉已看过的一条（从队列里消失）
        gone = seen[0]["kp_id"]
        return [p for p in items if p["kp_id"] != gone]

    assert ids(_walk(full, isolated_key, 3, "isolated_node", process_first_seen)) == ids(full)

    edges = [e(f"k{i:02d}", f"k{i + 1:02d}", "low_confidence", round(0.1 * (i % 3), 1)) for i in range(9)]
    rels = classify(nodes, edges).relations
    walked = _walk(rels, relation_key, 2, "low_confidence_relation",
                   lambda seen, items: [r for r in items if r is not seen[-1]])
    assert [r["p"]["rel_id"] for r in walked] == [r["p"]["rel_id"] for r in rels]


def test_duplicate_cursor_round_trips_the_similarity():
    c = classify([n("a", "快速排序"), n("b", "快速排序算法"), n("c", "栈"), n("d", "栈")], [])
    key = c.duplicates[0].key
    assert decode_cursor("suspected_duplicate", encode_cursor("suspected_duplicate", key)) == key
    assert _walk(c.duplicates, lambda d: d.key, 1, "suspected_duplicate") == c.duplicates


@pytest.mark.parametrize("kind, cursor, reason", [
    (None, encode_cursor("isolated_node", ["a", "b"]), "kind_required"),
    ("isolated_node", "not base64 at all!", "invalid_cursor"),
    ("isolated_node", encode_cursor("low_confidence_relation", [0.5, "r"]), "invalid_cursor"),
    ("isolated_node", encode_cursor("isolated_node", ["a"]), "invalid_cursor"),
    ("low_confidence_relation", encode_cursor("low_confidence_relation", ["x", "r"]), "invalid_cursor"),
    ("suspected_duplicate", encode_cursor("suspected_duplicate", [True, "a", "b"]), "invalid_cursor"),
])
def test_bad_cursors_are_rejected(kind, cursor, reason):
    with pytest.raises(InvalidCursor) as caught:
        decode_cursor(kind, cursor)
    assert caught.value.reason == reason


# --- 迁移 013 ---------------------------------------------------------------------------------------


def _schema(url):
    with connect(url) as db:
        return sorted(db.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
                                 "AND name <> 'schema_migrations'").fetchall())


def test_documented_rollback_restores_previous_schema_and_can_be_reapplied(tmp_path):
    before_dir, all_dir = tmp_path / "before", tmp_path / "all"
    before_dir.mkdir()
    all_dir.mkdir()
    ours = MIGRATIONS / "013_review_dismissals.sql"
    for path in MIGRATIONS.glob("*.sql"):
        shutil.copy(path, all_dir / path.name)
        if path.name < ours.name:
            shutil.copy(path, before_dir / path.name)
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url, before_dir)
    previous = _schema(url)
    migrate(url, all_dir)
    assert _schema(url) != previous

    prefix = "-- ROLLBACK: "
    steps = [line[len(prefix):] for line in ours.read_text(encoding="utf-8").splitlines() if line.startswith(prefix)]
    assert steps
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        for step in steps:
            db.execute(step)
        db.execute("COMMIT")
    assert _schema(url) == previous
    assert "013" in migrate(url, all_dir)


def test_dismissals_are_unique_per_course_kind_and_key(tmp_path):
    from app.repositories.accounts import insert_account
    from app.repositories.courses import create_course
    from app.repositories.review import dismiss, pair_key, read_dismissals

    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH, role="teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    assert pair_key("b", "a") == pair_key("a", "b") == '["a","b"]'
    assert dismiss(url, course.id, "suspected_duplicate", pair_key("b", "a"), teacher.id) is True
    assert dismiss(url, course.id, "suspected_duplicate", pair_key("a", "b"), teacher.id) is False
    assert dismiss(url, course.id, "isolated_node", "k1", teacher.id) is True
    assert read_dismissals(url, course.id) == ({("a", "b")}, {"k1"})
    with pytest.raises(sqlite3.IntegrityError):
        with connect(url) as db:
            db.execute("INSERT INTO review_dismissals VALUES (?, 'other', 'k', ?, 'now')", (course.id, teacher.id))


# --- 真实 Neo4j：单项处理与接口 ------------------------------------------------------------------------

_LIVE = all(os.environ.get(name) for name in (
    "SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD"))
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


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
    """一门课程的草稿种子数据（属性与 F04/F06/F08 写入的一致）。"""

    def __init__(self, q, course):
        self.q, self.course = q, course

    def node(self, kp_id, *, name=None, tasks=(DONE,), status="draft", aliases=(), revision=1):
        props = {"kp_id": kp_id, "name": name or kp_id, "aliases": list(aliases), "type": "concept",
                 "definition": f"{kp_id} 的定义", "confidence": 0.9, "status": status, "source": "ai",
                 "locked": False, "revision": revision, "contrib_tasks": list(tasks), "contrib_manual": False,
                 "level": 0}
        self.q("CREATE (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) SET n += $p", c=self.course, p=props)

    def edge(self, type, a, b, *, status="draft", confidence=0.8, tasks=(DONE,)):
        from app.repositories.graph_relations import derive_rel_id

        rel_id = derive_rel_id(self.course, type, a, b)
        props = {"course_id": self.course, "version_id": "draft", "rel_id": rel_id, "confidence": confidence,
                 "status": status, "source": "ai", "contrib_tasks": list(tasks), "contrib_manual": False,
                 "source_pairs": [], "revision": 1}
        self.q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: 'draft', kp_id: $a}}), "
               f"(b:KnowledgePoint {{course_id: $c, version_id: 'draft', kp_id: $b}}) "
               f"CREATE (a)-[r:{type}]->(b) SET r = $p", c=self.course, a=a, b=b, p=props)
        self.q("CREATE (:RelationIdentity {course_id: $c, version_id: 'draft', rel_id: $r, type: $t, "
               "from_id: $a, to_id: $b})", c=self.course, r=rel_id, t=type, a=a, b=b)
        return rel_id

    def props(self, kp_id):
        rows = self.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k}) "
                      "RETURN properties(n) AS p", c=self.course, k=kp_id)
        return rows[0]["p"] if rows else None

    def relation(self, rel_id):
        rows = self.q("MATCH ()-[r {course_id: $c, version_id: 'draft', rel_id: $r}]->() RETURN properties(r) AS p",
                      c=self.course, r=rel_id)
        return rows[0]["p"] if rows else None

    def dump(self):
        nodes = self.q("MATCH (n {course_id: $c}) WHERE NOT n:DraftWriteGuard RETURN properties(n) AS p", c=self.course)
        rels = self.q("MATCH (a {course_id: $c})-[r]->(b {course_id: $c}) RETURN properties(r) AS p", c=self.course)
        key = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)  # noqa: E731
        return sorted(map(key, nodes)), sorted(map(key, rels))


@pytest.fixture
def env(tmp_path, monkeypatch):
    if not _LIVE:
        pytest.skip("isolated Neo4j fixture not configured")
    neo4j = pytest.importorskip("neo4j")
    from fastapi.testclient import TestClient

    from app.repositories.accounts import insert_account
    from app.repositories.courses import add_member, create_course
    from app.repositories.graph_edit import DraftNodeStore
    from app.repositories.graph_migrations import apply_migrations
    from app.repositories.graph_read import GraphReader
    from app.repositories.neo4j import Neo4jRepository
    from app.services.auth import issue_access_token
    from app.services.graph.edit_node import EditContext

    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)

    def account(name, role):
        return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)

    teacher, student = account("teacher1", "teacher"), account("student1", "student")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    _task(url, course.id, DONE, "completed")
    _task(url, course.id, FAILED, "failed")
    driver = neo4j.GraphDatabase.driver(
        os.environ["SMARTSKETCH_TEST_NEO4J_URI"],
        auth=(os.environ["SMARTSKETCH_TEST_NEO4J_USER"], os.environ["SMARTSKETCH_TEST_NEO4J_PASSWORD"]))
    apply_migrations(driver)
    repo = Neo4jRepository(driver)

    def q(query, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    ctx = EditContext(url, DraftNodeStore(repo), GraphReader(repo), lock_seconds=30, wait_seconds=0)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("COURSE_LOCK_WAIT_SECONDS", "0")
    from app.main import create_app  # 模块导入时会校验签名密钥，须在设置环境变量之后

    application = create_app()
    application.state.graph_node_store = ctx.store
    application.state.graph_reader = ctx.reader

    def headers(user):
        token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                                   issued_at=int(time.time()), ttl_seconds=3600)
        return {"Authorization": f"Bearer {token}"}

    try:
        with TestClient(application) as client:
            def get(user=None, **params):
                return client.get(f"/api/v1/courses/{course.id}/review", params=params,
                                  headers=headers(user or teacher))

            def act(body, user=None):
                return client.post(f"/api/v1/courses/{course.id}/review/actions", json=body,
                                   headers=headers(user or teacher))

            yield SimpleNamespace(url=url, course=course.id, ctx=ctx, g=Graph(q, course.id), q=q, get=get, act=act,
                                  teacher=teacher, student=student)
    finally:
        q("MATCH (n) WHERE n.course_id = $c DETACH DELETE n", c=course.id)
        driver.close()


def _draft_revision(env):
    with connect(env.url) as db:
        return db.execute("SELECT draft_revision FROM courses WHERE id = ?", (env.course,)).fetchone()[0]


def _queue(env, **params):
    response = env.get(**params)
    assert response.status_code == 200, response.text
    assert_schema("ReviewQueue", response.json())
    return response.json()


def _ok(response):
    assert response.status_code == 200, response.text
    assert_schema("ReviewActionResult", response.json())
    return response.json()


@live
def test_api_lists_the_three_columns_from_the_visible_draft(env):
    g = env.g
    g.node("a", name="栈")
    g.node("b", name="栈")
    g.node("c", name="队列")
    g.node("d", name="树")
    g.node("hidden", name="队列", tasks=(FAILED,))          # 不在 V 中：不可见，不参与任何一栏
    low = g.edge("PREREQUISITE", "a", "c", status="low_confidence", confidence=0.4)
    g.edge("RELATED_TO", "c", "hidden", status="low_confidence")

    body = _queue(env)
    assert [r["id"] for r in body["low_confidence_relations"]] == [low]
    assert body["low_confidence_relations"][0]["status"] == "low_confidence"
    assert body["suspected_duplicates"] == [{"candidates": [{"id": "a", "name": "栈", "type": "concept"},
                                                            {"id": "b", "name": "栈", "type": "concept"}],
                                             "similarity": 1.0, "reason": "same_key"}]
    assert [p["id"] for p in body["isolated_nodes"]] == ["b", "d"]  # 「栈」<「树」，同名按 ID
    assert body["totals"] == {"low_confidence_relations": 1, "suspected_duplicates": 1, "isolated_nodes": 2}
    assert body["next_cursors"] == {"low_confidence_relations": None, "suspected_duplicates": None,
                                    "isolated_nodes": None}

    assert env.get(user=env.student).status_code == 403


@live
def test_api_pages_one_column_with_keyset_cursors(env):
    for i in range(5):
        env.g.node(f"k{i}", name=f"孤立{i}")
    first = _queue(env, limit=2)
    assert [p["id"] for p in first["isolated_nodes"]] == ["k0", "k1"]
    assert first["totals"]["isolated_nodes"] == 5
    cursor = first["next_cursors"]["isolated_nodes"]

    # 处理掉第一页的一条后翻页：后面的条目既不跳过也不重复
    _ok(env.act({"item": "isolated_node", "kp_id": "k0", "action": "approve"}))
    second = _queue(env, kind="isolated_node", cursor=cursor, limit=2)
    assert [p["id"] for p in second["isolated_nodes"]] == ["k2", "k3"]
    assert second["low_confidence_relations"] == [] and second["suspected_duplicates"] == []
    assert second["totals"]["isolated_nodes"] == 4
    third = _queue(env, kind="isolated_node", cursor=second["next_cursors"]["isolated_nodes"], limit=2)
    assert [p["id"] for p in third["isolated_nodes"]] == ["k4"]
    assert third["next_cursors"]["isolated_nodes"] is None

    for params in ({"cursor": cursor}, {"kind": "suspected_duplicate", "cursor": cursor},
                   {"kind": "isolated_node", "cursor": "%%%"}, {"limit": 0}, {"limit": 201}, {"kind": "nope"}):
        bad = env.get(**params)
        assert bad.status_code == 422, params
        assert bad.json()["code"] == "VALIDATION_ERROR"


@live
def test_approving_and_rejecting_low_confidence_relations(env):
    g = env.g
    for kp in ("a", "b", "c"):
        g.node(kp)
    first = g.edge("PREREQUISITE", "a", "b", status="low_confidence", confidence=0.3)
    second = g.edge("RELATED_TO", "b", "c", status="low_confidence", confidence=0.5)
    before = _draft_revision(env)

    done = _ok(env.act({"item": "low_confidence_relation", "rel_id": first, "action": "approve"}))
    assert done == {"item": "low_confidence_relation", "action": "approve", "changed": True,
                    "totals": {"low_confidence_relations": 1, "suspected_duplicates": 0, "isolated_nodes": 0}}
    r = g.relation(first)
    assert r["status"] == "approved" and r["contrib_manual"] is True and r["revision"] == 2
    assert _draft_revision(env) == before + 1

    again = _ok(env.act({"item": "low_confidence_relation", "rel_id": first, "action": "approve"}))
    assert again["changed"] is False and _draft_revision(env) == before + 1 and g.relation(first)["revision"] == 2

    wrong = env.act({"item": "low_confidence_relation", "rel_id": first, "action": "reject"})
    assert wrong.status_code == 404 and wrong.json()["code"] == "NOT_FOUND"

    rejected = _ok(env.act({"item": "low_confidence_relation", "rel_id": second, "action": "reject"}))
    assert rejected["changed"] is True and rejected["totals"]["low_confidence_relations"] == 0
    assert g.relation(second)["status"] == "rejected"
    # b→c 被拒绝后 c 没有会被发布的边，进入孤立栏
    assert [p["id"] for p in _queue(env)["isolated_nodes"]] == ["c"]
    assert env.act({"item": "low_confidence_relation", "rel_id": "missing", "action": "approve"}).status_code == 404


@live
def test_relation_on_a_hidden_or_rejected_endpoint_is_not_in_the_queue(env):
    g = env.g
    g.node("a")
    g.node("b", status="rejected")
    g.node("h", tasks=(FAILED,))
    to_rejected = g.edge("PREREQUISITE", "a", "b", status="low_confidence")
    to_hidden = g.edge("PREREQUISITE", "a", "h", status="low_confidence")
    snapshot = g.dump()
    for rel_id in (to_rejected, to_hidden):
        assert env.act({"item": "low_confidence_relation", "rel_id": rel_id, "action": "approve"}).status_code == 404
    assert g.dump() == snapshot


@live
def test_isolated_nodes_can_be_kept_or_rejected(env):
    g = env.g
    for kp in ("a", "b", "x", "y"):
        g.node(kp)
    g.edge("PREREQUISITE", "x", "y")
    before = _draft_revision(env)

    kept = _ok(env.act({"item": "isolated_node", "kp_id": "a", "action": "approve"}))
    assert kept["changed"] is True and kept["totals"]["isolated_nodes"] == 1
    assert _draft_revision(env) == before  # 只记在 SQLite，不改草稿
    assert g.props("a")["status"] == "draft" and g.props("a")["revision"] == 1
    assert _ok(env.act({"item": "isolated_node", "kp_id": "a", "action": "approve"}))["changed"] is False
    assert env.act({"item": "isolated_node", "kp_id": "a", "action": "reject"}).status_code == 404

    dropped = _ok(env.act({"item": "isolated_node", "kp_id": "b", "action": "reject"}))
    assert dropped["changed"] is True and dropped["totals"]["isolated_nodes"] == 0
    p = g.props("b")
    assert p["status"] == "rejected" and p["locked"] is True and p["contrib_manual"] is True and p["revision"] == 2
    assert _draft_revision(env) == before + 1
    assert _ok(env.act({"item": "isolated_node", "kp_id": "b", "action": "reject"}))["changed"] is False
    assert _draft_revision(env) == before + 1

    g.node("c")
    g.node("gone", status="rejected")
    g.edge("PREREQUISITE", "c", "gone")  # 唯一的边通往已拒绝的节点：发布时连带排除，c 仍算孤立
    assert [p["id"] for p in _queue(env)["isolated_nodes"]] == ["c"]
    assert _ok(env.act({"item": "isolated_node", "kp_id": "c", "action": "reject"}))["changed"] is True
    assert g.props("c")["status"] == "rejected"

    for kp in ("x", "missing"):  # 有边的节点、不存在的节点都不在队列中
        assert env.act({"item": "isolated_node", "kp_id": kp, "action": "reject"}).status_code == 404
        assert env.act({"item": "isolated_node", "kp_id": kp, "action": "approve"}).status_code == 404


@live
def test_duplicates_can_be_dismissed_or_merged(env):
    g = env.g
    g.node("a", name="栈")
    g.node("b", name="栈", aliases=["堆栈"])
    g.node("c", name="队列")
    g.node("d", name="队列（queue）")
    g.edge("PREREQUISITE", "a", "c")
    g.edge("PREREQUISITE", "b", "d")
    assert _queue(env)["totals"]["suspected_duplicates"] == 2

    dismissed = _ok(env.act({"item": "suspected_duplicate", "kp_ids": ["d", "c"], "action": "reject"}))
    assert dismissed["changed"] is True and dismissed["totals"]["suspected_duplicates"] == 1
    assert _ok(env.act({"item": "suspected_duplicate", "kp_ids": ["c", "d"], "action": "reject"}))["changed"] is False

    before = _draft_revision(env)
    merged = _ok(env.act({"item": "suspected_duplicate", "kp_ids": ["a", "b"], "action": "merge", "primary_id": "a"}))
    assert merged["changed"] is True and merged["totals"]["suspected_duplicates"] == 0
    assert g.props("b") is None and g.props("a")["merged_from"] == ["b"] and "堆栈" in g.props("a")["aliases"]
    assert _draft_revision(env) == before + 1
    repeat = _ok(env.act({"item": "suspected_duplicate", "kp_ids": ["b", "a"], "action": "merge", "primary_id": "a"}))
    assert repeat["changed"] is False and _draft_revision(env) == before + 1

    gone = env.act({"item": "suspected_duplicate", "kp_ids": ["a", "b"], "action": "reject"})
    assert gone.status_code == 404
    other = env.act({"item": "suspected_duplicate", "kp_ids": ["a", "c"], "action": "reject"})
    assert other.status_code == 404  # 不是疑似重复的一对不能记为「不是重复」


@live
def test_merge_from_the_queue_keeps_merge_conflicts(env):
    g = env.g
    for kp, name in (("p", "栈"), ("q", "栈"), ("m", "中间")):
        g.node(kp, name=name)
    g.edge("PREREQUISITE", "p", "m")
    g.edge("PREREQUISITE", "m", "q")
    snapshot = g.dump()
    cycle = env.act({"item": "suspected_duplicate", "kp_ids": ["p", "q"], "action": "merge", "primary_id": "p"})
    assert cycle.status_code == 409 and cycle.json()["code"] == "CYCLE_DETECTED"
    assert g.dump() == snapshot


@live
def test_graph_writes_wait_for_the_course_lock(env):
    g = env.g
    g.node("a")
    g.node("b")
    rel = g.edge("PREREQUISITE", "a", "b", status="low_confidence")
    snapshot, before = g.dump(), _draft_revision(env)
    lock = course_locks.acquire(env.url, env.course, holder="publish", lease_seconds=30, wait_seconds=0)
    try:
        busy = env.act({"item": "low_confidence_relation", "rel_id": rel, "action": "approve"})
    finally:
        course_locks.release(env.url, lock)
    assert busy.status_code == 409 and busy.json()["code"] == "COURSE_BUSY"
    assert g.dump() == snapshot and _draft_revision(env) == before


@live
@pytest.mark.parametrize("body", [
    {"item": "nope", "rel_id": "r", "action": "approve"},
    {"rel_id": "r", "action": "approve"},
    {"item": "low_confidence_relation", "rel_id": "r", "action": "merge"},
    {"item": "low_confidence_relation", "rel_id": "", "action": "approve"},
    {"item": "low_confidence_relation", "action": "approve"},
    {"item": "low_confidence_relation", "rel_id": "r", "action": "approve", "extra": 1},
    {"item": "isolated_node", "kp_id": "k", "action": "approve", "primary_id": "k"},
    {"item": "suspected_duplicate", "kp_ids": ["a"], "action": "reject"},
    {"item": "suspected_duplicate", "kp_ids": ["a", "a"], "action": "reject"},
    {"item": "suspected_duplicate", "kp_ids": ["a", "b"], "action": "approve"},
    {"item": "suspected_duplicate", "kp_ids": ["a", "b"], "action": "merge"},
    {"item": "suspected_duplicate", "kp_ids": ["a", "b"], "action": "merge", "primary_id": "c"},
    {"item": "suspected_duplicate", "kp_ids": ["a", "b"], "action": "reject", "primary_id": "a"},
    ["not", "an", "object"],
])
def test_invalid_actions_are_validation_errors(env, body):
    response = env.act(body)
    assert response.status_code == 422, body
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert_schema("Error", response.json())


@live
def test_students_cannot_resolve_items(env):
    env.g.node("a")
    response = env.act({"item": "isolated_node", "kp_id": "a", "action": "reject"}, user=env.student)
    assert response.status_code == 403
    assert env.g.props("a")["status"] == "draft"
