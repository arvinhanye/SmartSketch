"""F13：直通 ``merging`` 与 ``persisting`` 阶段（specs/task-processing.md §3、§8.4、§8.5；ADR-009、ADR-028）。

验收：失败重跑幂等（LEASE-3、LEASE-21）；取消不标已完成（T8 只在 T5 之前，``persisting`` 不可取消）；
部分块失败按 A03（E12 已判定，阈值内的任务照常写入成功块的内容）。另覆盖：ADR-009 降级（DAG-2～5、DAG-10）、
课程写锁、T6 提交序号、存储故障释放与 ``cleanup_pending`` 清理（LEASE-12、LEASE-18、LEASE-19）。

前半部分不连 Neo4j，任何环境都跑；后半部分连真实 Neo4j 5.26，只在设置
``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行，每个用例使用独立课程 ID 并只清理自己的数据。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.repositories import course_locks, task_leases, tasks
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_relations import PrerequisiteEdge, derive_rel_id
from app.repositories.model_calls import SqliteCallStore
from app.repositories.neo4j import Neo4jRepository, RepositoryError
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.services.ai.client import ModelRequest
from app.services.ai.entities import EntityExtractor
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import ModelCallPolicy
from app.services.ai.relations import RelationExtractor
from app.services.file_storage import FileStorage, StoredFile
from app.services.graph.downgrade import UnresolvableCycleError, plan_downgrades
from app.workers import persist_graph
from app.workers.extract_task import ExtractionToolkit, ExtractLimits, ExtractStatus, run_extract_stage
from app.workers.parse_task import ParseStatus, run_parse_stage
from app.workers.persist_graph import PersistStatus, build_plan, run_merge_stage, run_persist_stage

MODEL = "extract-model"
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3

_SENTENCE = re.compile(r"(概念(\d{2}))是第\d章的第\d个知识点。")
_PREREQ = re.compile(r"学习(概念\d{2})之前需要先掌握(概念\d{2})。")


def _material(pairs: list[tuple[str, str]], names: list[str]) -> bytes:
    """一章；每个知识点一段，段内可带「学习 X 之前需要先掌握 Y」。"""
    lines = ["第1章 主题1"]
    needs = {}
    for later, earlier in pairs:
        needs.setdefault(later, []).append(earlier)
    for i, name in enumerate(names, 1):
        text = f"{name}是第1章的第{i}个知识点。" + "".join(f"学习{name}之前需要先掌握{e}。" for e in needs.get(name, []))
        lines += [text, ""]
    return "\n".join(lines).encode("utf-8")


def _responder(request: ModelRequest) -> str:
    prompt = request.messages[0].content
    if "实体表" in prompt:
        ids = {}
        for line in prompt.splitlines():
            line = line.strip().rstrip(",")
            if line.startswith('{"id"'):
                row = json.loads(line)
                ids[row["name"]] = row["id"]
        items = [
            {"from_id": ids[m.group(2)], "to_id": ids[m.group(1)], "type": "PREREQUISITE", "evidence": m.group(0),
             "confidence": 0.8}
            for m in _PREREQ.finditer(prompt) if m.group(1) in ids and m.group(2) in ids and m.group(1) != m.group(2)
        ]
        return json.dumps({"relations": items}, ensure_ascii=False)
    items = [{"name": m.group(1), "type": "concept", "definition": f"{m.group(1)}的定义", "evidence": m.group(0),
              "confidence": 0.9} for m in _SENTENCE.finditer(prompt)]
    return json.dumps({"entities": items}, ensure_ascii=False)


def _toolkit(db_url: str) -> ExtractionToolkit:
    policy = ModelCallPolicy(primary=FakeModelClient(responder=_responder), store=SqliteCallStore(db_url),
                             max_retries=0, failure_threshold=1000, open_seconds=30, task_token_budget=10**9,
                             daily_token_budget=10**9, sleep=lambda _s: None)
    return ExtractionToolkit(policy=policy,
                             entities=lambda c: EntityExtractor(c, model=MODEL, max_output_tokens=4000),
                             relations=lambda c: RelationExtractor(c, model=MODEL, max_output_tokens=4000))


def _limits() -> ExtractLimits:
    return ExtractLimits(max_attempts=MAX_ATTEMPTS, chunk_max_attempts=2, max_failed_ratio=0.2, max_concurrency=1)


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    return url


@pytest.fixture
def storage(tmp_path: Path) -> FileStorage:
    return FileStorage(tmp_path / "files", 10 * 1024 * 1024)


def _sql(url: str, statement: str, *params: object) -> list[tuple]:
    with connect(url) as database:
        return database.execute(statement, params).fetchall()


def _add_material(db_url: str, storage: FileStorage, data: bytes, course: str) -> str:
    name = secrets.token_hex(16) + ".txt"
    path = storage.path_for(name)
    path.write_bytes(data)
    stored = StoredFile(storage_name=name, path=path, original_filename="notes.txt", format="txt",  # type: ignore[arg-type]
                        size_bytes=len(data), content_hash="sha256:" + hashlib.sha256(data).hexdigest())
    return tasks.create_material_task(db_url, course_id=course, stored_file=stored,
                                      idempotency_key=secrets.token_hex(8)).task.id


def _claim(db_url: str, owner: str = "worker-a") -> task_leases.Lease:
    lease = task_leases.claim_next(db_url, owner=owner, lease_seconds=LEASE_SECONDS, max_attempts=MAX_ATTEMPTS)
    assert lease is not None
    return lease


def _at(lease: task_leases.Lease, stage: str) -> task_leases.Lease:
    return task_leases.Lease(**{**lease.__dict__, "stage": stage})


def _to_merging(db_url: str, storage: FileStorage, data: bytes, course: str) -> task_leases.Lease:
    task_id = _add_material(db_url, storage, data, course)
    lease = _claim(db_url)
    assert lease.task_id == task_id
    parsed = run_parse_stage(db_url, lease, storage=storage, max_attempts=MAX_ATTEMPTS, target_chars=2000,
                             overlap_chars=0)
    assert parsed.status is ParseStatus.ADVANCED
    extracted = run_extract_stage(db_url, _at(lease, "extracting"), toolkit=_toolkit(db_url), limits=_limits())
    assert extracted.status is ExtractStatus.ADVANCED
    return _at(lease, "merging")


def _row(db_url: str, task_id: str) -> dict[str, object]:
    (row,) = _sql(db_url, """SELECT stage, progress, error_code, error_details, lease_token, t6_seq, cleanup_pending,
                                    attempt, cancel_requested FROM processing_tasks WHERE id = ?""", task_id)
    return dict(zip("stage progress error_code error_details lease_token t6_seq cleanup_pending attempt "
                    "cancel_requested".split(), row))


def _expire(db_url: str, task_id: str) -> None:
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", task_id)


# --- 不连 Neo4j ---------------------------------------------------------------------------------


def _edge(rel_id: str, a: str, b: str, confidence: float = 0.5, downgradable: bool = True) -> PrerequisiteEdge:
    return PrerequisiteEdge(rel_id, a, b, confidence, downgradable)


def test_dag2_lowest_confidence_edge_on_the_cycle_is_downgraded():
    edges = [_edge("r1", "A", "B", 0.9), _edge("r2", "B", "C", 0.8), _edge("r3", "C", "A", 0.4)]
    [d] = plan_downgrades("ABC", edges)
    assert d.rel_id == "r3" and d.cycle[0] == d.cycle[-1] and set(d.cycle) == {"A", "B", "C"}


def test_dag3_ties_pick_the_smallest_id_and_are_reproducible():
    edges = [_edge("r2", "A", "B"), _edge("r1", "B", "C"), _edge("r3", "C", "A")]
    first = plan_downgrades("ABC", edges)
    assert [d.rel_id for d in first] == ["r1"]
    assert plan_downgrades("CBA", list(reversed(edges))) == first


def test_dag4_confirmed_edges_are_never_downgraded():
    edges = [_edge("r1", "A", "B", 0.1, False), _edge("r2", "B", "C", 0.1, False), _edge("r3", "C", "A", 0.95)]
    assert [d.rel_id for d in plan_downgrades("ABC", edges)] == ["r3"]


def test_dag5_two_cycles_are_resolved_one_edge_per_round():
    edges = [_edge("r1", "A", "B", 0.9), _edge("r2", "B", "A", 0.3),
             _edge("r3", "C", "D", 0.9), _edge("r4", "D", "C", 0.2)]
    assert sorted(d.rel_id for d in plan_downgrades("ABCD", edges)) == ["r2", "r4"]
    shared = [_edge("r1", "A", "B", 0.9), _edge("r2", "B", "A", 0.2), _edge("r3", "B", "C", 0.9),
              _edge("r4", "C", "B", 0.8)]
    assert sorted(d.rel_id for d in plan_downgrades("ABC", shared)) == ["r2", "r4"]


def test_dag10_cycle_of_confirmed_edges_is_unresolvable():
    edges = [_edge("r1", "A", "B", downgradable=False), _edge("r2", "B", "A", downgradable=False)]
    with pytest.raises(UnresolvableCycleError) as error:
        plan_downgrades("AB", edges)
    assert error.value.cycle in (("A", "B", "A"), ("B", "A", "B"))


def test_acyclic_edges_need_no_downgrade():
    assert plan_downgrades("ABC", [_edge("r1", "A", "B"), _edge("r2", "B", "C")]) == ()


def test_course_lock_is_exclusive_until_released_or_expired(db_url):
    first = course_locks.try_acquire(db_url, "c1", holder="a", lease_seconds=60)
    assert first is not None
    assert course_locks.try_acquire(db_url, "c1", holder="b", lease_seconds=60) is None
    assert course_locks.try_acquire(db_url, "c2", holder="b", lease_seconds=60) is not None
    assert course_locks.renew(db_url, first, lease_seconds=60)
    assert course_locks.release(db_url, first)
    second = course_locks.try_acquire(db_url, "c1", holder="b", lease_seconds=60)
    assert second is not None
    _sql(db_url, "UPDATE course_locks SET expires_at = unixepoch() - 1 WHERE course_id = 'c1'")
    third = course_locks.try_acquire(db_url, "c1", holder="c", lease_seconds=60)
    assert third is not None and third.token != second.token
    assert not course_locks.release(db_url, second) and not course_locks.renew(db_url, second, lease_seconds=60)
    assert course_locks.release(db_url, third)


def test_course_lock_wait_is_bounded(db_url):
    assert course_locks.try_acquire(db_url, "c1", holder="a", lease_seconds=60) is not None
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    lock = course_locks.acquire(db_url, "c1", holder="b", lease_seconds=60, wait_seconds=1, poll_seconds=0.25,
                                sleep=sleep, clock=lambda: now[0])
    assert lock is None and sum(slept) == pytest.approx(1.0)


def test_course_lock_is_renewed_while_held_and_released_after(db_url):
    import time

    lock = course_locks.try_acquire(db_url, "c1", holder="a", lease_seconds=3)
    assert lock is not None
    with course_locks.held(db_url, lock, lease_seconds=3):
        _sql(db_url, "UPDATE course_locks SET expires_at = unixepoch() WHERE course_id = 'c1'")
        time.sleep(1.3)
        [(expires, now)] = _sql(db_url, "SELECT expires_at, unixepoch() FROM course_locks WHERE course_id = 'c1'")
        assert expires >= now + 2
    assert _sql(db_url, "SELECT count(*) FROM course_locks") == [(0,)]


def test_migration_009_rolls_back(db_url):
    text = next(MIGRATIONS_DIR.glob("*_course_locks.sql")).read_text(encoding="utf-8")
    lines = [line.split("ROLLBACK:", 1)[1].strip() for line in text.splitlines() if "ROLLBACK:" in line]
    assert len(lines) == 4
    database = sqlite3.connect(db_url.removeprefix("sqlite:///"))
    try:
        with database:
            for line in lines:
                database.execute(line)
        columns = {row[1] for row in database.execute("PRAGMA table_info(processing_tasks)")}
        assert "t6_seq" not in columns
        assert not database.execute("SELECT 1 FROM sqlite_master WHERE name = 'course_locks'").fetchall()
    finally:
        database.close()
    migrate(db_url)  # 重新迁移恢复
    assert _sql(db_url, "SELECT count(*) FROM course_locks") == [(0,)]


def test_merging_passes_through_to_persisting(db_url, storage):
    lease = _to_merging(db_url, storage, _material([], ["概念11"]), "c-merge")
    outcome = run_merge_stage(db_url, lease)
    assert outcome.status is PersistStatus.ADVANCED and outcome.stage == "persisting"
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "persisting" and row["progress"] == pytest.approx(0.80)
    assert row["lease_token"] == lease.token


def test_cancel_during_merging_ends_cancelled_never_completed(db_url, storage):
    lease = _to_merging(db_url, storage, _material([], ["概念11"]), "c-cancel")
    with connect(db_url) as database:
        assert tasks.mark_cancel_requested(database, task_id=lease.task_id, course_id="c-cancel",
                                           expected_stage="merging", target_stage="merging")
    outcome = run_merge_stage(db_url, lease)
    assert outcome.status is PersistStatus.CANCELLED
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "cancelled" and row["lease_token"] is None and row["t6_seq"] is None


def test_persisting_cannot_be_cancelled(db_url, storage):
    lease = _to_merging(db_url, storage, _material([], ["概念11"]), "c-nocancel")
    run_merge_stage(db_url, lease)
    with connect(db_url) as database:
        assert not tasks.mark_cancel_requested(database, task_id=lease.task_id, course_id="c-nocancel",
                                               expected_stage="persisting", target_stage="persisting")
    assert _row(db_url, lease.task_id)["cancel_requested"] == 0


def test_persisting_failure_by_exhaustion_marks_cleanup(db_url, storage):
    lease = _to_merging(db_url, storage, _material([], ["概念11"]), "c-exhaust")
    run_merge_stage(db_url, lease)
    _sql(db_url, "UPDATE processing_tasks SET attempt = ? WHERE id = ?", MAX_ATTEMPTS, lease.task_id)
    _expire(db_url, lease.task_id)
    reclaimed = task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS)
    assert [t.task_id for t in reclaimed.failed] == [lease.task_id]
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "failed" and row["cleanup_pending"] == 1
    assert [t.task_id for t in task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS).cleanup_pending] == [
        lease.task_id]


def test_extracting_exhaustion_does_not_mark_cleanup(db_url, storage):
    task_id = _add_material(db_url, storage, _material([], ["概念11"]), "c-early")
    _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET attempt = ? WHERE id = ?", MAX_ATTEMPTS, task_id)
    _expire(db_url, task_id)
    task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS)
    assert _row(db_url, task_id)["cleanup_pending"] == 0


def test_build_plan_maps_entities_and_relations_deterministically(db_url, storage):
    lease = _to_merging(db_url, storage, _material([("概念12", "概念11")], ["概念11", "概念12"]), "c-plan")
    from app.workers.extract_task import load_candidates

    candidates = load_candidates(db_url, course_id="c-plan", task_id=lease.task_id)
    plan = build_plan("c-plan", lease.task_id, candidates)
    assert plan == build_plan("c-plan", lease.task_id, candidates)
    assert {n.name for n in plan.nodes} == {"概念11", "概念12"}
    assert all(n.status == "draft" and n.kp_id.startswith("kp_") and n.sources for n in plan.nodes)
    kp = {n.name: n.kp_id for n in plan.nodes}
    [rel] = plan.relations
    assert (rel.from_id, rel.to_id, rel.type, rel.status) == (kp["概念11"], kp["概念12"], "PREREQUISITE", "draft")
    assert rel.rel_id == derive_rel_id("c-plan", "PREREQUISITE", kp["概念11"], kp["概念12"])
    assert build_plan("c-plan", "other-task", candidates).nodes[0].kp_id not in kp.values()


def test_effective_task_ids_are_course_scoped(db_url, storage):
    a = _add_material(db_url, storage, b"x", "c-v1")
    b = _add_material(db_url, storage, b"y", "c-v2")
    _sql(db_url, "UPDATE processing_tasks SET stage = 'awaiting_review', progress = 0.95 WHERE id IN (?, ?)", a, b)
    with connect(db_url) as database:
        assert tasks.read_effective_task_ids(database, "c-v1") == (a,)


# --- 真实 Neo4j ---------------------------------------------------------------------------------

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
_LIVE = all(os.environ.get(name) for name in _ENV)
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "f13-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    try:
        yield SimpleNamespace(course=course, repo=Neo4jRepository(driver), q=q)
    finally:
        q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)
        driver.close()


class _BrokenRepo:
    def __init__(self) -> None:
        self.calls = 0

    def write_transaction(self, scope, work):
        self.calls += 1
        raise RepositoryError()


def _persist(db_url, lease, repo, **kw):
    params = dict(repo=repo, max_attempts=MAX_ATTEMPTS, lock_seconds=LEASE_SECONDS, lock_wait_seconds=0)
    params.update(kw)
    return run_persist_stage(db_url, _at(lease, "persisting"), **params)


def _persisting(db_url, storage, graph, pairs, names):
    lease = _to_merging(db_url, storage, _material(pairs, names), graph.course)
    assert run_merge_stage(db_url, lease).status is PersistStatus.ADVANCED
    return _at(lease, "persisting")


def _counts(graph):
    [row] = graph.q(
        "MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) "
        "OPTIONAL MATCH (n)-[e:EVIDENCED_BY]->(:Chunk) "
        "WITH count(DISTINCT n) AS nodes, count(e) AS sources "
        "OPTIONAL MATCH ()-[r {course_id: $c, version_id: 'draft'}]->() "
        "WITH nodes, sources, count(r) AS rels "
        "OPTIONAL MATCH (ri:RelationIdentity {course_id: $c}) "
        "RETURN nodes, sources, rels, count(ri) AS identities", c=graph.course)
    return row


def _rels(graph):
    return graph.q("MATCH (a)-[r {course_id: $c, version_id: 'draft'}]->(b) "
                   "RETURN type(r) AS type, a.name AS a, b.name AS b, properties(r) AS p ORDER BY a, b",
                   c=graph.course)


def _visible_to_teacher(graph, db_url):
    with connect(db_url) as database:
        v = list(tasks.read_effective_task_ids(database, graph.course))
    return graph.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) "
                   "WHERE n.contrib_manual OR any(t IN n.contrib_tasks WHERE t IN $v) RETURN n.name AS name "
                   "ORDER BY name", c=graph.course, v=v)


@live
def test_live_persisting_writes_the_draft_then_t6_with_sequence(db_url, storage, graph):
    user = uuid.uuid4().hex
    _sql(db_url, "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, 'teacher')",
         user, "t" + user[:10], "$argon2id$v=19$m=1,t=1,p=1$c2FsdA$aGFzaA")
    _sql(db_url, "INSERT INTO courses (id, name, teacher_id) VALUES (?, 'c', ?)", graph.course, user)
    lease = _persisting(db_url, storage, graph, [("概念12", "概念11"), ("概念13", "概念12")],
                        ["概念11", "概念12", "概念13"])
    assert _sql(db_url, "SELECT draft_revision FROM courses WHERE id = ?", graph.course) == [(0,)]
    outcome = _persist(db_url, lease, graph.repo)
    assert _sql(db_url, "SELECT draft_revision FROM courses WHERE id = ?", graph.course) == [(1,)]
    assert outcome.status is PersistStatus.ADVANCED and outcome.stage == "awaiting_review"
    row = _row(db_url, lease.task_id)
    assert (row["stage"], row["t6_seq"], row["lease_token"]) == ("awaiting_review", 1, None)
    assert row["progress"] == pytest.approx(0.95)
    counts = _counts(graph)
    assert (counts["nodes"], counts["rels"], counts["identities"]) == (3, 2, 2) and counts["sources"] >= 3
    assert [(r["type"], r["a"], r["b"]) for r in _rels(graph)] == [
        ("PREREQUISITE", "概念11", "概念12"), ("PREREQUISITE", "概念12", "概念13")]
    assert [r["name"] for r in _visible_to_teacher(graph, db_url)] == ["概念11", "概念12", "概念13"]
    assert _sql(db_url, "SELECT count(*) FROM course_locks") == [(0,)]

    second = _persisting(db_url, storage, graph, [], ["概念21"])
    assert _persist(db_url, second, graph.repo).status is PersistStatus.ADVANCED
    assert _row(db_url, second.task_id)["t6_seq"] == 2


@live
def test_live_lease3_rerun_after_neo4j_commit_matches_a_single_run(db_url, storage, graph, monkeypatch):
    lease = _persisting(db_url, storage, graph, [("概念12", "概念11")], ["概念11", "概念12"])

    class Crash(BaseException):
        pass

    def crash(*_a, **_k):
        raise Crash()

    monkeypatch.setattr(persist_graph, "_t6", crash)
    with pytest.raises(Crash):
        _persist(db_url, lease, graph.repo)
    monkeypatch.undo()
    first = _counts(graph)
    assert _visible_to_teacher(graph, db_url) == []  # LEASE-20：T6 前不可见
    assert _sql(db_url, "SELECT count(*) FROM course_locks") == [(0,)]

    _expire(db_url, lease.task_id)
    task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS)
    again = _claim(db_url, "worker-b")
    assert again.task_id == lease.task_id and again.stage == "persisting"
    assert _persist(db_url, again, graph.repo).status is PersistStatus.ADVANCED
    assert _counts(graph) == first
    [rel] = _rels(graph)
    assert rel["p"]["contrib_tasks"] == [lease.task_id] and len(rel["p"]["source_pairs"]) == 1


@live
def test_live_lease21_rerun_revokes_elements_the_new_attempt_does_not_write(db_url, storage, graph, monkeypatch):
    lease = _persisting(db_url, storage, graph, [("概念12", "概念11")], ["概念11", "概念12"])
    monkeypatch.setattr(persist_graph, "_t6", lambda *_a, **_k: (_ for _ in ()).throw(persist_graph.LeaseLost("x")))
    assert _persist(db_url, lease, graph.repo).status is PersistStatus.LOST
    monkeypatch.undo()
    assert _counts(graph)["nodes"] == 2

    real = persist_graph.build_plan

    def only_first(course, task, candidates):
        plan = real(course, task, candidates)
        keep = [n for n in plan.nodes if n.name == "概念11"]
        return persist_graph.DraftPlan(tuple(keep), (), 0)

    monkeypatch.setattr(persist_graph, "build_plan", only_first)
    _expire(db_url, lease.task_id)
    again = _claim(db_url, "worker-b")
    assert _persist(db_url, again, graph.repo).status is PersistStatus.ADVANCED
    counts = _counts(graph)
    assert (counts["nodes"], counts["rels"], counts["identities"]) == (1, 0, 0)
    assert [r["name"] for r in _visible_to_teacher(graph, db_url)] == ["概念11"]


@live
def test_live_dag2_in_task_cycle_is_downgraded_and_task_completes(db_url, storage, graph):
    lease = _persisting(db_url, storage, graph, [("概念12", "概念11"), ("概念11", "概念12")], ["概念11", "概念12"])
    outcome = _persist(db_url, lease, graph.repo)
    assert outcome.status is PersistStatus.ADVANCED and len(outcome.downgraded) == 1
    types = sorted((r["type"], r["p"]["status"]) for r in _rels(graph))
    assert types == [("PREREQUISITE", "draft"), ("RELATED_TO", "low_confidence")]
    [down] = [r for r in _rels(graph) if r["type"] == "RELATED_TO"]
    assert down["p"]["downgraded_from_type"] == "PREREQUISITE"
    cycle = down["p"]["downgrade_cycle"]
    assert cycle[0] == cycle[-1] and len(cycle) == 3
    assert down["p"]["rel_id"] == outcome.downgraded[0].rel_id


@live
def test_live_dag10_confirmed_cycle_fails_the_task_and_cleans_up(db_url, storage, graph):
    graph.q("CREATE (a:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'm1', name: 'm1', "
            "contrib_manual: true, contrib_tasks: []}), "
            "(b:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'm2', name: 'm2', "
            "contrib_manual: true, contrib_tasks: []}), "
            "(a)-[:PREREQUISITE {course_id: $c, version_id: 'draft', rel_id: 'r1', status: 'approved', "
            "source: 'manual', contrib_manual: true, contrib_tasks: []}]->(b), "
            "(b)-[:PREREQUISITE {course_id: $c, version_id: 'draft', rel_id: 'r2', status: 'approved', "
            "source: 'manual', contrib_manual: true, contrib_tasks: []}]->(a)", c=graph.course)
    lease = _persisting(db_url, storage, graph, [], ["概念11"])
    outcome = _persist(db_url, lease, graph.repo)
    assert outcome.status is PersistStatus.FAILED and outcome.error_code == "CYCLE_DETECTED"
    assert outcome.cleanup_pending is False
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "failed" and row["error_code"] == "CYCLE_DETECTED" and row["cleanup_pending"] == 0
    assert set(json.loads(row["error_details"])["cycle"]) == {"m1", "m2"}
    assert _counts(graph)["nodes"] == 2  # 只剩教师节点；本任务内容已回滚/清理
    assert len(_rels(graph)) == 2


@live
def test_live_storage_failure_releases_then_fails_and_cleanup_retries(db_url, storage, graph):
    lease = _persisting(db_url, storage, graph, [], ["概念11"])
    broken = _BrokenRepo()
    outcome = _persist(db_url, lease, broken)
    assert outcome.status is PersistStatus.RELEASED and outcome.not_before is not None
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "persisting" and row["lease_token"] is None and row["cleanup_pending"] == 0
    assert _sql(db_url, "SELECT count(*) FROM course_locks") == [(0,)]

    _sql(db_url, "UPDATE processing_tasks SET not_before = unixepoch(), attempt = ? WHERE id = ?",
         MAX_ATTEMPTS - 1, lease.task_id)
    last = _claim(db_url, "worker-b")
    outcome = _persist(db_url, last, broken)
    assert outcome.status is PersistStatus.FAILED and outcome.error_code == "STORAGE_UNAVAILABLE"
    assert outcome.cleanup_pending is True
    assert _row(db_url, lease.task_id)["cleanup_pending"] == 1

    pending = task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS).cleanup_pending
    assert [t.task_id for t in pending] == [lease.task_id]
    assert persist_graph.cleanup_failed_task(db_url, graph.repo, course_id=graph.course, task_id=lease.task_id,
                                             holder="w", lock_seconds=60, lock_wait_seconds=0)
    assert _row(db_url, lease.task_id)["cleanup_pending"] == 0


@live
def test_live_lease12_18_cleanup_keeps_elements_with_other_contributions(db_url, storage, graph):
    first = _persisting(db_url, storage, graph, [("概念12", "概念11")], ["概念11", "概念12"])
    assert _persist(db_url, first, graph.repo).status is PersistStatus.ADVANCED
    second = _persisting(db_url, storage, graph, [], ["概念21"])
    # 第二个任务在 T6 前「失败」：它也给第一个任务的关系登记了来源（模拟同一关系 ID 被复用）。
    [rel] = _rels(graph)
    graph.q("MATCH ()-[r {course_id: $c, rel_id: $r}]->() "
            "SET r.contrib_tasks = r.contrib_tasks + $t, r.source_pairs = r.source_pairs + [$p]",
            c=graph.course, r=rel["p"]["rel_id"], t=second.task_id, p=json.dumps([second.task_id, "chunk-x"]))
    monkey = _BrokenRepo()
    _sql(db_url, "UPDATE processing_tasks SET attempt = ? WHERE id = ?", MAX_ATTEMPTS, second.task_id)
    outcome = _persist(db_url, second, monkey)
    assert outcome.status is PersistStatus.FAILED and outcome.cleanup_pending is True
    assert persist_graph.cleanup_failed_task(db_url, graph.repo, course_id=graph.course, task_id=second.task_id,
                                             holder="w", lock_seconds=60, lock_wait_seconds=0)
    [kept] = _rels(graph)
    assert kept["p"]["contrib_tasks"] == [first.task_id]
    assert all(json.loads(p)[0] == first.task_id for p in kept["p"]["source_pairs"])
    assert _counts(graph)["nodes"] == 2


@live
def test_live_busy_course_lock_releases_without_writing(db_url, storage, graph):
    lease = _persisting(db_url, storage, graph, [], ["概念11"])
    holder = course_locks.try_acquire(db_url, graph.course, holder="publisher", lease_seconds=60)
    assert holder is not None
    outcome = _persist(db_url, lease, graph.repo)
    assert outcome.status is PersistStatus.RELEASED
    assert _counts(graph)["nodes"] == 0
    assert course_locks.release(db_url, holder)


@live
def test_live_lost_lease_writes_nothing_to_neo4j(db_url, storage, graph):
    lease = _persisting(db_url, storage, graph, [], ["概念11"])
    _sql(db_url, "UPDATE processing_tasks SET lease_token = ? WHERE id = ?", "f" * 32, lease.task_id)
    outcome = _persist(db_url, lease, graph.repo)
    assert outcome.status is PersistStatus.LOST
    assert _counts(graph)["nodes"] == 0
    assert _sql(db_url, "SELECT count(*) FROM course_locks") == [(0,)]


@live
def test_live_pipeline_runs_a_queued_task_to_awaiting_review(db_url, storage, graph):
    task_id = _add_material(db_url, storage, _material([("概念12", "概念11")], ["概念11", "概念12"]), graph.course)
    settings = load_settings({"SQLITE_URL": db_url, "STORAGE_DIR": str(storage.root), "TASK_LEASE_SECONDS": "15",
                              "LLM_MAX_CONCURRENCY": "1", "COURSE_LOCK_WAIT_SECONDS": "0"})
    result = persist_graph.run_pipeline_once(settings, toolkit=_toolkit(db_url), repo=graph.repo, owner="w",
                                             storage=storage)
    assert result.lease is not None and result.lease.task_id == task_id
    assert [stage for stage, _ in result.stages] == ["parsing", "extracting", "merging", "persisting"]
    assert all(status == "advanced" for _, status in result.stages)
    assert _row(db_url, task_id)["stage"] == "awaiting_review"
    assert _counts(graph)["nodes"] == 2 and len(_rels(graph)) == 1

