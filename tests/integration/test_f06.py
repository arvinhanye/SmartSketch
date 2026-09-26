"""F06：草稿关系的事务写入与并发防环（specs/course-knowledge-graph.md「前置关系成环处理」；
specs/task-processing.md §8.4「贡献记录」「草稿可见性」；ADR-009、ADR-025）。

验收：两个连接并发写 A→B / B→A，至少一方 ``CYCLE_DETECTED``；读图、环检测与提交在同一个写事务里，
且同一课程草稿的关系写入经课程守卫节点串行。

前半部分用假驱动，任何环境都跑；后半部分连真实 Neo4j 5.26，只在设置
``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行，每个用例使用独立课程 ID 并只清理自己的数据。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from types import SimpleNamespace

import pytest

from app.repositories.chunks import StoredChunk
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_relations import DraftRelation, derive_rel_id
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, RepositoryError
from app.services.chunk_identity import text_sha256
from app.services.chunking import ChunkSource
from app.services.graph.dag import find_cycle
from app.services.graph.relations import (
    CycleDetectedError,
    DanglingEndpointError,
    DuplicateRelationError,
    InvalidRelationError,
    write_relations,
)
from app.services.parsers.models import SourceLocator

TASK = "task-1"
REVISION = "rev_" + "b" * 64


def _chunk(course: str, ordinal: int = 0) -> StoredChunk:
    text = "栈是一种后进先出的线性表。"
    return StoredChunk(
        chunk_id=f"{REVISION}-{ordinal}",
        course_id=course,
        material_id="doc-1",
        revision_id=REVISION,
        ordinal=ordinal,
        text=text,
        text_sha256=text_sha256(text),
        section_titles=("第1章",),
        sources=(ChunkSource(0, 0, len(text), SourceLocator(section_titles=("第1章",), paragraph=1)),),
    )


def _rel(course: str, a: str, b: str, *, type: str = "PREREQUISITE", source: str = "manual",
         status: str | None = None, confidence: float = 1.0, chunk_ids: tuple[str, ...] = ()) -> DraftRelation:
    if status is None:
        status = "approved" if source == "manual" else "draft"
    return DraftRelation(rel_id=derive_rel_id(course, type, a, b), type=type, from_id=a, to_id=b,
                         confidence=confidence, status=status, source=source, chunk_ids=chunk_ids)


def _ai(course: str, a: str, b: str, chunk: StoredChunk, **kw) -> DraftRelation:
    return _rel(course, a, b, source="ai", confidence=kw.pop("confidence", 0.8), chunk_ids=(chunk.chunk_id,), **kw)


def _scope(course: str, v: tuple[str, ...] = ()) -> GraphScope:
    return GraphScope(course, "draft", effective_task_ids=v)


# --- 假驱动 --------------------------------------------------------------------------------------


class _FakeTx:
    def __init__(self, calls: list, answer) -> None:
        self.calls, self.answer = calls, answer

    def run(self, query, parameters=None):
        self.calls.append((query, dict(parameters or {})))
        return self.answer(query, parameters or {})


class _FakeSession:
    def __init__(self, driver) -> None:
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute_write(self, work):
        self.driver.transactions += 1
        if self.driver.error is not None:
            raise self.driver.error
        return work(_FakeTx(self.driver.calls, self.driver.answer))


class _FakeDriver:
    def __init__(self, answer=lambda q, p: [], error: Exception | None = None) -> None:
        self.calls: list = []
        self.transactions = 0
        self.answer, self.error = answer, error

    def verify_connectivity(self) -> None: ...

    def execute_query(self, *a, **kw):  # pragma: no cover - F06 只走显式事务
        raise AssertionError("F06 must use one explicit write transaction")

    def session(self, **kw):
        assert kw.get("database") == "neo4j"
        return _FakeSession(self)

    def close(self) -> None: ...


def test_derive_rel_id_is_deterministic_and_directional():
    rid = derive_rel_id("c1", "PREREQUISITE", "a", "b")
    assert rid.startswith("rel_") and len(rid) == 36
    assert rid == derive_rel_id("c1", "PREREQUISITE", "a", "b")
    assert len({rid, derive_rel_id("c1", "PREREQUISITE", "b", "a"), derive_rel_id("c2", "PREREQUISITE", "a", "b"),
                derive_rel_id("c1", "RELATED_TO", "a", "b")}) == 4
    with pytest.raises(ValueError):
        derive_rel_id("c1", "LIKES", "a", "b")


def test_scoped_transaction_validates_every_statement():
    repo = Neo4jRepository(_FakeDriver(answer=lambda q, p: [{"ok": 1}]))
    scope = _scope("c1", ("t1",))

    def work(tx):
        rows = tx.run("MATCH (n {course_id: $course_id, version_id: $version_id}) "
                      "WHERE n.t IN $effective_task_ids RETURN 1 AS ok", {"effective_task_ids": ["forged"]})
        assert rows == [{"ok": 1}]
        tx.run("MATCH (n {course_id: $course_id}) RETURN n")  # 缺少 version / V

    with pytest.raises(GraphScopeError):
        repo.write_transaction(scope, work)
    # 调用方给的 V 被忽略，只用 scope 的 V。
    assert repo._driver.calls[0][1]["effective_task_ids"] == ["t1"]
    assert repo._driver.calls[0][1]["course_id"] == "c1"


def test_write_transaction_redacts_driver_errors_but_keeps_domain_errors():
    neo4j = pytest.importorskip("neo4j")
    repo = Neo4jRepository(_FakeDriver(error=neo4j.exceptions.ClientError("secret detail")))
    with pytest.raises(RepositoryError) as error:
        repo.write_transaction(_scope("c1"), lambda tx: None)
    assert "secret" not in str(error.value)

    repo = Neo4jRepository(_FakeDriver(error=neo4j.exceptions.ServiceUnavailable("down")))
    with pytest.raises(RepositoryError) as error:
        repo.write_transaction(_scope("c1"), lambda tx: None)
    assert error.value.code == "NEO4J_CONNECTION_FAILED"

    class Domain(Exception):
        pass

    repo = Neo4jRepository(_FakeDriver())
    with pytest.raises(Domain):
        repo.write_transaction(_scope("c1"), lambda tx: (_ for _ in ()).throw(Domain()))


def test_scope_must_be_the_draft_with_v():
    repo = Neo4jRepository(_FakeDriver())
    rel = _rel("c1", "a", "b")
    with pytest.raises(GraphScopeError):
        write_relations(repo, GraphScope("c1", "v1"), relations=[rel])
    with pytest.raises(GraphScopeError):
        write_relations(repo, GraphScope("c1", "draft"), relations=[rel])
    assert repo._driver.transactions == 0


@pytest.mark.parametrize("change", [
    {"type": "LIKES"},
    {"confidence": 1.5},
    {"confidence": float("nan")},
    {"status": "published"},
    {"from_id": " "},
    {"rel_id": "rel_forged"},
])
def test_invalid_relations_are_rejected_before_any_write(change):
    base = _rel("c1", "a", "b")
    fields = {**base.__dict__, **change}
    if "rel_id" not in change and {"type", "from_id"} & change.keys():
        fields["rel_id"] = base.rel_id
    repo = Neo4jRepository(_FakeDriver())
    with pytest.raises(InvalidRelationError):
        write_relations(repo, _scope("c1"), relations=[DraftRelation(**fields)])
    assert repo._driver.transactions == 0


def test_source_must_match_the_writer():
    chunk = _chunk("c1")
    repo = Neo4jRepository(_FakeDriver())
    with pytest.raises(InvalidRelationError):  # 教师写入不能冒充 AI
        write_relations(repo, _scope("c1"), relations=[_ai("c1", "a", "b", chunk)], chunks=[chunk])
    with pytest.raises(InvalidRelationError):  # 任务写入不能冒充人工
        write_relations(repo, _scope("c1"), relations=[_rel("c1", "a", "b")], task_id=TASK)
    with pytest.raises(InvalidRelationError):  # 任务不能写已确认状态
        write_relations(repo, _scope("c1"), relations=[_ai("c1", "a", "b", chunk, status="approved")],
                        task_id=TASK, chunks=[chunk])
    with pytest.raises(InvalidRelationError):  # AI 关系必须有来源
        write_relations(repo, _scope("c1"), relations=[_rel("c1", "a", "b", source="ai", confidence=0.5)],
                        task_id=TASK)
    assert repo._driver.transactions == 0


def test_sources_outside_the_course_are_rejected():
    other = _chunk("c2")
    repo = Neo4jRepository(_FakeDriver())
    with pytest.raises(InvalidRelationError):
        write_relations(repo, _scope("c1"), relations=[_ai("c1", "a", "b", other)], task_id=TASK, chunks=[other])
    with pytest.raises(InvalidRelationError):  # 调用方没给出该块
        write_relations(repo, _scope("c1"), relations=[_ai("c1", "a", "b", _chunk("c1"))], task_id=TASK)


def test_prerequisite_self_loop_is_a_closed_cycle_without_touching_the_database():
    repo = Neo4jRepository(_FakeDriver())
    with pytest.raises(CycleDetectedError) as error:
        write_relations(repo, _scope("c1"), relations=[_rel("c1", "a", "a")])
    assert error.value.cycle == ("a", "a")
    assert error.value.code == "CYCLE_DETECTED"
    with pytest.raises(InvalidRelationError):
        write_relations(repo, _scope("c1"), relations=[_rel("c1", "a", "a", type="RELATED_TO")])
    assert repo._driver.transactions == 0


def test_duplicate_ids_in_one_call_are_rejected():
    repo = Neo4jRepository(_FakeDriver())
    rel = _rel("c1", "a", "b")
    with pytest.raises(InvalidRelationError):
        write_relations(repo, _scope("c1"), relations=[rel, rel])


def test_empty_input_does_not_contact_the_driver():
    repo = Neo4jRepository(_FakeDriver())
    result = write_relations(repo, _scope("c1"), relations=[])
    assert result.written == () and repo._driver.transactions == 0


def test_relation_repr_hides_nothing_sensitive_and_is_frozen():
    rel = _rel("c1", "a", "b")
    with pytest.raises(AttributeError):
        rel.status = "rejected"  # type: ignore[misc]


# --- 真实 Neo4j --------------------------------------------------------------------------------

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
_LIVE = all(os.environ.get(name) for name in _ENV)
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


def _driver():
    neo4j = pytest.importorskip("neo4j")
    return neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))


@pytest.fixture
def graph():
    course = "f06-" + uuid.uuid4().hex
    driver = _driver()
    apply_migrations(driver)
    extra: list = []

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    def kp(*ids: str, course_id: str | None = None, tasks: tuple[str, ...] = (), manual: bool = True):
        for kp_id in ids:
            q("CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k, name: $k, "
              "contrib_manual: $m, contrib_tasks: $t, locked: false})",
              c=course_id or course, k=kp_id, m=manual, t=list(tasks))

    def connection():
        other = _driver()
        extra.append(other)
        return Neo4jRepository(other)

    try:
        yield SimpleNamespace(course=course, repo=Neo4jRepository(driver), q=q, kp=kp, connection=connection)
    finally:
        for c in (course, course + "-other"):
            q("MATCH (n {course_id: $c}) DETACH DELETE n", c=c)
        for other in extra:
            other.close()
        driver.close()


def _edges(graph, course: str | None = None, type: str = "PREREQUISITE"):
    return graph.q(
        f"MATCH (a:KnowledgePoint)-[r:{type} {{course_id: $c, version_id: 'draft'}}]->(b:KnowledgePoint) "
        "RETURN r.rel_id AS rel_id, a.kp_id AS a, b.kp_id AS b, properties(r) AS p ORDER BY a, b",
        c=course or graph.course)


def _pairs(graph, **kw):
    return [(e["a"], e["b"]) for e in _edges(graph, **kw)]


@live
def test_live_concurrent_opposite_edges_conflict(graph):
    """验收：两个连接并发写 A→B 与 B→A，至少一方冲突，草稿始终无环。"""
    for round_ in range(8):
        a, b = f"a{round_}", f"b{round_}"
        graph.kp(a, b)
        barrier = threading.Barrier(2)
        outcomes: dict[str, object] = {}

        def worker(name, rel, repo):
            barrier.wait()
            try:
                outcomes[name] = write_relations(repo, _scope(graph.course), relations=[rel])
            except CycleDetectedError as exc:
                outcomes[name] = exc

        threads = [threading.Thread(target=worker, args=("ab", _rel(graph.course, a, b), graph.connection())),
                   threading.Thread(target=worker, args=("ba", _rel(graph.course, b, a), graph.connection()))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        conflicts = [o for o in outcomes.values() if isinstance(o, CycleDetectedError)]
        assert len(outcomes) == 2 and len(conflicts) == 1, outcomes
        assert set(conflicts[0].cycle[:-1]) == {a, b} and conflicts[0].cycle[0] == conflicts[0].cycle[-1]
        assert len([p for p in _pairs(graph) if set(p) == {a, b}]) == 1


@live
def test_live_concurrent_writers_on_disjoint_endpoints_still_serialize(graph):
    """四个连接并发写 A→B、B→C、C→D、D→A（两两端点不全相交），最终草稿仍无环。"""
    for round_ in range(5):
        ids = [f"n{round_}{x}" for x in "abcd"]
        graph.kp(*ids)
        edges = list(zip(ids, ids[1:] + ids[:1]))
        barrier = threading.Barrier(len(edges))
        results: list = []

        def worker(pair, repo):
            barrier.wait()
            try:
                results.append(write_relations(repo, _scope(graph.course), relations=[_rel(graph.course, *pair)]))
            except CycleDetectedError as exc:
                results.append(exc)

        threads = [threading.Thread(target=worker, args=(pair, graph.connection())) for pair in edges]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert len(results) == 4
        assert sum(isinstance(r, CycleDetectedError) for r in results) == 1
        pairs = _pairs(graph)
        assert find_cycle({x for p in pairs for x in p}, pairs) is None


@live
def test_live_dag1_manual_edge_closing_a_cycle_writes_nothing(graph):
    graph.kp("A", "B", "C")
    write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "B", "C"),
                                                                  _rel(graph.course, "C", "A")])
    before = _edges(graph)
    with pytest.raises(CycleDetectedError) as error:
        write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "B")])
    cycle = error.value.cycle
    assert cycle[0] == cycle[-1] and set(cycle) == {"A", "B", "C"} and len(cycle) == 4
    assert error.value.edge == ("A", "B")
    assert _edges(graph) == before
    assert not graph.q("MATCH (ri:RelationIdentity {course_id: $c, rel_id: $r}) RETURN ri",
                       c=graph.course, r=derive_rel_id(graph.course, "PREREQUISITE", "A", "B"))


@live
def test_live_batch_is_all_or_nothing(graph):
    graph.kp("A", "B", "C")
    with pytest.raises(CycleDetectedError):
        write_relations(graph.repo, _scope(graph.course), relations=[
            _rel(graph.course, "A", "B"), _rel(graph.course, "B", "C"), _rel(graph.course, "C", "A"),
            _rel(graph.course, "A", "C", type="RELATED_TO")])
    assert graph.q("MATCH ()-[r {course_id: $c}]->() RETURN r", c=graph.course) == []
    assert graph.q("MATCH (ri:RelationIdentity {course_id: $c}) RETURN ri", c=graph.course) == []


@live
def test_live_dag7_rejected_edges_do_not_participate(graph):
    graph.kp("A", "B")
    write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "B", "A", status="rejected")])
    write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "B")])
    assert sorted(_pairs(graph)) == [("A", "B"), ("B", "A")]


@live
def test_live_invisible_task_edges_do_not_participate_but_own_edges_do(graph):
    chunk = _chunk(graph.course)
    graph.kp("A", "B")
    # 未提交任务 t-old 留下的 B→A 对教师不可见，不阻止教师写 A→B。
    write_relations(graph.repo, _scope(graph.course), relations=[_ai(graph.course, "B", "A", chunk)],
                    task_id="t-old", chunks=[chunk])
    write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "B")])
    # 同一任务再写 B→A：自己的 B→A 仍在，与可见的 A→B 成环。
    graph.kp("C", "D", manual=False, tasks=("t-new",))
    write_relations(graph.repo, _scope(graph.course), relations=[_ai(graph.course, "C", "D", chunk)],
                    task_id="t-new", chunks=[chunk])
    with pytest.raises(CycleDetectedError):
        write_relations(graph.repo, _scope(graph.course), relations=[_ai(graph.course, "D", "C", chunk)],
                        task_id="t-new", chunks=[chunk])
    # 其他任务看不到 t-new 的节点。
    with pytest.raises(DanglingEndpointError) as error:
        write_relations(graph.repo, _scope(graph.course), relations=[_ai(graph.course, "C", "A", chunk)],
                        task_id="t-other", chunks=[chunk])
    assert error.value.missing == ("C",)


@live
def test_live_edges_of_other_courses_are_ignored(graph):
    other = graph.course + "-other"
    graph.kp("A", "B")
    graph.kp("A", "B", course_id=other)
    write_relations(graph.repo, _scope(other), relations=[_rel(other, "B", "A")])
    result = write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "B")])
    assert result.written == (derive_rel_id(graph.course, "PREREQUISITE", "A", "B"),)
    assert _pairs(graph) == [("A", "B")] and _pairs(graph, course=other) == [("B", "A")]
    # 端点只在另一课程存在：悬空。
    graph.kp("X", course_id=other)
    with pytest.raises(DanglingEndpointError):
        write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "X")])


@live
def test_live_task_retry_is_idempotent_and_contributions_accumulate(graph):
    chunk = _chunk(graph.course)
    graph.kp("A", "B")
    rel = _ai(graph.course, "A", "B", chunk)
    first = write_relations(graph.repo, _scope(graph.course), relations=[rel], task_id="t1", chunks=[chunk])
    again = write_relations(graph.repo, _scope(graph.course), relations=[rel], task_id="t1", chunks=[chunk])
    assert first.created == (rel.rel_id,) and again.written == (rel.rel_id,)
    later = write_relations(graph.repo, _scope(graph.course, ("t1",)), relations=[rel], task_id="t2",
                            chunks=[chunk])
    assert later.created == ()
    [edge] = _edges(graph)
    p = edge["p"]
    assert p["contrib_tasks"] == ["t1", "t2"] and p["contrib_manual"] is False
    assert sorted(json.loads(x) for x in p["source_pairs"]) == [["t1", chunk.chunk_id], ["t2", chunk.chunk_id]]
    assert p["source"] == "ai" and p["status"] == "draft" and p["revision"] == 1
    [ri] = graph.q("MATCH (ri:RelationIdentity {course_id: $c, version_id: 'draft', rel_id: $r}) "
                   "RETURN properties(ri) AS p", c=graph.course, r=rel.rel_id)
    assert ri["p"]["type"] == "PREREQUISITE" and (ri["p"]["from_id"], ri["p"]["to_id"]) == ("A", "B")


@live
def test_live_manual_duplicate_of_a_visible_relation_is_rejected(graph):
    graph.kp("A", "B")
    rel = _rel(graph.course, "A", "B", type="RELATED_TO")
    write_relations(graph.repo, _scope(graph.course), relations=[rel])
    with pytest.raises(DuplicateRelationError) as error:
        write_relations(graph.repo, _scope(graph.course), relations=[rel])
    assert error.value.existing_id == rel.rel_id


@live
def test_live_manual_write_takes_over_an_invisible_ai_relation(graph):
    chunk = _chunk(graph.course)
    graph.kp("A", "B")
    ai = _ai(graph.course, "A", "B", chunk, confidence=0.3, status="low_confidence")
    write_relations(graph.repo, _scope(graph.course), relations=[ai], task_id="t-failed", chunks=[chunk])
    result = write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "B")])
    assert result.created == (ai.rel_id,)
    [edge] = _edges(graph)
    p = edge["p"]
    assert (p["source"], p["status"], p["confidence"], p["contrib_manual"]) == ("manual", "approved", 1.0, True)
    assert p["contrib_tasks"] == ["t-failed"] and p["revision"] == 2


@live
def test_live_ai_candidate_keeps_a_downgraded_relation_type(graph):
    """ADR-009 降级后关系 ID 不变、类型为 RELATED_TO；同一 ID 的 AI 候选只登记贡献，不改回前置。"""
    chunk = _chunk(graph.course)
    graph.kp("A", "B", "C")
    rid = derive_rel_id(graph.course, "PREREQUISITE", "C", "A")
    downgraded = DraftRelation(rel_id=rid, type="RELATED_TO", from_id="C", to_id="A", confidence=0.4,
                               status="low_confidence", source="ai", chunk_ids=(chunk.chunk_id,))
    write_relations(graph.repo, _scope(graph.course), relations=[downgraded], task_id="t1", chunks=[chunk])
    write_relations(graph.repo, _scope(graph.course, ("t1",)), relations=[_rel(graph.course, "A", "B"),
                                                                           _rel(graph.course, "B", "C")])
    result = write_relations(graph.repo, _scope(graph.course, ("t1",)),
                             relations=[_ai(graph.course, "C", "A", chunk)], task_id="t2", chunks=[chunk])
    assert result.kept_type == (rid,)
    assert _pairs(graph) == [("A", "B"), ("B", "C")]
    [edge] = _edges(graph, type="RELATED_TO")
    assert edge["p"]["contrib_tasks"] == ["t1", "t2"]


@live
def test_live_ai_candidate_whose_id_was_repointed_is_skipped(graph):
    """同一 rel_id 已指向其他端点（教师改过端点）：AI 候选跳过并报告，其余照写。"""
    chunk = _chunk(graph.course)
    graph.kp("A", "B", "C")
    rid = derive_rel_id(graph.course, "RELATED_TO", "A", "B")
    graph.q("MATCH (a:KnowledgePoint {course_id: $c, kp_id: 'A'}), (b:KnowledgePoint {course_id: $c, kp_id: 'C'}) "
            "CREATE (ri:RelationIdentity {course_id: $c, version_id: 'draft', rel_id: $r, type: 'RELATED_TO', "
            "from_id: 'A', to_id: 'C'}) "
            "CREATE (a)-[:RELATED_TO {course_id: $c, version_id: 'draft', rel_id: $r, status: 'approved', "
            "source: 'manual', confidence: 1.0, contrib_manual: true, contrib_tasks: [], source_pairs: [], "
            "revision: 2}]->(b)", c=graph.course, r=rid)
    ok = _ai(graph.course, "B", "C", chunk, type="RELATED_TO")
    result = write_relations(graph.repo, _scope(graph.course), task_id="t1", chunks=[chunk],
                             relations=[_ai(graph.course, "A", "B", chunk, type="RELATED_TO"), ok])
    assert result.conflicts == (rid,) and result.written == (ok.rel_id,)
    assert sorted(_pairs(graph, type="RELATED_TO")) == [("A", "C"), ("B", "C")]
    with pytest.raises(DuplicateRelationError):
        write_relations(graph.repo, _scope(graph.course), relations=[_rel(graph.course, "A", "B", type="RELATED_TO")])
