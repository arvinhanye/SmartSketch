"""F04：草稿节点与来源关联批量写入（specs/task-processing.md §8.4「贡献记录」「草稿可见性」；
specs/teacher-review-publish.md「节点加锁」；ADR-011 修订 1）。

验收：重试幂等；教师加锁节点不被覆盖（ArvinHan 2026-09-26：加锁节点内容与来源完全不动，只记为跳过）；
跨课程来源被拒绝；批量部分失败有记录。

前半部分用假驱动，任何环境都跑；后半部分连真实 Neo4j 5.26，只在设置
``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行，每个用例使用独立课程 ID 并只清理自己的数据。
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest

from app.repositories.chunks import StoredChunk
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_nodes import (
    DRAFT_VERSION,
    DraftNode,
    NodeSource,
    RejectReason,
    derive_kp_id,
    write_draft_nodes,
)
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, RepositoryError
from app.services.chunk_identity import text_sha256
from app.services.chunking import ChunkSource
from app.services.parsers.models import SourceLocator

TASK = "task-1"
SECRET = "绝密定义-不得进入错误信息"
REVISION = "rev_" + "a" * 64


def _chunk(course: str, ordinal: int, text: str = "栈是一种后进先出的线性表。队列是先进先出的线性表。") -> StoredChunk:
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


def _source(chunk: StoredChunk, start: int = 0, end: int = 5) -> NodeSource:
    return NodeSource(chunk_id=chunk.chunk_id, document_id=chunk.material_id, revision_id=chunk.revision_id,
                      evidence_start=start, evidence_end=end)


def _node(kp_id: str, chunk: StoredChunk, **overrides: object) -> DraftNode:
    values: dict[str, object] = dict(
        kp_id=kp_id, name="栈", type="concept", definition="后进先出的线性表", confidence=0.9,
        status="draft", aliases=(), sources=(_source(chunk),),
    )
    values.update(overrides)
    return DraftNode(**values)  # type: ignore[arg-type]


def _scope(course: str, v: tuple[str, ...] = ()) -> GraphScope:
    return GraphScope(course, DRAFT_VERSION, v)


class FakeDriver:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_on_call = fail_on_call

    def verify_connectivity(self) -> None: ...

    def execute_query(self, query, *, parameters_, routing_, database_):
        self.calls.append((query, parameters_))
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError(SECRET)
        rows = [{"kp_id": row["kp_id"], "locked": False, "was_visible": False} for row in parameters_["nodes"]]
        return SimpleNamespace(records=rows)

    def close(self) -> None: ...


# --- 无服务器：校验、隔离与部分失败 -----------------------------------------------------------------


def test_invalid_nodes_are_rejected_without_blocking_valid_ones():
    chunk = _chunk("c1", 0)
    driver = FakeDriver()
    nodes = [
        _node("kp-ok", chunk),
        _node("kp-type", chunk, type="person"),
        _node("kp-name", chunk, name="  "),
        _node("kp-conf", chunk, confidence=1.5),
        _node("kp-status", chunk, status="approved"),
        _node("kp-nosrc", chunk, sources=()),
    ]

    result = write_draft_nodes(Neo4jRepository(driver), _scope("c1"), task_id=TASK, nodes=nodes, chunks=[chunk])

    assert result.written == ("kp-ok",)
    assert dict(result.rejected) == {
        "kp-type": RejectReason.INVALID_NODE,
        "kp-name": RejectReason.INVALID_NODE,
        "kp-conf": RejectReason.INVALID_NODE,
        "kp-status": RejectReason.INVALID_NODE,
        "kp-nosrc": RejectReason.NO_SOURCE,
    }
    (_, params), = driver.calls
    assert [row["kp_id"] for row in params["nodes"]] == ["kp-ok"]


def test_sources_outside_the_course_are_rejected():
    mine, theirs = _chunk("c1", 0), _chunk("c2", 1)
    driver = FakeDriver()
    nodes = [
        _node("kp-foreign", mine, sources=(_source(theirs),)),  # 他课块
        _node("kp-unknown", mine, sources=(NodeSource("rev_x-9", "doc-1", "rev_x", 0, 1),)),  # 未提供的块
        _node("kp-ok", mine),
    ]

    result = write_draft_nodes(Neo4jRepository(driver), _scope("c1"), task_id=TASK, nodes=nodes,
                               chunks=[mine, theirs])

    assert result.written == ("kp-ok",)
    assert dict(result.rejected) == {
        "kp-foreign": RejectReason.SOURCE_OUTSIDE_COURSE,
        "kp-unknown": RejectReason.SOURCE_OUTSIDE_COURSE,
    }
    sent = driver.calls[0][1]["nodes"]
    assert all(s["chunk_id"] == mine.chunk_id for row in sent for s in row["sources"])


@pytest.mark.parametrize(
    "source",
    [
        lambda c: NodeSource(c.chunk_id, "other-doc", c.revision_id, 0, 5),
        lambda c: NodeSource(c.chunk_id, c.material_id, "rev_" + "b" * 64, 0, 5),
        lambda c: NodeSource(c.chunk_id, c.material_id, c.revision_id, 5, 5),
        lambda c: NodeSource(c.chunk_id, c.material_id, c.revision_id, -1, 5),
        lambda c: NodeSource(c.chunk_id, c.material_id, c.revision_id, 0, len(c.text) + 1),
    ],
)
def test_sources_that_do_not_match_their_chunk_are_invalid(source):
    chunk = _chunk("c1", 0)
    result = write_draft_nodes(Neo4jRepository(FakeDriver()), _scope("c1"), task_id=TASK,
                               nodes=[_node("kp", chunk, sources=(source(chunk),))], chunks=[chunk])
    assert dict(result.rejected) == {"kp": RejectReason.INVALID_SOURCE} and result.written == ()


def test_duplicate_kp_ids_keep_the_first():
    chunk = _chunk("c1", 0)
    result = write_draft_nodes(Neo4jRepository(FakeDriver()), _scope("c1"), task_id=TASK,
                               nodes=[_node("kp", chunk), _node("kp", chunk, name="队列")], chunks=[chunk])
    assert result.written == ("kp",) and dict(result.rejected) == {"kp": RejectReason.DUPLICATE_KP_ID}


def test_a_failed_batch_is_recorded_and_later_batches_still_run(caplog):
    chunk = _chunk("c1", 0)
    driver = FakeDriver(fail_on_call=2)
    nodes = [_node(f"kp-{i}", chunk, definition=SECRET) for i in range(5)]

    result = write_draft_nodes(Neo4jRepository(driver), _scope("c1"), task_id=TASK, nodes=nodes, chunks=[chunk],
                               batch_size=2)

    assert len(driver.calls) == 3
    assert result.written == ("kp-0", "kp-1", "kp-4")
    assert dict(result.rejected) == {"kp-2": RejectReason.WRITE_FAILED, "kp-3": RejectReason.WRITE_FAILED}
    assert SECRET not in caplog.text and SECRET not in repr(result)


def test_scope_must_be_the_draft_with_v_and_task_is_required():
    chunk = _chunk("c1", 0)
    repo = Neo4jRepository(FakeDriver())
    with pytest.raises(GraphScopeError):
        write_draft_nodes(repo, GraphScope("c1", "01VERSION"), task_id=TASK, nodes=[_node("kp", chunk)],
                          chunks=[chunk])
    with pytest.raises(GraphScopeError):
        write_draft_nodes(repo, GraphScope("c1", DRAFT_VERSION), task_id=TASK, nodes=[_node("kp", chunk)],
                          chunks=[chunk])
    with pytest.raises(ValueError):
        write_draft_nodes(repo, _scope("c1"), task_id=" ", nodes=[_node("kp", chunk)], chunks=[chunk])
    with pytest.raises(ValueError):
        write_draft_nodes(repo, _scope("c1"), task_id=TASK, nodes=[_node("kp", chunk)], chunks=[chunk],
                          batch_size=0)


def test_empty_input_does_not_contact_the_driver():
    driver = FakeDriver()
    result = write_draft_nodes(Neo4jRepository(driver), _scope("c1"), task_id=TASK, nodes=[], chunks=[])
    assert driver.calls == [] and result.written == () and result.rejected == ()


def test_derive_kp_id_is_deterministic_and_scoped():
    assert derive_kp_id("c1", "t1", "tent_x") == derive_kp_id("c1", "t1", "tent_x")
    assert derive_kp_id("c1", "t1", "tent_x") != derive_kp_id("c2", "t1", "tent_x")
    assert derive_kp_id("c1", "t1", "tent_x") != derive_kp_id("c1", "t2", "tent_x")
    assert derive_kp_id("c1", "t1", "tent_x").startswith("kp_")


def test_node_repr_hides_text():
    chunk = _chunk("c1", 0)
    assert SECRET not in repr(_node("kp", chunk, definition=SECRET))


# --- 真实 Neo4j --------------------------------------------------------------------------------

_LIVE = all(os.environ.get(name) for name in (
    "SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD"))
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "f04-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(
        os.environ["SMARTSKETCH_TEST_NEO4J_URI"],
        auth=(os.environ["SMARTSKETCH_TEST_NEO4J_USER"], os.environ["SMARTSKETCH_TEST_NEO4J_PASSWORD"]),
    )
    apply_migrations(driver)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    try:
        yield SimpleNamespace(course=course, repo=Neo4jRepository(driver), q=q)
    finally:
        for c in (course, course + "-other"):
            q("MATCH (n {course_id: $c}) DETACH DELETE n", c=c)
        driver.close()


def _kp(graph, kp_id: str, course: str | None = None):
    rows = graph.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k}) RETURN properties(n) AS p",
                   c=course or graph.course, k=kp_id)
    return rows[0]["p"] if rows else None


def _links(graph, kp_id: str):
    return sorted(
        (r["task"], r["chunk"], r["start"], r["end"])
        for r in graph.q(
            "MATCH (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k})-[r:EVIDENCED_BY]->(ch:Chunk) "
            "RETURN r.task_id AS task, ch.chunk_id AS chunk, r.evidence_start AS start, r.evidence_end AS end",
            c=graph.course, k=kp_id)
    )


@live
def test_live_writes_nodes_chunks_and_task_scoped_sources(graph):
    a, b = _chunk(graph.course, 0), _chunk(graph.course, 1)
    node = _node("kp-1", a, aliases=("stack",), sources=(_source(a, 0, 5), _source(b, 6, 12)))

    result = write_draft_nodes(graph.repo, _scope(graph.course), task_id=TASK, nodes=[node], chunks=[a, b])

    assert result.written == ("kp-1",) and result.created == ("kp-1",) and result.skipped_locked == ()
    props = _kp(graph, "kp-1")
    assert props["name"] == "栈" and props["type"] == "concept" and props["definition"] == "后进先出的线性表"
    assert props["confidence"] == 0.9 and props["status"] == "draft" and props["aliases"] == ["stack"]
    assert props["source"] == "ai" and props["locked"] is False and props["contrib_manual"] is False
    assert props["contrib_tasks"] == [TASK] and props["revision"] == 1 and props["level"] == 0
    assert _links(graph, "kp-1") == [(TASK, a.chunk_id, 0, 5), (TASK, b.chunk_id, 6, 12)]
    chunks = graph.q("MATCH (c:Chunk {course_id: $c}) RETURN c.chunk_id AS id, c.document_id AS doc, "
                     "c.revision_id AS rev ORDER BY id", c=graph.course)
    assert chunks == [{"id": a.chunk_id, "doc": "doc-1", "rev": REVISION},
                      {"id": b.chunk_id, "doc": "doc-1", "rev": REVISION}]


@live
def test_live_retry_is_idempotent(graph):
    a = _chunk(graph.course, 0)
    nodes = [_node("kp-1", a), _node("kp-2", a, name="队列", sources=(_source(a, 13, 20),))]
    write_draft_nodes(graph.repo, _scope(graph.course), task_id=TASK, nodes=nodes, chunks=[a])
    before = graph.q("MATCH (n {course_id: $c}) OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n) AS n, "
                     "count(r) AS r", c=graph.course)

    again = write_draft_nodes(graph.repo, _scope(graph.course), task_id=TASK, nodes=nodes, chunks=[a])

    after = graph.q("MATCH (n {course_id: $c}) OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n) AS n, "
                    "count(r) AS r", c=graph.course)
    assert before == after
    assert again.written == ("kp-1", "kp-2")
    assert _kp(graph, "kp-1")["contrib_tasks"] == [TASK] and _kp(graph, "kp-1")["revision"] == 1


@live
def test_live_second_task_adds_its_contribution_and_sources(graph):
    a, b = _chunk(graph.course, 0), _chunk(graph.course, 1)
    write_draft_nodes(graph.repo, _scope(graph.course), task_id="task-1", nodes=[_node("kp-1", a)], chunks=[a])

    result = write_draft_nodes(graph.repo, _scope(graph.course, ("task-1",)), task_id="task-2",
                               nodes=[_node("kp-1", b, definition="新定义", sources=(_source(b, 0, 3),))],
                               chunks=[b])

    assert result.created == () and result.written == ("kp-1",)  # 已对教师可见的节点 → 更新
    props = _kp(graph, "kp-1")
    assert props["contrib_tasks"] == ["task-1", "task-2"]
    assert props["definition"] == "新定义" and props["revision"] == 2
    assert _links(graph, "kp-1") == [("task-1", a.chunk_id, 0, 5), ("task-2", b.chunk_id, 0, 3)]


@live
def test_live_node_left_by_an_invisible_task_counts_as_created(graph):
    a = _chunk(graph.course, 0)
    write_draft_nodes(graph.repo, _scope(graph.course), task_id="failed-task", nodes=[_node("kp-1", a)], chunks=[a])

    result = write_draft_nodes(graph.repo, _scope(graph.course, ()), task_id="task-2", nodes=[_node("kp-1", a)],
                               chunks=[a])

    assert result.created == ("kp-1",)


@live
def test_live_locked_node_is_left_completely_untouched(graph):
    a = _chunk(graph.course, 0)
    graph.q("CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'kp-locked', name: '教师写的名',"
            " definition: '教师写的定义', type: 'concept', status: 'approved', source: 'manual', locked: true,"
            " contrib_manual: true, contrib_tasks: [], revision: 3, level: 0, confidence: 1.0})", c=graph.course)

    result = write_draft_nodes(graph.repo, _scope(graph.course), task_id=TASK,
                               nodes=[_node("kp-locked", a), _node("kp-free", a)], chunks=[a])

    assert result.skipped_locked == ("kp-locked",) and result.written == ("kp-free",)
    props = _kp(graph, "kp-locked")
    assert props["name"] == "教师写的名" and props["definition"] == "教师写的定义"
    assert props["contrib_tasks"] == [] and props["revision"] == 3 and props["status"] == "approved"
    assert _links(graph, "kp-locked") == []


@live
def test_live_writes_stay_inside_the_course(graph):
    other = graph.course + "-other"
    a, x = _chunk(graph.course, 0), _chunk(other, 0)
    write_draft_nodes(graph.repo, _scope(other), task_id=TASK, nodes=[_node("kp-1", x, name="别课")], chunks=[x])

    write_draft_nodes(graph.repo, _scope(graph.course), task_id=TASK, nodes=[_node("kp-1", a)], chunks=[a])

    assert _kp(graph, "kp-1", other)["name"] == "别课"
    assert _kp(graph, "kp-1")["name"] == "栈"
    cross = graph.q("MATCH (n:KnowledgePoint {course_id: $c})-[:EVIDENCED_BY]->(ch:Chunk) "
                    "WHERE ch.course_id <> n.course_id RETURN count(*) AS n", c=graph.course)
    assert cross == [{"n": 0}]


@live
def test_live_published_versions_are_never_written(graph):
    a = _chunk(graph.course, 0)
    graph.q("CREATE (:KnowledgePoint {course_id: $c, version_id: '01PUBLISHED', kp_id: 'kp-1', name: '发布版'})",
            c=graph.course)

    write_draft_nodes(graph.repo, _scope(graph.course), task_id=TASK, nodes=[_node("kp-1", a)], chunks=[a])

    rows = graph.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: '01PUBLISHED'}) RETURN n.name AS name",
                   c=graph.course)
    assert rows == [{"name": "发布版"}]


def test_repository_error_is_redacted():
    """驱动异常经 F02 统一脱敏为 RepositoryError（本模块再转成 write_failed）。"""
    driver = FakeDriver(fail_on_call=1)
    chunk = _chunk("c1", 0)
    with pytest.raises(RepositoryError):
        Neo4jRepository(driver).write("RETURN $course_id, $version_id, $effective_task_ids",
                                      _scope("c1"))
    result = write_draft_nodes(Neo4jRepository(FakeDriver(fail_on_call=1)), _scope("c1"), task_id=TASK,
                               nodes=[_node("kp", chunk)], chunks=[chunk])
    assert dict(result.rejected) == {"kp": RejectReason.WRITE_FAILED}
