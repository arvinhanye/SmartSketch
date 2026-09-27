"""F06 API：``POST/PATCH/DELETE /api/v1/courses/{cid}/relations``（契约 ``createRelation`` /
``updateRelation`` / ``deleteRelation``；specs/course-knowledge-graph.md「前置关系成环处理」）。

验收（``docs/atomic-tasks.json`` F06-API）：三条路由按契约给出路径、方法、状态码与响应体；
只有本课程的教师能写（学生 403 ``ROLE_FORBIDDEN``、非成员 403 ``COURSE_FORBIDDEN``、未认证 401）；
``PREREQUISITE`` 新建与改向、以及把 ``rejected`` 恢复为有效时写入前检测成环（409 ``CYCLE_DETECTED``
且 ``details.cycle`` 给出首尾相同的链路）；悬空端点 422 ``DANGLING_ENDPOINT``；重复关系 409
``DUPLICATE_RELATION``；返回值来自真实图（不是请求体回显）；课程写锁与 ``COURSE_BUSY``；
Neo4j 不可达 503；每次成功写入恰记一条 F12 审计且草稿修订号恰加一，审计 ``commit`` 失败不回滚编辑。

Neo4j 侧是内存 ``FakeDraft``：它按语句逐条镜像 ``app.repositories.graph_relations`` 与本任务新增的
``app.repositories.graph_relation_edit`` 的 Cypher（每个 handler 都注明它替代的语句），所以被替换的只有
「Cypher 的执行」，而校验、环检测、加锁顺序、审计时序全部是真代码。真实 Cypher 由
``tests/integration/test_relations_api.py``（真实 Neo4j 5.26）覆盖。
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import edit_logs
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.neo4j import RepositoryConnectionError
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.graph import audit
from test_f08 import assert_schema

SECRET = "relations-api-test-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
V = ("t-done",)
#: ``Scenario`` 的默认调用者哨兵：省略 ``user`` 就是课程教师，``None`` 是不带令牌。
TEACHER = object()


def _account(url, name, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                              issued_at=int(time.time()), ttl_seconds=3600)


# --- 内存草稿图：逐条镜像 Cypher ---------------------------------------------------------------


class FakeDraft:
    """草稿的节点、关系与关系身份；可见性按 V 与人工贡献判定，与仓储层同一规则。"""

    def __init__(self, course_id):
        self.course_id = course_id
        self.nodes: dict[str, dict] = {}
        self.relations: dict[str, dict] = {}
        self.guard = 0
        self.fail = False
        self.writes: list[str] = []

    def _visible(self, props):
        return bool(props.get("contrib_manual")) or any(t in V for t in props.get("contrib_tasks", []))

    def kp(self, kp_id, *, manual=True, tasks=()):
        self.nodes[kp_id] = {"kp_id": kp_id, "contrib_manual": manual, "contrib_tasks": list(tasks)}

    def edge(self, type, a, b, *, status="draft", source="ai", confidence=0.8, manual=False, tasks=(),
             pairs=()):
        from app.repositories.graph_relations import derive_rel_id
        rel_id = derive_rel_id(self.course_id, type, a, b)
        self.relations[rel_id] = {
            "type": type, "from_id": a, "to_id": b,
            "props": {"course_id": self.course_id, "version_id": "draft", "rel_id": rel_id,
                      "confidence": confidence, "status": status, "source": source,
                      "contrib_tasks": list(tasks), "contrib_manual": manual,
                      "source_pairs": list(pairs), "revision": 1},
        }
        return rel_id

    def visible_nodes(self):
        return [k for k, p in self.nodes.items() if self._visible(p)]

    def detail(self, rel_id):
        """``read_relation_detail`` 的读法：不可见视为不存在。"""
        rel = self.relations.get(rel_id)
        if rel is None or not self._visible(rel["props"]):
            return None
        return {"type": rel["type"], "from_id": rel["from_id"], "to_id": rel["to_id"],
                "p": dict(rel["props"])}


_MERGE_TYPE = re.compile(r"ON CREATE SET ri\.type = '([A-Z_]+)'")


def _merge_type(query):
    """``_MERGE[type]`` 按类型逐条生成语句：类型写在语句里，行里没有。"""
    return _MERGE_TYPE.search(query).group(1)


class FakeTx:
    """一个写事务内的语句执行器；顺序与语句内容对齐 ``graph_relations``／``graph_relation_edit``。"""
    def __init__(self, draft, scope):
        self.draft, self.scope = draft, scope

    def run(self, query, parameters=None):
        p = dict(parameters or {})
        d = self.draft
        assert self.draft.course_id == self.scope.course_id
        if d.fail:
            raise RepositoryConnectionError()
        if "DraftWriteGuard" in query:                                    # _LOCK
            d.guard += 1
            return [{"seq": d.guard, "visible_tasks": len(self.scope.effective_task_ids)}]
        if "RETURN n.kp_id AS kp_id" in query:                            # _VISIBLE_NODES
            return [{"kp_id": k} for k in d.visible_nodes()]
        if "ri.type AS type" in query:                                    # _RELATIONS
            rows = []
            for rel_id in p["rel_ids"]:
                rel = d.relations.get(rel_id)
                if rel is not None:
                    rows.append({"rel_id": rel_id, "type": rel["type"], "from_id": rel["from_id"],
                                 "to_id": rel["to_id"], "status": rel["props"].get("status"),
                                 "visible": d._visible(rel["props"])})
            return rows
        if "AS downgradable" in query:
            raise AssertionError("this route must not read downgradable edges")
        if "coalesce(r.status, '') <> 'rejected'" in query:               # _PREREQUISITE_EDGES
            return [{"rel_id": rel_id, "from_id": rel["from_id"], "to_id": rel["to_id"]}
                    for rel_id, rel in sorted(d.relations.items())
                    if rel["type"] == "PREREQUISITE" and rel["props"].get("status") != "rejected"
                    and d._visible(rel["props"]) and d._visible(d.nodes.get(rel["from_id"], {}))
                    and d._visible(d.nodes.get(rel["to_id"], {}))]
        if "ON CREATE SET r.confidence" in query:                         # _MERGE[type]
            type = _merge_type(query)                                     # 类型在语句里，不在行里
            written = []
            for row in p["rows"]:
                a, b = d.nodes.get(row["from_id"]), d.nodes.get(row["to_id"])
                if a is None or b is None or not (d._visible(a) and d._visible(b)):
                    continue                                              # 端点不可见：MERGE 不命中
                old = d.relations.get(row["rel_id"])
                props = {"course_id": d.course_id, "version_id": "draft", "rel_id": row["rel_id"],
                         "confidence": row["confidence"], "status": row["status"], "source": row["source"],
                         "contrib_tasks": [], "contrib_manual": p["task_id"] is None,
                         "source_pairs": [json.dumps([p["task_id"], c]) for c in ()], "revision": 1}
                if old is not None:                                       # 教师接管不可见的关系
                    props["source_pairs"] = list(old["props"].get("source_pairs", []))
                    props["contrib_tasks"] = list(old["props"].get("contrib_tasks", []))
                    props["revision"] = int(old["props"].get("revision") or 1) + 1
                    props["contrib_manual"] = True
                d.relations[row["rel_id"]] = {"type": type, "from_id": row["from_id"],
                                              "to_id": row["to_id"], "props": props}
                written.append({"rel_id": row["rel_id"]})
            d.writes.append("merge")
            return written
        if "SET r.status = $status" in query:                             # retake_relation
            rel = d.relations.get(p["rel_id"])
            if rel is None or not d._visible(rel["props"]):
                return []
            rel["props"]["status"] = p["status"]
            rel["props"]["source"] = "manual"
            rel["props"]["contrib_manual"] = True
            rel["props"]["revision"] = int(rel["props"].get("revision") or 1) + 1
            d.writes.append("retake")
            return [{"rel_id": p["rel_id"]}]
        if "DELETE r, ri" in query:                                       # delete_relation
            rel = d.relations.get(p["rel_id"])
            if rel is None or not d._visible(rel["props"]):
                return []
            del d.relations[p["rel_id"]]
            d.writes.append("delete")
            return [{"deleted": 1}]
        if "properties(r) AS p" in query:                                 # read_relation_detail
            detail = d.detail(p["rel_id"])
            return [] if detail is None else [detail]
        raise AssertionError(f"unexpected statement: {query[:80]}")


class FakeRelationStore:
    """``DraftRelationStore`` 的替身：真事务语义由 ``FakeTx`` 提供，另含审计对账用的读。"""

    def __init__(self, draft):
        self.draft, self.transactions, self.during = draft, 0, []

    def transaction(self, scope, work):
        assert scope.version_id == "draft" and scope.effective_task_ids is not None
        self.transactions += 1
        keep = (copy.deepcopy(self.draft.nodes), copy.deepcopy(self.draft.relations), self.draft.guard)
        try:
            return work(FakeTx(self.draft, scope))
        except BaseException:                     # 一个写事务：失败则整体回滚（Neo4j 语义）
            self.draft.nodes, self.draft.relations, self.draft.guard = keep
            raise

    # audit.reconcile 需要的两个读
    def node(self, scope, kp_id):
        props = self.draft.nodes.get(kp_id)
        return dict(props) if props is not None and self.draft._visible(props) else None

    def relation(self, scope, rel_id):
        detail = self.draft.detail(rel_id)
        if detail is None:
            return None
        p = detail["p"]
        return {"rel_id": rel_id, "type": detail["type"], "from_id": detail["from_id"],
                "to_id": detail["to_id"], "status": p.get("status"), "source": p.get("source"),
                "revision": p.get("revision"), "p": p}


class FakeReader:
    """只用于 ``EditContext.reader``；关系路由不通过它读图。"""

    def nodes(self, scope, reader, kp_ids=None):  # pragma: no cover - must not be used
        raise AssertionError("the relation routes must not read through GraphView.nodes")

    def edges(self, scope, reader, kp_ids=None):  # pragma: no cover - must not be used
        raise AssertionError("the relation routes must not read through GraphView.edges")


# --- 场景 ---------------------------------------------------------------------------------------


class Scenario:
    """``user=TEACHER`` 用课程教师，``user=None`` 表示不带 Authorization 头。"""

    def __init__(self, client, url, teacher, teacher2, student, outsider, course, draft):
        self.client, self.url, self.draft = client, url, draft
        self.teacher, self.teacher2, self.student, self.outsider = teacher, teacher2, student, outsider
        self.course = course

    def call(self, method, path, user=TEACHER, body=None, course_id=None):
        if user is TEACHER:
            user = self.teacher
        headers = {"Authorization": f"Bearer {token(user)}"} if user is not None else {}
        return self.client.request(method, f"/api/v1/courses/{course_id or self.course.id}{path}",
                                   headers=headers, json=body)

    def post(self, body, user=TEACHER):
        return self.call("POST", "/relations", user, body)

    def patch(self, rid, body, user=TEACHER):
        return self.call("PATCH", f"/relations/{rid}", user, body)

    def delete(self, rid, user=TEACHER):
        return self.call("DELETE", f"/relations/{rid}", user)

    def draft_revision(self, course_id=None):
        with connect(self.url) as db:
            return db.execute("SELECT draft_revision FROM courses WHERE id = ?",
                              (course_id or self.course.id,)).fetchone()[0]

    def locks(self):
        with connect(self.url) as db:
            return db.execute("SELECT course_id, holder FROM course_locks").fetchall()

    def logs(self, user=None, after_seq=0):
        return edit_logs.list_logs(self.url, self.course.id, after_seq=after_seq)

    def rel_id(self, type, a, b):
        from app.repositories.graph_relations import derive_rel_id
        return derive_rel_id(self.course.id, type, a, b)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(audit, "_sleep", lambda seconds: None)


@pytest.fixture
def s(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    teacher2 = _account(url, "teacher3", "teacher")
    student = _account(url, "student1", "student")
    outsider = _account(url, "teacher2", "teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=teacher2.id, role="teacher", added_by=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    with connect(url) as db:  # V 里的已完成任务（关系写入的作用域要求）
        db.execute("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
                   " VALUES ('doc1', ?, 'a.txt', 'txt', 1, ?, 'stored-doc1')",
                   (course.id, "sha256:" + uuid.uuid4().hex * 2))
        db.execute("INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key, stage, progress)"
                   " VALUES ('t-done', ?, 'doc1', 'idem-done', 'completed', 1.0)", (course.id,))
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("COURSE_LOCK_WAIT_SECONDS", "0")
    application = create_app()
    draft = FakeDraft(course.id)
    application.state.relation_store = FakeRelationStore(draft)
    application.state.graph_reader = FakeReader()
    scenario = Scenario(None, url, teacher, teacher2, student, outsider, course, draft)
    with TestClient(application) as client:
        scenario.client = client
        yield scenario


def _hold_lock(s, holder):
    with connect(s.url) as db:
        db.execute("INSERT INTO course_locks (course_id, holder, token, expires_at)"
                   " VALUES (?, ?, ?, unixepoch() + 600)", (s.course.id, holder, "t" * 32))


# --- POST：契约形状与真实图返回值 ----------------------------------------------------------------


def test_create_returns_the_relation_read_from_the_graph(s):
    s.draft.kp("a")
    s.draft.kp("b")
    before = s.draft_revision()

    response = s.post({"type": "PREREQUISITE", "from_id": "a", "to_id": "b"})

    assert response.status_code == 201, response.text
    body = response.json()
    assert_schema("Relation", body)
    rel_id = s.rel_id("PREREQUISITE", "a", "b")
    assert body == {"id": rel_id, "course_id": s.course.id, "type": "PREREQUISITE", "from_id": "a",
                    "to_id": "b", "confidence": 1.0, "status": "approved", "source": "manual",
                    "source_refs": []}
    assert s.draft.relations[rel_id]["props"]["contrib_manual"] is True
    assert s.draft_revision() == before + 1
    assert s.locks() == []
    [entry] = s.logs()
    assert (entry.action, entry.kp_id, entry.state, entry.actor_id) == ("create", rel_id, "committed",
                                                                       s.teacher.id)
    assert entry.draft_revision == before + 1 == s.draft_revision()
    assert entry.summary["after"]["type"] == "PREREQUISITE"


def test_create_takes_over_an_invisible_relation_with_the_same_identity(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", source="ai", status="draft", tasks=("t-running",))
    assert s.draft.detail(rel_id) is None  # 对教师不可见

    assert s.post({"type": "PREREQUISITE", "from_id": "a", "to_id": "b"}).status_code == 201
    assert s.draft.detail(rel_id)["p"]["source"] == "manual"


def test_duplicate_visible_relation_is_409_with_the_existing_id(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    before = s.draft_revision()

    response = s.post({"type": "PREREQUISITE", "from_id": "a", "to_id": "b"})

    assert response.status_code == 409
    body = response.json()
    assert_schema("Error", body)
    assert (body["code"], body["details"]) == ("DUPLICATE_RELATION", {"existing_id": rel_id})
    assert s.draft_revision() == before and s.logs() == []


@pytest.mark.parametrize("missing", ["b"])
def test_dangling_endpoint_is_422_with_the_missing_ids(s, missing):
    s.draft.kp("a")
    before = s.draft_revision()

    response = s.post({"type": "CONTAINS", "from_id": "a", "to_id": missing})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "DANGLING_ENDPOINT"
    assert body["details"] == {"missing": [missing]}
    assert s.draft_revision() == before and s.logs() == [] and s.draft.relations == {}


def test_cycle_is_409_with_the_conflicting_chain_and_nothing_is_written(s):
    for kp in ("a", "b", "c"):
        s.draft.kp(kp)
    ab = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    bc = s.draft.edge("PREREQUISITE", "b", "c", manual=True)
    before = s.draft_revision()

    response = s.post({"type": "PREREQUISITE", "from_id": "c", "to_id": "a"})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CYCLE_DETECTED"
    cycle = body["details"]["cycle"]
    assert cycle[0] == cycle[-1] == "c" and set(cycle[:-1]) == {"a", "b", "c"}
    assert set(s.draft.relations) == {ab, bc}  # 成环则整个操作不写入
    assert s.draft_revision() == before and s.logs() == []


def test_prerequisite_self_loop_is_a_409_cycle(s):
    s.draft.kp("a")
    response = s.post({"type": "PREREQUISITE", "from_id": "a", "to_id": "a"})
    assert response.status_code == 409
    assert response.json()["details"]["cycle"] == ["a", "a"]


@pytest.mark.parametrize("body, field, reason", [
    ({"type": "PREREQUISITE", "from_id": "a"}, "to_id", "missing"),
    ({"from_id": "a", "to_id": "b"}, "type", "missing"),
    ({"type": "LIKES", "from_id": "a", "to_id": "b"}, "type", "enum"),
    ({"type": "PREREQUISITE", "from_id": "", "to_id": "b"}, "from_id", "string_too_short"),
    ({"type": "PREREQUISITE", "from_id": "a", "to_id": None}, "to_id", "string_type"),
    ({"type": None, "from_id": "a", "to_id": "b"}, "type", "enum"),
])
def test_create_body_is_validated_against_the_contract(s, body, field, reason):
    s.draft.kp("a")
    s.draft.kp("b")
    before = s.draft_revision()

    response = s.post(body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert {"in": "body", "field": field, "reason": reason} in payload["details"]["fields"]
    assert s.draft.relations == {} and s.draft_revision() == before and s.logs() == []


def test_self_loop_on_a_non_prerequisite_type_is_a_field_error(s):
    s.draft.kp("a")
    before = s.draft_revision()

    response = s.post({"type": "CONTAINS", "from_id": "a", "to_id": "a"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert {"in": "body", "field": "to_id", "reason": "self_loop"} in payload["details"]["fields"]
    assert s.draft.relations == {} and s.draft_revision() == before and s.logs() == []


def test_patch_into_a_self_loop_is_a_field_error(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("CONTAINS", "a", "b", manual=True)

    response = s.patch(rel_id, {"to_id": "a"})

    assert response.status_code == 422
    assert {"in": "body", "field": "to_id", "reason": "self_loop"} \
        in response.json()["details"]["fields"]
    assert rel_id in s.draft.relations


def test_create_body_must_be_an_object(s):
    response = s.post(["PREREQUISITE"])
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"


# --- PATCH：改类型、改端点、反转方向、恢复 rejected ----------------------------------------------


def test_patch_that_changes_direction_moves_the_relation_to_the_new_id(s):
    s.draft.kp("a")
    s.draft.kp("b")
    old = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    before = s.draft_revision()

    response = s.patch(old, {"from_id": "b", "to_id": "a"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert_schema("Relation", body)
    new = s.rel_id("PREREQUISITE", "b", "a")
    assert body["id"] == new and (body["from_id"], body["to_id"]) == ("b", "a")
    assert old not in s.draft.relations and set(s.draft.relations) == {new}
    assert s.draft_revision() == before + 1 and s.locks() == []
    [entry] = s.logs()
    assert (entry.action, entry.kp_id) == ("update", new)
    assert entry.summary["before"]["from_id"] == "a" and entry.summary["after"]["from_id"] == "b"


def test_patch_that_only_changes_status_keeps_the_identity_and_evidence(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("RELATED_TO", "a", "b", status="low_confidence", manual=False,
                          tasks=V, pairs=(json.dumps(["t-done", "ch-1"]),))
    before = s.draft_revision()

    response = s.patch(rel_id, {"status": "approved"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == rel_id and body["status"] == "approved" and body["source"] == "manual"
    assert s.draft.relations[rel_id]["props"]["source_pairs"] == [json.dumps(["t-done", "ch-1"])]
    assert s.draft.relations[rel_id]["props"]["revision"] == 2
    assert s.draft_revision() == before + 1


def test_patch_that_changes_nothing_does_not_write_or_log(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", status="approved", source="manual", manual=True)
    before = s.draft_revision()

    response = s.patch(rel_id, {"status": "approved"})

    assert response.status_code == 200
    assert response.json()["id"] == rel_id and response.json()["status"] == "approved"
    assert s.draft.relations[rel_id]["props"]["revision"] == 1
    assert s.draft_revision() == before and s.logs() == [] and s.draft.writes == []


def test_patch_from_related_to_back_to_prerequisite_detects_the_cycle(s):
    for kp in ("a", "b", "c"):
        s.draft.kp(kp)
    s.draft.edge("PREREQUISITE", "b", "c", manual=True)
    s.draft.edge("PREREQUISITE", "c", "a", manual=True)
    downgraded = s.draft.edge("RELATED_TO", "a", "b", status="low_confidence", source="ai", tasks=V)
    before = s.draft_revision()

    response = s.patch(downgraded, {"type": "PREREQUISITE"})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "CYCLE_DETECTED"
    cycle = body["details"]["cycle"]
    assert cycle[0] == cycle[-1] == "a" and set(cycle[:-1]) == {"a", "b", "c"}
    assert set(s.draft.relations) == {downgraded, s.rel_id("PREREQUISITE", "b", "c"),
                                      s.rel_id("PREREQUISITE", "c", "a")}
    assert s.draft_revision() == before and s.logs() == []


def test_patch_that_revives_a_rejected_prerequisite_rechecks_the_cycle(s):
    s.draft.kp("a")
    s.draft.kp("b")
    ab = s.draft.edge("PREREQUISITE", "a", "b", status="rejected", manual=True)
    s.draft.edge("PREREQUISITE", "b", "a", manual=True)
    before = s.draft_revision()

    response = s.patch(ab, {"status": "approved"})

    assert response.status_code == 409 and response.json()["code"] == "CYCLE_DETECTED"
    assert s.draft.relations[ab]["props"]["status"] == "rejected"
    assert s.draft_revision() == before and s.logs() == []


def test_patch_missing_or_invisible_relation_is_404_without_write(s):
    s.draft.kp("a")
    s.draft.kp("b")
    hidden = s.draft.edge("PREREQUISITE", "a", "b", tasks=("t-running",))
    before = s.draft_revision()

    for rid in ("rel_missing", hidden):
        response = s.patch(rid, {"status": "approved"})
        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert s.draft_revision() == before and s.logs() == [] and s.draft.writes == []


@pytest.mark.parametrize("body, field, reason", [
    ({}, "", "too_short"),
    ({"status": None}, "status", "null_forbidden"),
    ({"type": None}, "type", "null_forbidden"),
    ({"from_id": None}, "from_id", "null_forbidden"),
    ({"course_id": "other"}, "course_id", "extra_forbidden"),
    ({"id": "rel_x"}, "id", "extra_forbidden"),
    ({"revision": 2}, "revision", "extra_forbidden"),
    ({"status": "published"}, "status", "enum"),
    ({"type": "LIKES"}, "type", "enum"),
    ({"from_id": ""}, "from_id", "string_too_short"),
    ({"to_id": 7}, "to_id", "string_type"),
])
def test_patch_body_is_a_closed_editable_set(s, body, field, reason):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    before = s.draft_revision()

    response = s.patch(rel_id, body)

    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert {"in": "body", "field": field, "reason": reason} in payload["details"]["fields"]
    assert s.draft_revision() == before and s.logs() == [] and s.draft.writes == []


def test_patch_body_must_be_an_object(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    assert s.patch(rel_id, ["status"]).status_code == 422


# --- DELETE ------------------------------------------------------------------------------------


def test_delete_removes_the_relation_and_its_identity(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    before = s.draft_revision()

    response = s.delete(rel_id)

    assert response.status_code == 204 and response.content == b""
    assert s.draft.relations == {} and s.draft_revision() == before + 1 and s.locks() == []
    [entry] = s.logs()
    assert (entry.action, entry.kp_id, entry.state, entry.actor_id) == ("delete", rel_id, "committed",
                                                                       s.teacher.id)
    assert entry.summary["deleted"]["type"] == "PREREQUISITE"


def test_delete_missing_or_invisible_relation_is_404_and_writes_nothing(s):
    s.draft.kp("a")
    s.draft.kp("b")
    hidden = s.draft.edge("PREREQUISITE", "a", "b", tasks=("t-running",))
    before = s.draft_revision()

    for rid in ("rel_missing", hidden):
        response = s.delete(rid)
        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"

    assert s.draft_revision() == before and s.logs() == [] and s.draft.writes == []
    assert hidden in s.draft.relations


def test_delete_twice_succeeds_once(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    before = s.draft_revision()

    assert s.delete(rel_id).status_code == 204
    assert s.delete(rel_id).status_code == 404
    assert s.draft_revision() == before + 1 and len(s.logs()) == 1


# --- 鉴权 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("who, code", [("student", "ROLE_FORBIDDEN"), ("outsider", "COURSE_FORBIDDEN")])
@pytest.mark.parametrize("op", ["post", "patch", "delete"])
def test_only_course_teachers_can_write_relations(s, who, code, op):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    user = getattr(s, who)
    before = s.draft_revision()

    if op == "post":
        response = s.post({"type": "CONTAINS", "from_id": "a", "to_id": "b"}, user=user)
    elif op == "patch":
        response = s.patch(rel_id, {"status": "approved"}, user=user)
    else:
        response = s.delete(rel_id, user=user)

    assert response.status_code == 403 and response.json()["code"] == code
    assert s.draft.writes == [] and s.draft_revision() == before and s.logs() == []


@pytest.mark.parametrize("op", ["post", "patch", "delete"])
def test_unauthenticated_writes_are_401(s, op):
    rid = s.rel_id("PREREQUISITE", "a", "b")
    if op == "post":
        response = s.post({"type": "CONTAINS", "from_id": "a", "to_id": "b"}, user=None)
    elif op == "patch":
        response = s.patch(rid, {"status": "approved"}, user=None)
    else:
        response = s.delete(rid, user=None)
    assert response.status_code == 401


# --- 课程写锁与存储故障 --------------------------------------------------------------------------


@pytest.mark.parametrize("op", ["post", "patch", "delete"])
def test_busy_course_lock_is_409_course_busy_with_holder(s, op):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    _hold_lock(s, "publish")
    before = s.draft_revision()

    if op == "post":
        response = s.post({"type": "CONTAINS", "from_id": "a", "to_id": "b"})
    elif op == "patch":
        response = s.patch(rel_id, {"status": "approved"})
    else:
        response = s.delete(rel_id, user=s.teacher)

    assert response.status_code == 409
    assert response.json()["code"] == "COURSE_BUSY" and response.json()["details"] == {"holder": "publish"}
    assert s.draft.writes == [] and s.draft_revision() == before
    assert s.locks() == [(s.course.id, "publish")]


def test_writes_hold_the_lock_as_edit_and_release_it(s):
    s.draft.kp("a")
    s.draft.kp("b")
    seen = []
    store = s.client.app.state.relation_store
    original = store.transaction

    def spy(scope, work):
        seen.extend(s.locks())
        return original(scope, work)

    store.transaction = spy
    assert s.post({"type": "CONTAINS", "from_id": "a", "to_id": "b"}).status_code == 201
    assert seen == [(s.course.id, "edit")] and s.locks() == []


def test_neo4j_unavailable_is_503_and_releases_the_lock(s):
    s.draft.kp("a")
    s.draft.kp("b")
    s.draft.fail = True
    before = s.draft_revision()

    response = s.post({"type": "CONTAINS", "from_id": "a", "to_id": "b"})

    assert response.status_code == 503 and response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert s.locks() == [] and s.logs() == []
    assert s.draft_revision() == before  # 校验/写入之前的故障不加草稿修订号


def test_neo4j_unavailable_on_patch_and_delete_is_503(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    s.draft.fail = True
    assert s.patch(rel_id, {"status": "approved"}).status_code == 503
    assert s.delete(rel_id).status_code == 503
    assert rel_id in s.draft.relations


# --- 审计（F12）----------------------------------------------------------------------------------


@pytest.mark.parametrize("op", ["post", "patch", "delete"])
def test_a_rejected_write_bumps_nothing_and_logs_nothing(s, op):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    before = s.draft_revision()

    if op == "post":
        response = s.post({"type": "PREREQUISITE", "from_id": "b", "to_id": "a"})
    elif op == "patch":
        response = s.patch(rel_id, {"status": "published"})
    else:
        response = s.delete("rel_missing")

    assert response.status_code in (404, 409, 422)
    assert s.draft_revision() == before and s.logs() == [] and edit_logs.pending(s.url, s.course.id) == []


def test_audit_commit_failure_never_rolls_the_edit_back(s, monkeypatch, caplog):
    s.draft.kp("a")
    s.draft.kp("b")
    calls = {"n": 0}
    real = edit_logs.resolve

    def broken(*args, **kwargs):
        calls["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(edit_logs, "resolve", broken)
    response = s.post({"type": "PREREQUISITE", "from_id": "a", "to_id": "b"})

    assert response.status_code == 201, response.text
    rel_id = s.rel_id("PREREQUISITE", "a", "b")
    assert rel_id in s.draft.relations  # Neo4j 已提交：编辑不回滚
    assert calls["n"] == len(audit.RETRY_DELAYS) + 1  # 退避预算用尽后放弃
    [entry] = edit_logs.pending(s.url, s.course.id)
    assert (entry.action, entry.draft_revision) == ("create", s.draft_revision())
    assert "left pending for reconcile" in caplog.text

    monkeypatch.setattr(edit_logs, "resolve", real)  # SQLite 恢复：下一次写入先对账
    assert s.delete(rel_id).status_code == 204
    first, second = s.logs()
    assert (first.state, first.resolved_by) == ("committed", "reconcile")
    assert (second.state, second.resolved_by) == ("committed", "writer")


def test_reconcile_resolves_a_pending_relation_row_against_the_graph(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.rel_id("PREREQUISITE", "a", "b")
    assert s.post({"type": "PREREQUISITE", "from_id": "a", "to_id": "b"}).status_code == 201

    # 与写入前完全相同的状态：对账判定为已生效
    event_id, _ = edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action="create",
                                  kp_id=rel_id, kp_revision_before=None,
                                  summary={"entity": "relation", "after": {"type": "PREREQUISITE",
                                                                           "from_id": "a", "to_id": "b",
                                                                           "status": "approved",
                                                                           "source": "manual"}})
    assert audit.reconcile(_ctx(s), _scope(s)) == [(event_id, "committed")]

    # 摘要与图里的状态不符（写入其实没生效）：判定为未生效
    stale, _ = edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action="update",
                               kp_id=rel_id, kp_revision_before=None,
                               summary={"entity": "relation", "after": {"type": "PREREQUISITE",
                                                                        "from_id": "b", "to_id": "a",
                                                                        "status": "approved",
                                                                        "source": "manual"}})
    assert audit.reconcile(_ctx(s), _scope(s)) == [(stale, "aborted")]


def test_reconcile_treats_a_deleted_relation_row_as_applied_once_it_is_gone(s):
    s.draft.kp("a")
    s.draft.kp("b")
    rel_id = s.draft.edge("PREREQUISITE", "a", "b", manual=True)
    event_id, _ = edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action="delete",
                                  kp_id=rel_id, kp_revision_before=None,
                                  summary={"entity": "relation", "deleted": {"type": "PREREQUISITE"}})
    assert audit.reconcile(_ctx(s), _scope(s)) == [(event_id, "aborted")]
    del s.draft.relations[rel_id]
    again, _ = edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action="delete",
                               kp_id=rel_id, kp_revision_before=None,
                               summary={"entity": "relation", "deleted": {"type": "PREREQUISITE"}})
    assert audit.reconcile(_ctx(s), _scope(s)) == [(again, "committed")]


def _scope(s):
    from app.repositories.neo4j import GraphScope
    return GraphScope(s.course.id, "draft", effective_task_ids=V)


def _ctx(s):
    from types import SimpleNamespace
    return SimpleNamespace(sqlite_url=s.url, store=s.client.app.state.relation_store, actor_id=s.teacher.id)


# --- 契约注册 -----------------------------------------------------------------------------------


def test_routes_are_registered_with_the_contract_operation_ids(s):
    paths = s.client.app.openapi()["paths"]
    assert paths["/api/v1/courses/{cid}/relations"]["post"]["operationId"] == "createRelation"
    assert paths["/api/v1/courses/{cid}/relations/{rid}"]["patch"]["operationId"] == "updateRelation"
    assert paths["/api/v1/courses/{cid}/relations/{rid}"]["delete"]["operationId"] == "deleteRelation"
