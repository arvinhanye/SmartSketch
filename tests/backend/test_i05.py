"""I05 推荐查询 API：``GET /api/v1/courses/{cid}/recommend``，连真实迁移后的 SQLite 与真实应用。

验收（docs/atomic-tasks.json I05）：请求全程同版本；截断稳定；未发布 404 与全掌握区别；已提交图损坏 5xx；
有环明确错误。另覆盖 specs/learning-path.md LP-1、LP-2、LP-6、LP-9、LP-10、LP-11、LP-12、LP-13 的接口面，
``limit`` 边界、权重来自启动配置、课程隔离与契约形状。已提交版本经 G04 仓储真实提交，只有完整性用例直接改表。
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from app.api import recommend as recommend_api
from app.main import create_app
from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.learning import progress as progress_service
from app.services.learning import recommend as service
from app.services.versions import resolver
from app.services.versions.snapshot import (
    DraftChapter,
    DraftEdge,
    DraftGraph,
    DraftNode,
    Revision,
    build_snapshot,
    digest_of,
)

ROOT = Path(__file__).resolve().parents[2]
SECRET = "i05-test-signing-key-0123456789abcdefghijkl"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
EXCLUDED = {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0}
WEIGHT_NAMES = ("RECOMMEND_WEIGHT_UNLOCK", "RECOMMEND_WEIGHT_IMPORTANCE", "RECOMMEND_WEIGHT_CHAPTER",
                "RECOMMEND_WEIGHT_EASE")

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


def kp(kp_id, *, chapter=None, importance=None, difficulty=None, merged=()):
    return DraftNode(kp_id=kp_id, name=f"点{kp_id}", type="concept", definition="定义", status="approved",
                     chapter_id=chapter, importance=importance, difficulty=difficulty, source_refs=("ch-1",),
                     merged_from=merged)


def pre(source, target, rel_type="PREREQUISITE"):
    return DraftEdge(rel_id=f"r-{source}-{target}-{rel_type}", type=rel_type, from_id=source, to_id=target,
                     status="approved", source_refs=("ch-1",))


def pointer(url, course_id):
    with connect(url) as db:
        return db.execute("SELECT published_version_id FROM courses WHERE id = ?", (course_id,)).fetchone()[0]


def publish(url, course_id, teacher, nodes, edges=(), chapters=()):
    nodes = [kp(n) if isinstance(n, str) else n for n in nodes]
    revision = Revision("rev-1", "mat-1", "sha256:" + "a" * 64, "txt/1+chunk/1@1500-200")
    draft = DraftGraph(course_id, [revision], list(chapters), nodes, list(edges), {"ch-1": "rev-1"})
    snap = build_snapshot(draft).snapshot
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=teacher.id, lease_seconds=60)
    assert versions.record_snapshot(url, attempt.version_id, snapshot=snap.canonical, digest=snap.digest,
                                    node_count=len(nodes), edge_count=len(edges), excluded=EXCLUDED,
                                    draft_revision=1, task_watermark=0, embedding_space="bge-m3@1024")
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer(url, course_id),
                                       published_from_revision=1)


class Env:
    def __init__(self, client, url, teacher, alice, bob, outsider, course, other):
        self.client, self.url = client, url
        self.teacher, self.alice, self.bob, self.outsider = teacher, alice, bob, outsider
        self.course, self.other = course, other

    @staticmethod
    def _auth(user):
        return {} if user is None else {"Authorization": f"Bearer {token(user)}"}

    def get(self, user, course=None, query=""):
        return self.client.get(f"/api/v1/courses/{course or self.course}/recommend{query}", headers=self._auth(user))

    def mark(self, user, statuses, course=None):
        body = [{"kp_id": kp_id, "status": status} for kp_id, status in statuses.items()]
        response = self.client.put(f"/api/v1/courses/{course or self.course}/progress", json=body,
                                   headers=self._auth(user))
        assert response.status_code == 200, response.text

    def publish(self, nodes, edges=(), chapters=(), course=None):
        return publish(self.url, course or self.course, self.teacher, nodes, edges, chapters)

    def tamper(self, version, change):
        """改写已提交快照并重算摘要（模拟已提交版损坏；需先拆掉冻结触发器）。"""
        raw = json.loads(versions.read_snapshot(self.url, version.version_id))
        change(raw)
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with connect(self.url) as db:
            db.execute("DROP TRIGGER IF EXISTS graph_versions_committed_frozen")
            db.execute("UPDATE graph_versions SET snapshot_json = ?, digest = ? WHERE version_id = ?",
                       (canonical.decode("utf-8"), digest_of(canonical), version.version_id))


@pytest.fixture(autouse=True)
def fresh_cache():
    for module in (resolver, progress_service, service):
        module.clear_cache()
    yield
    for module in (resolver, progress_service, service):
        module.clear_cache()


def _env(tmp_path, monkeypatch, weights=None):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    alice = _account(url, "alice01", "student")
    bob = _account(url, "bob0001", "student")
    outsider = _account(url, "carol01", "student")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    other = create_course(url, name="他课", description=None, creator_id=teacher.id)
    for student in (alice, bob):
        for course_id in (course.id, other.id):
            add_member(url, course_id=course_id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    for name in WEIGHT_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in zip(WEIGHT_NAMES, weights or ()):
        monkeypatch.setenv(name, value)
    return url, teacher, alice, bob, outsider, course.id, other.id


@pytest.fixture
def env(tmp_path, monkeypatch):
    url, *rest = _env(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        yield Env(client, url, *rest)


def body_of(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert_schema("RecommendResponse", body)
    return body


def ids(response):
    return [item["kp_id"] for item in body_of(response)["recommendations"]]


def assert_integrity_500(response, caplog, *log_fragments):
    assert response.status_code == 500, response.text
    body = response.json()
    assert_schema("LearningIntegrityError", body)
    assert body["code"] == "INTERNAL_ERROR"
    assert set(body["details"]) == {"request_id"}
    assert body["details"]["request_id"] in caplog.text
    for fragment in log_fragments:
        assert fragment in caplog.text
        assert fragment not in response.text  # 内部 ID/环路只进日志


# --- 鉴权、未发布与全掌握 ---------------------------------------------------------------------


def test_access_rules_and_unpublished_is_404(env):
    assert env.get(None).status_code == 401
    unpublished = env.get(env.alice)
    assert (unpublished.status_code, unpublished.json()["code"]) == (404, "GRAPH_NOT_PUBLISHED")
    env.publish(["a"])
    assert env.get(env.outsider).json()["code"] == "COURSE_FORBIDDEN"
    assert env.get(env.teacher).json()["code"] == "ROLE_FORBIDDEN"
    assert body_of(env.get(env.alice))["state"] == "recommendations"


def test_all_mastered_is_a_200_empty_state_distinct_from_unpublished(env):
    env.publish(["a", "b"], [pre("a", "b")])
    env.mark(env.alice, {"a": "mastered", "b": "mastered"})
    body = body_of(env.get(env.alice))
    assert body == {"state": "all_mastered", "graph_version": 1, "total_eligible": 0, "recommendations": []}
    other = env.get(env.alice, course=env.other)
    assert (other.status_code, other.json()["code"]) == (404, "GRAPH_NOT_PUBLISHED")


def test_learning_does_not_count_as_mastered(env):
    env.publish(["a", "b"], [pre("a", "b")])
    env.mark(env.alice, {"a": "learning", "b": "mastered"})
    body = body_of(env.get(env.alice))
    assert (body["state"], [r["kp_id"] for r in body["recommendations"]]) == ("recommendations", ["a"])


# --- 推荐内容 --------------------------------------------------------------------------------


def test_lp1_only_nodes_with_all_direct_prerequisites_mastered(env):
    env.publish(["a", "b", "c", "d"], [pre("a", "b"), pre("b", "c")])
    assert sorted(ids(env.get(env.alice))) == ["a", "d"]
    env.mark(env.alice, {"a": "mastered"})
    assert sorted(ids(env.get(env.alice))) == ["b", "d"]
    env.mark(env.alice, {"a": "unknown"})  # 改标后重算
    assert sorted(ids(env.get(env.alice))) == ["a", "d"]


def test_lp2_lp13_unlock_count_and_reason(env):
    env.publish(["a", "b", "c"], [pre("a", "c"), pre("b", "c")])
    body = body_of(env.get(env.alice))
    assert {r["kp_id"]: r["unlock_count"] for r in body["recommendations"]} == {"a": 0, "b": 0}
    env.mark(env.alice, {"b": "mastered"})
    [item] = body_of(env.get(env.alice))["recommendations"]
    assert (item["kp_id"], item["unlock_count"], item["factors"]["unlock"]) == ("a", 1, 1.0)
    assert item["reason_facts"]["primary_factor"] == "unlock"
    assert item["reason"] == "完成该点可立即解锁 1 个知识点（解锁度 1.0000）"


def test_item_shape_score_rebuilds_bitwise_and_version_is_repeated(env):
    chapters = [DraftChapter("c1", "第一章", 1), DraftChapter("c2", "第二章", 2)]
    env.publish([kp("a", chapter="c1", importance=0.8, difficulty=0.3), kp("b", chapter="c2"), "c"],
                [pre("a", "b"), pre("c", "b", "RELATED_TO")], chapters)
    body = body_of(env.get(env.alice))
    assert (body["graph_version"], body["total_eligible"]) == (1, 2)
    for item in body["recommendations"]:
        w = item["weighted"]
        assert item["score"] == ((w["unlock"] + w["importance"]) + w["chapter_order"]) + w["ease"]
        assert item["graph_version"] == 1
    a = next(r for r in body["recommendations"] if r["kp_id"] == "a")
    assert a["name"] == "点a"
    assert a["reason_facts"] | {"primary_factor": None} == {
        "primary_factor": None, "chapter_id": "c1", "chapter_name": "第一章", "chapter_rank": 0,
        "importance": 0.8, "centrality": 0.5, "difficulty": 0.3}
    assert a["factors"] == {"unlock": 1.0, "importance": 0.65, "chapter_order": 1.0, "ease": 0.7}
    c = next(r for r in body["recommendations"] if r["kp_id"] == "c")
    assert c["reason_facts"]["centrality"] == 0.0  # RELATED_TO 不参与
    assert c["reason_facts"]["chapter_id"] is None and c["factors"]["chapter_order"] == 0.0


def test_lp9_recommendation_uses_the_same_projection_as_progress(env):
    env.publish(["a", "b", "c"], [pre("b", "c")])
    env.mark(env.alice, {"a": "mastered"})
    env.publish([kp("b", merged=("a",)), "c"], [pre("b", "c")])  # v2：A 并入 B
    body = body_of(env.get(env.alice))
    assert (body["graph_version"], [r["kp_id"] for r in body["recommendations"]]) == (2, ["c"])


def test_students_and_courses_are_isolated(env):
    env.publish(["a", "b"], [pre("a", "b")])
    env.publish(["a", "b"], [pre("a", "b")], course=env.other)
    env.mark(env.alice, {"a": "mastered"}, course=env.other)
    env.mark(env.bob, {"a": "mastered"})
    assert ids(env.get(env.alice)) == ["a"]
    assert ids(env.get(env.alice, course=env.other)) == ["b"]
    assert ids(env.get(env.bob)) == ["b"]
    # 身份只取自已认证会话：查询串里的 user_id 不被信任
    assert ids(env.get(env.alice, query=f"?user_id={env.bob.id}")) == ["a"]


def test_dirty_and_dormant_rows_do_not_break_the_read(env, caplog):
    env.publish(["a", "b"])
    env.mark(env.alice, {"b": "mastered"})
    env.publish(["a"])  # B 删除：dormant
    with connect(env.url) as db:
        db.execute("UPDATE commit_sequence SET value = value + 1")
        db.execute("INSERT INTO learning_progress VALUES (?, ?, 'ghost', 'mastered', '2026-01-01T00:00:00Z', "
                   "(SELECT value FROM commit_sequence))", (env.alice.id, env.course))
    body = body_of(env.get(env.alice))
    assert (body["graph_version"], [r["kp_id"] for r in body["recommendations"]]) == (2, ["a"])
    assert "ghost" in caplog.text


# --- limit 与截断 ----------------------------------------------------------------------------


def test_limit_defaults_to_ten_and_total_eligible_counts_before_truncation(env):
    env.publish([f"k{i:02d}" for i in range(13)])
    body = body_of(env.get(env.alice))
    assert (len(body["recommendations"]), body["total_eligible"]) == (10, 13)
    assert len(body_of(env.get(env.alice, query="?limit=50"))["recommendations"]) == 13
    assert len(body_of(env.get(env.alice, query="?limit=1"))["recommendations"]) == 1


@pytest.mark.parametrize("query", ["?limit=0", "?limit=51", "?limit=-1", "?limit=x", "?limit=1.5"])
def test_limit_out_of_range_is_validation_error(env, query):
    env.publish(["a"])
    response = env.get(env.alice, query=query)
    assert response.status_code == 422, response.text
    body = response.json()
    assert_schema("Error", body)
    assert body["code"] == "VALIDATION_ERROR"
    assert [f["field"] for f in body["details"]["fields"]] == ["limit"]


def test_truncation_is_a_stable_prefix_of_the_full_order(env):
    """LP-6：先全量排序再截断；同分按章节秩、再按 kp_id 字节序；多次请求结果逐字节相同。"""
    chapters = [DraftChapter("c1", "一", 1), DraftChapter("c2", "二", 2)]
    nodes = [kp("z", chapter="c1"), kp("y", chapter="c2"), kp("x"), kp("b"), kp("a"),
             kp("é"), kp("m", chapter="c1"), kp("hub", importance=1.0)]
    env.publish(nodes + ["t1", "t2"], [pre("hub", "t1"), pre("hub", "t2")], chapters)
    full = body_of(env.get(env.alice, query="?limit=50"))
    order = [r["kp_id"] for r in full["recommendations"]]
    assert order == ["hub", "m", "z", "y", "a", "b", "x", "é"]
    for limit in range(1, len(order) + 1):
        body = body_of(env.get(env.alice, query=f"?limit={limit}"))
        assert body["recommendations"] == full["recommendations"][:limit]
        assert body["total_eligible"] == len(order)
    assert env.get(env.alice, query="?limit=50").content == env.get(env.alice, query="?limit=50").content


def test_weights_come_from_startup_settings(tmp_path, monkeypatch):
    url, *rest = _env(tmp_path, monkeypatch, weights=("0", "0", "0", "1"))
    with TestClient(create_app()) as client:
        env = Env(client, url, *rest)
        env.publish([kp("hard", difficulty=0.9, importance=1.0), kp("easy", difficulty=0.1)])
        body = body_of(env.get(env.alice))
    assert [r["kp_id"] for r in body["recommendations"]] == ["easy", "hard"]
    easy = body["recommendations"][0]
    assert easy["weighted"] == {"unlock": 0.0, "importance": 0.0, "chapter_order": 0.0, "ease": 0.9}
    assert easy["reason_facts"]["primary_factor"] == "ease"


# --- 请求全程同版本 ---------------------------------------------------------------------------


def test_lp10_request_stays_on_the_version_bound_at_start(env, monkeypatch):
    env.publish(["a", "b"], [pre("a", "b")])
    env.mark(env.alice, {"a": "mastered"})
    original = service.project_progress
    fired = []

    def publish_mid_request(sqlite_url, user_id, bound):
        if not fired:
            fired.append(True)
            env.publish(["n1", "n2"])  # v2 在本请求绑定 v1 之后提交
            env.mark(env.bob, {"n1": "mastered"})
        return original(sqlite_url, user_id, bound)

    monkeypatch.setattr(service, "project_progress", publish_mid_request)
    body = body_of(env.get(env.alice))
    assert (body["graph_version"], [r["kp_id"] for r in body["recommendations"]]) == (1, ["b"])
    assert {r["graph_version"] for r in body["recommendations"]} == {1}
    later = body_of(env.get(env.alice))
    assert (later["graph_version"], sorted(r["kp_id"] for r in later["recommendations"])) == (2, ["n1", "n2"])


def test_pointer_is_resolved_once_per_request(env, monkeypatch):
    env.publish(["a"])
    calls = []
    original = service.resolve_published
    monkeypatch.setattr(service, "resolve_published", lambda *a, **k: calls.append(a) or original(*a, **k))
    body_of(env.get(env.alice))
    assert len(calls) == 1


# --- 已提交版损坏 -----------------------------------------------------------------------------


def _cycle(raw):
    raw["edges"] += [
        {"from_id": "a", "to_id": "b", "rel_id": "x1", "source_refs": [], "type": "PREREQUISITE"},
        {"from_id": "b", "to_id": "a", "rel_id": "x2", "source_refs": [], "type": "PREREQUISITE"},
    ]


def _self_loop(raw):
    raw["edges"] += [{"from_id": "a", "to_id": "a", "rel_id": "x1", "source_refs": [], "type": "PREREQUISITE"}]


def _dangling(raw):
    raw["edges"] += [{"from_id": "a", "to_id": "gone", "rel_id": "x1", "source_refs": [], "type": "PREREQUISITE"}]


def _empty(raw):
    raw["nodes"] = []


def _orphan_chapter(raw):
    raw["chapters"] = [{"chapter_id": "c1", "order": 1, "parent_id": "missing", "title": "一"}]
    raw["nodes"][0]["chapter_id"] = "c1"


def _unknown_chapter(raw):
    raw["nodes"][0]["chapter_id"] = "nowhere"


def _bad_lineage(raw):
    raw["nodes"][1]["merged_from"] = ["a"]


@pytest.mark.parametrize("change,fragment", [
    (_cycle, "cycle"), (_self_loop, "self_loop"), (_dangling, "dangling_edge"), (_empty, "empty"),
    (_orphan_chapter, "chapter_tree"), (_unknown_chapter, "unknown_chapter"), (_bad_lineage, "lineage"),
])
def test_committed_graph_fault_is_500_with_request_id_only(env, caplog, change, fragment):
    version = env.publish(["a", "b"])
    env.tamper(version, change)
    assert_integrity_500(env.get(env.alice), caplog)
    assert fragment in caplog.text


def test_cycle_is_an_explicit_error_with_the_path_only_in_the_log(env, caplog):
    version = env.publish(["kp-secret-1", "kp-secret-2"])

    def cycle(raw):
        raw["edges"] += [
            {"from_id": "kp-secret-1", "to_id": "kp-secret-2", "rel_id": "x1", "source_refs": [], "type": "PREREQUISITE"},
            {"from_id": "kp-secret-2", "to_id": "kp-secret-1", "rel_id": "x2", "source_refs": [], "type": "PREREQUISITE"},
        ]

    env.tamper(version, cycle)
    assert_integrity_500(env.get(env.alice), caplog, "kp-secret-1", "kp-secret-2")
    assert "cycle" in caplog.text


def test_digest_mismatch_is_500(env, caplog):
    version = env.publish(["a"])
    with connect(env.url) as db:
        db.execute("DROP TRIGGER graph_versions_committed_frozen")
        db.execute("UPDATE graph_versions SET digest = ? WHERE version_id = ?", ("sha256:" + "0" * 64,
                                                                                 version.version_id))
    assert_integrity_500(env.get(env.alice), caplog)


@pytest.mark.parametrize("damage", ["digest-column", "foreign-course"])
def test_graph_read_revalidates_snapshot_with_warm_version_caches(env, caplog, damage):
    """I05 的图读自己也复核摘要与课程：G07 修订缓存、I02 谱系缓存已热时仍必须 500。

    先成功请求一次预热 resolver 的修订缓存与 progress 的谱系缓存，再只让 I05 自己的图缓存转冷；
    此时这次复核若被删掉，损坏的已提交版会以 200 返回缓存外的图，而不是 5xx。
    """
    version = env.publish(["a"])
    assert body_of(env.get(env.alice))["state"] == "recommendations"
    service.clear_cache()
    if damage == "digest-column":
        with connect(env.url) as db:
            db.execute("DROP TRIGGER graph_versions_committed_frozen")
            db.execute("UPDATE graph_versions SET digest = ? WHERE version_id = ?",
                       ("sha256:" + "0" * 64, version.version_id))
    else:
        env.tamper(version, lambda raw: raw.__setitem__("course_id", "another-course"))
    assert_integrity_500(env.get(env.alice), caplog)


def test_broken_graph_is_not_cached_and_recovery_is_seen(env, caplog):
    """损坏版本不进缓存；缓存按 version_id，新发布版本立即使用新图。"""
    version = env.publish(["a", "b"])
    env.tamper(version, _cycle)
    assert env.get(env.alice).status_code == 500
    env.publish(["a", "b"], [pre("a", "b")])
    assert ids(env.get(env.alice)) == ["a"]


def test_serialisation_fault_is_500_with_request_id_only(env, monkeypatch, caplog):
    env.publish(["a"])

    class Broken:
        @staticmethod
        def model_validate(value):
            raise ValueError("not serialisable")

    monkeypatch.setattr(recommend_api, "RecommendResponse", Broken)
    response = env.get(env.alice)
    assert response.status_code == 500
    assert set(response.json()["details"]) == {"request_id"}


# --- 服务层 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [0, 51, True, 1.0])
def test_service_rejects_limits_outside_contract(env, limit):
    from app.services.learning.ranking import RecommendWeights

    env.publish(["a"])
    with pytest.raises(ValueError):
        service.get_recommendations(env.url, env.alice.id, env.course,
                                    RecommendWeights(0.35, 0.25, 0.20, 0.20), limit)
