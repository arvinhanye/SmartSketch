"""F06 API × 真实 Neo4j 5.26 + 真实 SQLite：``/relations`` 三条路由的端到端行为（ADR-071）。

后端用例（``tests/backend/test_relations_api.py``）用内存草稿图验证协议、鉴权、错误映射与审计时序；
这里验证只有真 Cypher 能证明的部分：关系的身份（§8.4 由「课程 + 类型 + 起点 + 终点」派生）、
守卫锁下的环检测、``source_pairs`` 与 ``source_refs`` 的真实来源、关系身份与边的删除、
以及响应体确实由读图 + 读块拼出（不是请求体回显）。

只在设置 ``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行；夹具复用 ``test_f09`` 的
``env``/``Graph``/``live``（真实存储 + 每课独立 ID + 只清理自己的数据）。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.repositories.courses import add_member, create_course
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_read import GraphReader
from app.repositories.graph_relation_edit import DraftRelationStore
from app.repositories.graph_relations import derive_rel_id
from app.repositories.neo4j import Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.chunking import ChunkSource, SemanticChunk, chunking_version
from app.services.parsers.models import RevisionKey, SourceLocator
from test_f09 import (  # noqa: F401  (shared live helpers)
    DONE,
    FAILED,
    SECRET,
    Graph,
    _account,
    _draft_revision,
    _task,
    live,
)

PARSER = "txt/1+" + chunking_version(1500, 200)
CHUNK_TEXT = "栈是一种后进先出的线性表。"


@pytest.fixture
def env(tmp_path):
    """真实 Neo4j + 真实 SQLite；本课 V 含已完成任务 ``t-done``，他课的贡献在本课 V 之外。"""
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

    try:
        yield SimpleNamespace(url=url, course=course.id, other=other.id, repo=repo, q=q,
                              g=Graph(q, course.id), og=Graph(q, other.id), teacher=teacher, student=student)
    finally:
        q("MATCH (n) WHERE n.course_id IN [$a, $b] DETACH DELETE n", a=course.id, b=other.id)
        driver.close()


def _chunk(env, document_id, *, task=DONE) -> str:
    """为 ``task`` 的修订落一个带页码定位的文本块，返回块 ID（关系来源要能定位回原文）。"""
    key = RevisionKey(document_id=document_id, content_hash="sha256:" + uuid.uuid4().hex * 2,
                      parser_version=PARSER)
    chunk = SemanticChunk(0, CHUNK_TEXT, ("第二章",),
                          (ChunkSource(0, 0, len(CHUNK_TEXT), SourceLocator(page=3)),))
    from app.repositories.chunks import persist_revision_chunks
    _, written = persist_revision_chunks(env.url, course_id=env.course, task_id=task, key=key, chunks=[chunk])
    return (written.inserted + written.existing)[0]


@pytest.fixture
def api(env, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", env.url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("COURSE_LOCK_WAIT_SECONDS", "0")
    from app.main import create_app  # 模块导入时会校验签名密钥，须在设置环境变量之后

    application = create_app()
    application.state.relation_store = DraftRelationStore(env.repo)
    application.state.graph_reader = GraphReader(env.repo)

    def call(method, path, user=None, body=None, course=None, anonymous=False):
        headers = {}
        if not anonymous:
            user = env.teacher if user is None else user
            headers = {"Authorization": "Bearer " + issue_access_token(
                user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=int(time.time()),
                ttl_seconds=3600)}
        return client.request(method, f"/api/v1/courses/{course or env.course}{path}", headers=headers, json=body)

    with TestClient(application) as client:
        yield call


def _rel_id(env, type, a, b):
    return derive_rel_id(env.course, type, a, b)


def _edge(env, type, a, b, *, status="draft", source="ai", confidence=0.8, tasks=(DONE,), chunks=()):
    """``Graph.edge`` 只支持端点与来源块；状态与来源属性在这里补写（与 F13 写入的属性同名）。"""
    rel_id = env.g.edge(type, a, b, tasks=tasks, chunks=chunks)
    env.q("MATCH (:KnowledgePoint {course_id: $c, version_id: 'draft'})"
          "-[r {course_id: $c, version_id: 'draft', rel_id: $r}]->() "
          "SET r.status = $s, r.source = $src, r.confidence = $conf",
          c=env.course, r=rel_id, s=status, src=source, conf=confidence)
    return rel_id


def _edges(env, type="PREREQUISITE"):
    return env.q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: 'draft'}})-[r:{type} "
                 "{course_id: $c, version_id: 'draft'}]->(b:KnowledgePoint {course_id: $c}) "
                 "RETURN a.kp_id AS a, b.kp_id AS b, properties(r) AS p", c=env.course)


def _logs(env):
    from app.repositories import edit_logs
    return edit_logs.list_logs(env.url, env.course)


@live
def test_create_writes_the_edge_its_identity_and_the_audit_row(env, api):
    for kp in ("a", "b"):
        env.g.node(kp)
    before = _draft_revision(env)

    response = api("POST", "/relations", body={"type": "PREREQUISITE", "from_id": "a", "to_id": "b"})

    assert response.status_code == 201, response.text
    body = response.json()
    rel_id = _rel_id(env, "PREREQUISITE", "a", "b")
    assert body == {"id": rel_id, "course_id": env.course, "type": "PREREQUISITE", "from_id": "a",
                    "to_id": "b", "confidence": 1.0, "status": "approved", "source": "manual",
                    "source_refs": []}
    [edge] = _edges(env)
    assert (edge["a"], edge["b"]) == ("a", "b")
    assert (edge["p"]["source"], edge["p"]["status"], edge["p"]["contrib_manual"]) == ("manual", "approved", True)
    assert env.g.identities() == {("draft", rel_id)}
    assert _draft_revision(env) == before + 1
    # 守卫节点：仓储层的事务先加锁，F06 的 ``apply_relations`` 在同一事务里再加一次（与 F13 的
    # ``_write_draft`` 相同），锁只加一次而序号按调用计两次。
    assert env.q("MATCH (g:DraftWriteGuard {course_id: $c, version_id: 'draft'}) RETURN g.seq AS s",
                 c=env.course)[0]["s"] == 2
    [entry] = _logs(env)
    assert (entry.action, entry.kp_id, entry.state, entry.actor_id) == ("create", rel_id, "committed",
                                                                       env.teacher.id)
    assert entry.draft_revision == before + 1
    assert entry.summary["after"] == {"type": "PREREQUISITE", "from_id": "a", "to_id": "b",
                                      "status": "approved", "source": "manual", "rel_id": rel_id,
                                      "revision": 1}


@live
def test_the_response_is_read_back_from_the_graph_with_the_real_evidence(env, api):
    """响应里的 ``confidence`` / ``status`` / ``source_refs`` 请求体里都没有：只能来自读图 + 读块。"""
    for kp in ("a", "b"):
        env.g.node(kp)
    chunk_id = _chunk(env, "doc-" + env.course)
    seeded = _edge(env, "RELATED_TO", "a", "b", status="low_confidence", chunks=(chunk_id,))

    response = api("PATCH", f"/relations/{seeded}", body={"status": "approved"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == seeded and (body["type"], body["status"], body["source"]) == ("RELATED_TO",
                                                                                       "approved", "manual")
    assert body["confidence"] == 0.8  # 关系属性来自图，不是请求体
    [ref] = body["source_refs"]
    assert ref["chunk_id"] == chunk_id and ref["page"] == 3  # 块与页码定位来自 SQLite，不是请求体
    [edge] = _edges(env, "RELATED_TO")
    assert edge["p"]["source_pairs"] == [json.dumps([DONE, chunk_id])]  # 改状态不丢来源证据
    assert edge["p"]["contrib_manual"] is True and edge["p"]["revision"] == 2


@live
def test_cycle_is_rejected_and_nothing_is_written(env, api):
    for kp in ("a", "b", "c"):
        env.g.node(kp)
    env.g.edge("PREREQUISITE", "a", "b")
    env.g.edge("PREREQUISITE", "b", "c")
    before = _draft_revision(env)
    snapshot = env.g.dump()

    response = api("POST", "/relations", body={"type": "PREREQUISITE", "from_id": "c", "to_id": "a"})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CYCLE_DETECTED"
    cycle = body["details"]["cycle"]
    assert cycle[0] == cycle[-1] == "c" and set(cycle[:-1]) == {"a", "b", "c"}
    assert env.g.dump() == snapshot and _draft_revision(env) == before and _logs(env) == []


@live
def test_reversing_a_direction_moves_the_relation_to_the_new_identity(env, api):
    for kp in ("a", "b"):
        env.g.node(kp)
    old = env.g.edge("PREREQUISITE", "a", "b")
    before = _draft_revision(env)

    response = api("PATCH", f"/relations/{old}", body={"from_id": "b", "to_id": "a"})

    assert response.status_code == 200, response.text
    new = _rel_id(env, "PREREQUISITE", "b", "a")
    assert response.json()["id"] == new and response.json()["from_id"] == "b"
    [(a, b, _)] = [(e["a"], e["b"], e["p"]) for e in _edges(env)]
    assert (a, b) == ("b", "a")                       # 旧边不再存在，也不可能同时存在而误报成环
    assert env.g.identities() == {("draft", new)}
    assert _draft_revision(env) == before + 1
    [entry] = _logs(env)
    assert (entry.action, entry.kp_id) == ("update", new)
    assert entry.summary["before"] == {"type": "PREREQUISITE", "from_id": "a", "to_id": "b",
                                       "status": "draft", "source": "ai", "rel_id": old, "revision": 1}
    assert entry.summary["after"]["rel_id"] == new and entry.summary["after"]["from_id"] == "b"


@live
def test_reviving_a_downgraded_edge_into_a_cycle_is_rejected(env, api):
    """规格第 43 行：教师把降级边改回 ``PREREQUISITE``，环仍在则 409，且不降级、不写入任何边。"""
    for kp in ("a", "b", "c"):
        env.g.node(kp)
    env.g.edge("PREREQUISITE", "b", "c")
    env.g.edge("PREREQUISITE", "c", "a")
    downgraded = _edge(env, "RELATED_TO", "a", "b", status="low_confidence")
    before = _draft_revision(env)
    snapshot = env.g.dump()

    response = api("PATCH", f"/relations/{downgraded}", body={"type": "PREREQUISITE"})

    assert response.status_code == 409 and response.json()["code"] == "CYCLE_DETECTED"
    assert env.g.dump() == snapshot and _draft_revision(env) == before and _logs(env) == []


@live
def test_reviving_a_rejected_edge_rechecks_the_cycle(env, api):
    for kp in ("a", "b"):
        env.g.node(kp)
    ab = _edge(env, "PREREQUISITE", "a", "b", status="rejected")
    env.g.edge("PREREQUISITE", "b", "a")
    before = _draft_revision(env)

    response = api("PATCH", f"/relations/{ab}", body={"status": "approved"})

    assert response.status_code == 409 and response.json()["code"] == "CYCLE_DETECTED"
    assert env.g.props("a") is not None and _draft_revision(env) == before and _logs(env) == []
    [kept] = [e for e in _edges(env) if (e["a"], e["b"]) == ("a", "b")]
    assert kept["p"]["status"] == "rejected"


@live
def test_delete_removes_the_edge_and_the_identity_once(env, api):
    env.g.node("a")
    env.g.node("b")
    rel_id = env.g.edge("PREREQUISITE", "a", "b")
    before = _draft_revision(env)

    first = api("DELETE", f"/relations/{rel_id}")
    assert first.status_code == 204 and first.content == b""

    assert _edges(env) == [] and env.g.identities() == set()
    assert _draft_revision(env) == before + 1
    [entry] = _logs(env)
    assert (entry.action, entry.kp_id, entry.state) == ("delete", rel_id, "committed")
    assert entry.summary["deleted"]["type"] == "PREREQUISITE"

    second = api("DELETE", f"/relations/{rel_id}")
    assert second.status_code == 404 and second.json()["code"] == "NOT_FOUND"
    assert _draft_revision(env) == before + 1 and len(_logs(env)) == 1


@live
@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_a_relation_invisible_in_this_draft_is_404(env, api, method):
    env.g.node("a")
    env.g.node("b")
    hidden = env.g.edge("PREREQUISITE", "a", "b", tasks=(DONE + "-o",))  # 他课任务的贡献：本课 V 之外
    before, snapshot = _draft_revision(env), env.g.dump()

    response = (api(method, f"/relations/{hidden}", body={"status": "approved"}) if method == "PATCH"
                else api(method, f"/relations/{hidden}"))

    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert env.g.dump() == snapshot and _draft_revision(env) == before and _logs(env) == []


@live
def test_only_this_course_teachers_reach_a_relation(env, api):
    env.g.node("a")
    env.g.node("b")
    rel_id = env.g.edge("PREREQUISITE", "a", "b")
    before, other_before = _draft_revision(env), _draft_revision(env, course=env.other)

    assert api("PATCH", f"/relations/{rel_id}", user=env.student,
               body={"status": "approved"}).json()["code"] == "ROLE_FORBIDDEN"
    assert api("DELETE", f"/relations/{rel_id}", anonymous=True).status_code == 401

    # 他课的关系经本课路径不可见：同一身份在另一门课里是另一条关系（rel_id 含 course_id）
    env.og.node("a", tasks=(DONE + "-o",))
    env.og.node("b", tasks=(DONE + "-o",))
    other_rel = env.og.edge("PREREQUISITE", "a", "b", tasks=(DONE + "-o",))
    assert other_rel != rel_id
    assert api("PATCH", f"/relations/{other_rel}", body={"status": "approved"}).status_code == 404
    assert api("DELETE", f"/relations/{other_rel}").status_code == 404

    # 他课自己写自己的：本课的草稿与审计不受影响
    created = api("POST", "/relations", course=env.other,
                  body={"type": "CONTAINS", "from_id": "a", "to_id": "b"})
    assert created.status_code == 201, created.text
    assert created.json()["course_id"] == env.other
    assert _draft_revision(env) == before and _logs(env) == []
    assert _draft_revision(env, course=env.other) == other_before + 1
    assert [e["a"] for e in _edges(env)] == ["a"]


@live
def test_busy_course_lock_is_409_and_writes_nothing(env, api):
    from app.repositories import course_locks
    env.g.node("a")
    env.g.node("b")
    before, snapshot = _draft_revision(env), env.g.dump()
    lock = course_locks.acquire(env.url, env.course, holder="publish", lease_seconds=30, wait_seconds=0)
    try:
        response = api("POST", "/relations", body={"type": "PREREQUISITE", "from_id": "a", "to_id": "b"})
    finally:
        course_locks.release(env.url, lock)

    assert response.status_code == 409
    assert response.json() == {"code": "COURSE_BUSY",
                               "message": "课程正在被其他操作写入，请稍后重试",
                               "details": {"holder": "publish"}}
    assert env.g.dump() == snapshot and _draft_revision(env) == before and _logs(env) == []
