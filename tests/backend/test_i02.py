"""I02 掌握标记 API：``GET``/``PUT /api/v1/courses/{cid}/progress``，连真实迁移后的 SQLite 与真实应用。

验收（docs/atomic-tasks.json I02）：拒绝请求冒用他人 ``user_id``；改标后可重算；不能标草稿独有点。
另覆盖 specs/learning-path.md §5 的读时投影（LP-8、LP-9、LP-16～LP-20）、ADR-017 决定 4/5 的错误形状、
课程隔离与发布指针变化后的整批复核。已提交版本经 G04/G06 仓储真实提交，不直接改表（完整性用例除外）。
"""

from __future__ import annotations

import copy
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from app.api import progress as progress_api
from app.main import create_app
from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.progress import read_progress
from app.repositories.sqlite import connect, database_path, migrate
from app.services.auth import issue_access_token
from app.services.learning import progress as service
from app.services.learning.eligible import build_prerequisite_graph, eligible_set
from app.services.versions import resolver
from app.services.versions.resolver import resolve_published
from app.services.versions.snapshot import DraftGraph, DraftNode, Revision, build_snapshot

ROOT = Path(__file__).resolve().parents[2]
SECRET = "i02-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
EXCLUDED = {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0}

_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {key: (value.replace("#/components/schemas/", "#/$defs/")
                      if key == "$ref" and isinstance(value, str) else _rewrite(value))
                for key, value in node.items()}
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def assert_schema(name, instance):
    jsonschema.Draft202012Validator({"$defs": _DEFS, "$ref": f"#/$defs/{name}"}).validate(instance)


def token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=int(time.time()),
                              ttl_seconds=3600)


def _account(url, username, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=username, password_hash=VALID_HASH, role=role)


class Env:
    def __init__(self, client, url, teacher, alice, bob, outsider, course, other):
        self.client, self.url = client, url
        self.teacher, self.alice, self.bob, self.outsider = teacher, alice, bob, outsider
        self.course, self.other = course, other

    def get(self, user, course=None):
        return self.client.get(f"/api/v1/courses/{course or self.course}/progress", headers=self._auth(user))

    def put(self, user, body, course=None, query=""):
        return self.client.put(f"/api/v1/courses/{course or self.course}/progress{query}", json=body,
                               headers=self._auth(user))

    @staticmethod
    def _auth(user):
        return {} if user is None else {"Authorization": f"Bearer {token(user)}"}

    def publish(self, *nodes, course=None):
        return publish(self.url, course or self.course, self.teacher, *nodes)

    def rollback(self, source_version, course=None):
        course = course or self.course
        attempt = versions.begin_attempt(self.url, course, kind="rollback", created_by=self.teacher.id,
                                         lease_seconds=60, source_version=source_version)
        assert versions.mark_materialized(self.url, attempt.version_id)
        with versions.immediate(self.url) as db:
            return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer(self.url, course),
                                           published_from_revision=1)

    def rows(self, user):
        return {row.kp_id: row for row in read_progress(self.url, user_id=user.id, course_id=self.course)}

    def sequence(self):
        with connect(self.url) as db:
            return db.execute("SELECT value FROM commit_sequence").fetchone()[0]


def pointer(url, course_id):
    with connect(url) as db:
        return db.execute("SELECT published_version_id FROM courses WHERE id = ?", (course_id,)).fetchone()[0]


def node(spec):
    """``"a"`` 或 ``("b", ("a",))``：节点及其展平谱系。"""
    kp_id, merged = (spec, ()) if isinstance(spec, str) else spec
    return DraftNode(kp_id=kp_id, name=f"点{kp_id}", type="concept", definition="定义", status="approved",
                     source_refs=("ch-1",), merged_from=merged)


def publish(url, course_id, teacher, *nodes):
    revision = Revision("rev-1", "mat-1", "sha256:" + "a" * 64, "txt/1+chunk/1@1500-200")
    draft = DraftGraph(course_id, [revision], [], [node(n) for n in nodes], [], {"ch-1": "rev-1"})
    snap = build_snapshot(draft).snapshot
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=teacher.id, lease_seconds=60)
    assert versions.record_snapshot(url, attempt.version_id, snapshot=snap.canonical, digest=snap.digest,
                                    node_count=len(nodes), edge_count=0, excluded=EXCLUDED, draft_revision=1,
                                    task_watermark=0, embedding_space="bge-m3@1024")
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer(url, course_id),
                                       published_from_revision=1)


@pytest.fixture(autouse=True)
def fresh_cache():
    resolver.clear_cache()
    service.clear_cache()
    yield
    resolver.clear_cache()
    service.clear_cache()


@pytest.fixture
def env(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    alice = _account(url, "alice01", "student")
    bob = _account(url, "bob0001", "student")
    outsider = _account(url, "carol01", "student")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    other = create_course(url, name="他课", description=None, creator_id=teacher.id)
    for student in (alice, bob):
        add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
        add_member(url, course_id=other.id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    with TestClient(create_app()) as client:
        yield Env(client, url, teacher, alice, bob, outsider, course.id, other.id)


def entries(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert_schema("ProgressResponse", body)
    return {entry["kp_id"]: entry for entry in body["entries"]}


def statuses(response):
    return {kp_id: entry["status"] for kp_id, entry in entries(response).items()}


def assert_not_in_published(response, indices, graph_version):
    assert response.status_code == 422, response.text
    body = response.json()
    assert_schema("ProgressValidationError", body)
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"] == {
        "fields": [{"in": "body", "field": f"{i}.kp_id", "reason": "not_in_published_version"} for i in indices],
        "graph_version": graph_version,
    }


# --- 鉴权与路由 ------------------------------------------------------------------------------


def test_access_rules(env):
    assert env.get(None).status_code == 401
    assert env.put(None, [{"kp_id": "a", "status": "mastered"}]).status_code == 401
    unpublished = env.get(env.alice)
    assert (unpublished.status_code, unpublished.json()["code"]) == (404, "GRAPH_NOT_PUBLISHED")
    assert env.put(env.alice, [{"kp_id": "a", "status": "mastered"}]).json()["code"] == "GRAPH_NOT_PUBLISHED"
    env.publish("a")
    assert env.get(env.outsider).json()["code"] == "COURSE_FORBIDDEN"
    assert env.get(env.teacher).json()["code"] == "ROLE_FORBIDDEN"
    assert env.put(env.teacher, [{"kp_id": "a", "status": "mastered"}]).status_code == 403
    assert env.rows(env.alice) == {}


def test_get_lists_every_node_of_the_published_version(env):
    env.publish("b", "a", "c")
    response = env.get(env.alice)
    assert response.json()["graph_version"] == 1
    assert list(entries(response)) == ["a", "b", "c"]
    assert entries(response)["a"] == {"kp_id": "a", "status": "unknown", "own_status": None,
                                      "inherited_from": [], "updated_at": None}


# --- 验收 1：拒绝冒用他人 user_id ------------------------------------------------------------


def test_body_user_id_is_rejected_with_zero_writes(env):
    env.publish("a", "b")
    response = env.put(env.alice, [{"kp_id": "a", "status": "mastered"},
                                   {"kp_id": "b", "status": "mastered", "user_id": env.bob.id}])
    assert response.status_code == 422
    assert response.json()["details"]["fields"] == [{"in": "body", "field": "1.user_id", "reason": "extra_forbidden"}]
    assert env.rows(env.alice) == {} and env.rows(env.bob) == {}
    assert env.sequence() == 1  # 仅发布占用的提交序号


def test_query_user_id_cannot_redirect_the_write(env):
    env.publish("a")
    response = env.put(env.alice, [{"kp_id": "a", "status": "mastered"}], query=f"?user_id={env.bob.id}")
    assert statuses(response) == {"a": "mastered"}
    assert env.rows(env.bob) == {}
    assert env.rows(env.alice)["a"].status == "mastered"
    assert statuses(env.get(env.bob)) == {"a": "unknown"}


def test_students_and_courses_are_isolated(env):
    env.publish("a")
    env.publish("a", course=env.other)
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])
    assert statuses(env.get(env.bob)) == {"a": "unknown"}
    assert statuses(env.get(env.alice, course=env.other)) == {"a": "unknown"}


# --- 验收 2：改标后可重算 --------------------------------------------------------------------


def test_remarking_recomputes_projection_and_eligible_set(env):
    env.publish("a", "b")
    graph = build_prerequisite_graph(["a", "b"], [("a", "b")])

    def eligible():
        bound = resolve_published(env.url, env.course)
        return eligible_set(graph, service.project_progress(env.url, env.alice.id, bound).mastered)

    assert eligible() == ("a",)
    first = entries(env.put(env.alice, [{"kp_id": "a", "status": "mastered"}]))
    assert first["a"]["status"] == "mastered" and first["a"]["updated_at"] is not None
    assert eligible() == ("b",)
    second = entries(env.put(env.alice, [{"kp_id": "a", "status": "learning"}]))
    assert (second["a"]["status"], second["a"]["own_status"]) == ("learning", "learning")
    assert eligible() == ("a",)
    assert statuses(env.get(env.alice)) == {"a": "learning", "b": "unknown"}


def test_same_value_replay_without_sources_is_a_no_op(env):
    env.publish("a")
    first = entries(env.put(env.alice, [{"kp_id": "a", "status": "mastered"}]))
    seq = env.sequence()
    second = entries(env.put(env.alice, [{"kp_id": "a", "status": "mastered"}]))
    assert second == first and env.sequence() == seq


def test_valid_batch_is_written_in_one_transaction(env):
    env.publish("a", "b", "c")
    response = env.put(env.alice, [{"kp_id": "c", "status": "learning"}, {"kp_id": "a", "status": "mastered"}])
    assert statuses(response) == {"a": "mastered", "b": "unknown", "c": "learning"}
    assert {kp: row.status for kp, row in env.rows(env.alice).items()} == {"a": "mastered", "c": "learning"}


# --- 验收 3：不能标草稿独有点 ----------------------------------------------------------------


def test_draft_only_node_is_rejected_with_zero_writes(env):
    env.publish("a")  # 草稿里另有 draft-only，但未发布
    response = env.put(env.alice, [{"kp_id": "a", "status": "mastered"}, {"kp_id": "draft-only", "status": "learning"}])
    assert_not_in_published(response, [1], 1)
    assert env.rows(env.alice) == {} and env.sequence() == 1


def test_other_course_node_gets_the_same_reason(env):
    env.publish("a")
    env.publish("foreign", course=env.other)
    assert_not_in_published(env.put(env.alice, [{"kp_id": "foreign", "status": "mastered"}]), [0], 1)
    assert env.rows(env.alice) == {}


def test_batch_shape_errors_are_generic_validation_errors(env):
    env.publish("a", "b")
    duplicate = env.put(env.alice, [{"kp_id": "a", "status": "mastered"}, {"kp_id": "b", "status": "learning"},
                                    {"kp_id": "a", "status": "learning"}])
    assert duplicate.status_code == 422
    assert duplicate.json()["details"] == {"fields": [{"in": "body", "field": "2.kp_id", "reason": "duplicate"}]}
    assert_schema("ProgressValidationError", duplicate.json())
    for body in ([], [{"kp_id": "a", "status": "skipped"}], [{"kp_id": "", "status": "mastered"}], {"kp_id": "a"}):
        response = env.put(env.alice, body)
        assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert env.rows(env.alice) == {} and env.sequence() == 1


# --- 版本变化（LP-8、LP-16） ------------------------------------------------------------------


def test_deleted_node_is_rejected_and_its_row_stays_dormant(env):
    env.publish("a", "b")
    env.put(env.alice, [{"kp_id": "b", "status": "mastered"}])
    env.publish("a", "c")
    assert statuses(env.get(env.alice)) == {"a": "unknown", "c": "unknown"}
    assert_not_in_published(env.put(env.alice, [{"kp_id": "b", "status": "learning"}]), [0], 2)
    assert env.rows(env.alice)["b"].status == "mastered"
    env.rollback(1)
    response = env.get(env.alice)
    assert response.json()["graph_version"] == 3
    assert statuses(response) == {"a": "unknown", "b": "mastered"}


def test_pointer_moved_since_the_last_read_is_rechecked_as_a_whole(env):
    env.publish("a", "b")
    assert env.get(env.alice).json()["graph_version"] == 1
    env.publish("a", "c")
    assert_not_in_published(env.put(env.alice, [{"kp_id": "a", "status": "mastered"},
                                                {"kp_id": "b", "status": "mastered"}]), [1], 2)
    assert env.rows(env.alice) == {}
    response = env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])
    assert response.json()["graph_version"] == 2


def test_put_binds_the_pointer_inside_its_write_transaction(env, monkeypatch):
    """请求开始后才提交的版本也要用于复核：服务在写事务内解析指针，而不是沿用请求前的绑定。

    本用例只说明「复核用的是请求开始后的新版本」；「解析时确实持有写锁」的鉴别性证据见
    ``test_put_rechecks_the_pointer_while_holding_the_write_lock``。
    """
    env.publish("a", "b")
    seen = []
    original = service.resolve_published

    def spy(url, course_id, **kwargs):
        with connect(url) as db:
            seen.append(db.execute("SELECT count(*) FROM graph_versions").fetchone()[0])
        return original(url, course_id, **kwargs)

    monkeypatch.setattr(service, "resolve_published", spy)
    env.publish("a")
    assert_not_in_published(env.put(env.alice, [{"kp_id": "b", "status": "mastered"}]), [0], 2)
    assert seen == [2]


def test_put_rechecks_the_pointer_while_holding_the_write_lock(env, monkeypatch):
    """写事务内复核发布指针的鉴别性证据：解析指针时调用方必须已持有写锁。

    上一个用例的 ``seen == [2]`` 在锁内锁外都成立（恒真）。这里换判据：在 ``resolve_published``
    的调用点另开一个连接尝试 ``BEGIN IMMEDIATE``——写锁已被 ``update_progress`` 持有则立即以
    ``database is locked`` 失败；把 ``resolve_published`` 移到 ``with immediate`` 之外，该连接
    就能拿到写锁，``blocked`` 为空，用例失败。``timeout=0`` 让判定不依赖睡眠或竞态。
    """
    env.publish("a", "b")
    blocked: list[str] = []
    original = service.resolve_published

    def spy(url, course_id, **kwargs):
        with closing(sqlite3.connect(database_path(url), timeout=0)) as rival:
            try:
                rival.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                blocked.append(str(error))
            else:
                rival.execute("ROLLBACK")
        return original(url, course_id, **kwargs)

    monkeypatch.setattr(service, "resolve_published", spy)
    env.publish("a")  # 请求开始后发布指针从版本 1 移到 2
    assert_not_in_published(env.put(env.alice, [{"kp_id": "b", "status": "mastered"}]), [0], 2)
    assert blocked and all("locked" in text for text in blocked), (
        f"写事务内复核发布指针时未持有写锁：并发 BEGIN IMMEDIATE 全部成功（blocked={blocked}）")


# --- 合并继承与显式写入覆盖（LP-9、LP-17～LP-20） ---------------------------------------------


def test_lp17_lp18_inheritance_and_explicit_override(env):
    env.publish("a", "b")
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])
    env.publish(("b", ("a",)))
    b = entries(env.get(env.alice))["b"]
    assert b == {"kp_id": "b", "status": "mastered", "own_status": None,
                 "inherited_from": [{"kp_id": "a", "status": "mastered"}], "updated_at": None}
    b = entries(env.put(env.alice, [{"kp_id": "b", "status": "unknown"}]))["b"]
    assert (b["status"], b["own_status"], b["inherited_from"]) == ("unknown", "unknown", [])
    assert env.rows(env.alice)["a"].status == "mastered"


def test_lp18_same_value_write_overrides_then_replays_as_no_op(env):
    env.publish("a", "b")
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}, {"kp_id": "b", "status": "unknown"}])
    env.publish(("b", ("a",)))
    b = entries(env.get(env.alice))["b"]
    assert (b["status"], b["own_status"], [s["kp_id"] for s in b["inherited_from"]]) == ("mastered", "unknown", ["a"])
    before = env.rows(env.alice)["b"]
    first = entries(env.put(env.alice, [{"kp_id": "b", "status": "unknown"}]))
    after = env.rows(env.alice)["b"]
    assert after.write_seq > before.write_seq
    assert (first["b"]["status"], first["b"]["inherited_from"]) == ("unknown", [])
    seq = env.sequence()
    replay = entries(env.put(env.alice, [{"kp_id": "b", "status": "unknown"}]))
    assert replay == first and env.sequence() == seq and env.rows(env.alice)["b"] == after


def test_lp9_primary_written_before_merge_takes_the_highest(env):
    env.publish("a", "b", "c")
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}, {"kp_id": "b", "status": "learning"}])
    env.publish(("b", ("a",)), "c")
    assert entries(env.get(env.alice))["b"]["status"] == "mastered"
    env.publish(("c", ("a", "b")))  # A→B→C 链式合并，谱系已展平
    c = entries(env.get(env.alice))["c"]
    assert c["status"] == "mastered"
    assert c["inherited_from"] == [{"kp_id": "a", "status": "mastered"}, {"kp_id": "b", "status": "learning"}]
    env.rollback(1)  # A 重现：各用自身记录
    assert statuses(env.get(env.alice)) == {"a": "mastered", "b": "learning", "c": "unknown"}


def test_lp19_merge_target_deleted_leaves_sources_dormant(env):
    env.publish("a", "b", "c")
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])
    env.publish(("b", ("a",)), "c")
    env.publish("c")
    assert entries(env.get(env.alice)) == {"c": {"kp_id": "c", "status": "unknown", "own_status": None,
                                                 "inherited_from": [], "updated_at": None}}
    assert env.rows(env.alice)["a"].status == "mastered"


def test_lp20_remerge_restarts_the_override_bound(env):
    env.publish("a", "b")                              # v1
    env.publish(("b", ("a",)))                         # v2
    env.put(env.alice, [{"kp_id": "b", "status": "unknown"}])
    env.rollback(1)                                    # v3：A 重现
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])
    assert statuses(env.get(env.alice)) == {"a": "mastered", "b": "unknown"}
    env.publish(("b", ("a",)))                         # v4：重新起算
    b = entries(env.get(env.alice))["b"]
    assert (b["status"], b["inherited_from"]) == ("mastered", [{"kp_id": "a", "status": "mastered"}])
    b = entries(env.put(env.alice, [{"kp_id": "b", "status": "unknown"}]))["b"]
    assert (b["status"], b["inherited_from"]) == ("unknown", [])


def test_merge_source_is_not_writable_once_merged(env):
    env.publish("a", "b")
    env.publish(("b", ("a",)))
    assert_not_in_published(env.put(env.alice, [{"kp_id": "a", "status": "mastered"}]), [0], 2)


# --- 完整性与脏行 ----------------------------------------------------------------------------


def test_dirty_row_is_ignored_with_a_warning(env, caplog):
    env.publish("a")
    with connect(env.url) as db:
        db.execute("UPDATE commit_sequence SET value = value + 1")
        db.execute("INSERT INTO learning_progress VALUES (?, ?, 'ghost', 'mastered', '2026-01-01T00:00:00Z', 2)",
                   (env.alice.id, env.course))
    assert statuses(env.get(env.alice)) == {"a": "unknown"}
    assert "ghost" in caplog.text and "diagnostic_id=" in caplog.text


def test_integrity_fault_is_500_with_request_id_only(env, caplog):
    version = env.publish("a")
    with connect(env.url) as db:
        db.execute("DROP TRIGGER graph_versions_committed_frozen")
        db.execute("UPDATE graph_versions SET digest = ? WHERE version_id = ?", ("sha256:" + "0" * 64, version.version_id))
    for response in (env.get(env.alice), env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])):
        assert response.status_code == 500
        body = response.json()
        assert_schema("LearningIntegrityError", body)
        assert set(body["details"]) == {"request_id"}
        assert body["details"]["request_id"] in caplog.text
    assert env.rows(env.alice) == {}


def test_serialisation_fault_is_500_with_request_id_only(env, monkeypatch, caplog):
    """投影无法序列化时不能逃出处理器：500 `INTERNAL_ERROR`，`details` 只含 `request_id`。"""
    env.publish("a")

    class Broken:
        @staticmethod
        def model_validate(value):
            raise ValueError("projection is not serialisable")

    monkeypatch.setattr(progress_api, "ProgressResponse", Broken)
    response = env.get(env.alice)
    assert response.status_code == 500, response.text
    body = response.json()
    assert_schema("Error", body)
    assert body["code"] == "INTERNAL_ERROR"
    assert set(body["details"]) == {"request_id"}
    assert body["details"]["request_id"] in caplog.text


def test_override_bound_is_the_start_of_the_continuous_merge(env):
    """合并跨多个版本持续时，界 T 取连续归属的起算版本，而非绑定版本：v2 后写 B 在 v3 仍覆盖 A。"""
    env.publish("a", "b", "c")                         # v1
    env.put(env.alice, [{"kp_id": "a", "status": "mastered"}])
    env.publish(("b", ("a",)), "c")                    # v2：合并起算
    env.put(env.alice, [{"kp_id": "b", "status": "learning"}])
    env.publish(("b", ("a",)))                         # v3：合并延续，另删 C
    b = entries(env.get(env.alice))["b"]
    assert (b["status"], b["inherited_from"]) == ("learning", [])


def test_invalid_lineage_in_the_bound_version_is_an_integrity_fault(env):
    """修订 3 决定 16：来源是本版本节点（含自身）属于已提交版损坏；不输出部分进度。"""
    import json

    from app.services.versions.snapshot import digest_of

    version = env.publish("a", "b")
    raw = json.loads(versions.read_snapshot(env.url, version.version_id))
    raw["nodes"][1]["merged_from"] = ["a"]
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with connect(env.url) as db:
        db.execute("DROP TRIGGER graph_versions_committed_frozen")
        db.execute("UPDATE graph_versions SET snapshot_json = ?, digest = ? WHERE version_id = ?",
                   (canonical.decode("utf-8"), digest_of(canonical), version.version_id))
    response = env.get(env.alice)
    assert (response.status_code, response.json()["code"]) == (500, "INTERNAL_ERROR")
    assert set(response.json()["details"]) == {"request_id"}
