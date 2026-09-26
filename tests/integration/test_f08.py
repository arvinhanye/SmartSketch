"""F08：教师编辑与人工编辑锁的 Cypher（``app.repositories.graph_edit``；ADR-035）。

验收：条件更新只在修订号相符时写入（后写不覆盖）；教师修改置锁并登记人工贡献；F04 自动写入跳过
加锁节点，显式解锁后又能更新；新建的人工节点带不含 ``task_id`` 的来源，V 为空时也可见。

作用域检查不需要服务器；其余连真实 Neo4j 5.26，只在设置 ``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD``
时运行，每个用例使用独立课程 ID 并只清理自己的数据。
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest

from app.repositories.chunks import StoredChunk
from app.repositories.graph_edit import DraftNodeStore
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_nodes import DraftNode, NodeSource, write_draft_nodes
from app.repositories.graph_read import GraphReader
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository
from app.services.chunk_identity import text_sha256
from app.services.chunking import ChunkSource
from app.services.parsers.models import SourceLocator

TASK = "task-1"
REVISION = "rev_" + "b" * 64
TEXT = "栈是一种后进先出的线性表。"


def _chunk(course: str) -> StoredChunk:
    return StoredChunk(chunk_id=f"{REVISION}-0", course_id=course, material_id="doc-1", revision_id=REVISION,
                       ordinal=0, text=TEXT, text_sha256=text_sha256(TEXT), section_titles=("第1章",),
                       sources=(ChunkSource(0, 0, len(TEXT), SourceLocator(page=1)),))


def _ai_node(chunk: StoredChunk, **overrides: object) -> DraftNode:
    values: dict[str, object] = dict(
        kp_id="kp-a", name="栈", type="concept", definition="后进先出的线性表", confidence=0.9, status="draft",
        sources=(NodeSource(chunk.chunk_id, chunk.material_id, chunk.revision_id, 0, 1),))
    values.update(overrides)
    return DraftNode(**values)  # type: ignore[arg-type]


def _draft(course: str, v: tuple[str, ...] = (TASK,)) -> GraphScope:
    return GraphScope(course, "draft", v)


# --- 无服务器 ------------------------------------------------------------------------------------


class _NoDriver:
    def execute_query(self, *args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("query must be rejected before reaching the driver")

    def session(self, **kwargs):  # pragma: no cover
        raise AssertionError("transaction must be rejected before reaching the driver")


@pytest.mark.parametrize("scope", [GraphScope("c1", "ver-1"), GraphScope("c1", "draft")],
                         ids=["published", "draft-without-v"])
def test_store_only_accepts_draft_scope_with_v(scope):
    store = DraftNodeStore(Neo4jRepository(_NoDriver()))
    with pytest.raises(GraphScopeError):
        store.node(scope, "kp-a")
    with pytest.raises(GraphScopeError):
        store.update(scope, "kp-a", 1, {"name": "x"})
    with pytest.raises(GraphScopeError):
        store.unlock(scope, "kp-a", 1)
    with pytest.raises(GraphScopeError):
        store.create(scope, "kp-m", {"name": "x"}, [{"chunk_id": "c"}])


def test_create_requires_a_source():
    store = DraftNodeStore(Neo4jRepository(_NoDriver()))
    with pytest.raises(ValueError):
        store.create(_draft("c1"), "kp-m", {"name": "x"}, [])


# --- 真实 Neo4j --------------------------------------------------------------------------------

_LIVE = all(os.environ.get(name) for name in (
    "SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD"))
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "f08-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(
        os.environ["SMARTSKETCH_TEST_NEO4J_URI"],
        auth=(os.environ["SMARTSKETCH_TEST_NEO4J_USER"], os.environ["SMARTSKETCH_TEST_NEO4J_PASSWORD"]),
    )
    apply_migrations(driver)
    repo = Neo4jRepository(driver)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    try:
        yield SimpleNamespace(course=course, repo=repo, store=DraftNodeStore(repo), chunk=_chunk(course), q=q)
    finally:
        q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)
        driver.close()


def _props(graph, kp_id="kp-a"):
    rows = graph.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k}) RETURN properties(n) AS p",
                   c=graph.course, k=kp_id)
    return rows[0]["p"] if rows else None


def _ai_write(graph, **overrides):
    return write_draft_nodes(graph.repo, _draft(graph.course), task_id=TASK, nodes=[_ai_node(graph.chunk, **overrides)],
                             chunks=[graph.chunk])


@live
def test_conditional_update_locks_and_later_writer_does_not_overwrite(graph):
    _ai_write(graph)
    scope = _draft(graph.course)
    assert graph.store.node(scope, "kp-a")["revision"] == 1

    first = graph.store.update(scope, "kp-a", 1, {"name": "栈（甲）", "aliases": ["stack"], "difficulty": 0.4})
    second = graph.store.update(scope, "kp-a", 1, {"name": "栈（乙）"})

    assert first["name"] == "栈（甲）" and first["locked"] is True and first["revision"] == 2
    assert first["aliases"] == ["stack"] and first["difficulty"] == 0.4 and first["source"] == "ai"
    assert second is None
    stored = _props(graph)
    assert stored["name"] == "栈（甲）" and stored["revision"] == 2
    assert stored["contrib_manual"] is True and stored["contrib_tasks"] == [TASK]
    assert graph.q("MATCH (g:DraftWriteGuard {course_id: $c}) RETURN g.seq AS s", c=graph.course)[0]["s"] == 2


@live
def test_invisible_node_is_neither_read_nor_written(graph):
    _ai_write(graph)
    hidden = _draft(graph.course, ())  # the task is not in V
    assert graph.store.node(hidden, "kp-a") is None
    assert graph.store.update(hidden, "kp-a", 1, {"name": "x"}) is None
    assert graph.store.unlock(hidden, "kp-a", 1) is None
    assert _props(graph)["name"] == "栈"


@live
def test_automated_write_respects_the_lock_until_explicit_unlock(graph):
    _ai_write(graph)
    scope = _draft(graph.course)
    graph.store.update(scope, "kp-a", 1, {"definition": "教师写的定义"})

    skipped = _ai_write(graph, definition="模型重跑的定义", confidence=0.95)

    assert skipped.skipped_locked == ("kp-a",) and skipped.written == ()
    assert _props(graph)["definition"] == "教师写的定义" and _props(graph)["revision"] == 2

    unlocked = graph.store.unlock(scope, "kp-a", 2)
    assert unlocked["locked"] is False and unlocked["revision"] == 3
    assert graph.store.unlock(scope, "kp-a", 2) is None  # stale

    rewritten = _ai_write(graph, definition="模型重跑的定义", confidence=0.95)

    assert rewritten.written == ("kp-a",)
    stored = _props(graph)
    assert stored["definition"] == "模型重跑的定义" and stored["revision"] == 4
    assert stored["contrib_manual"] is True  # §8.4: never falls back


@live
def test_manual_node_has_manual_evidence_and_is_visible_without_tasks(graph):
    scope = _draft(graph.course, ())
    chunk = graph.chunk
    created = graph.store.create(scope, "kp-m", {"name": "双端队列", "type": "concept", "definition": "两端进出",
                                                 "aliases": [], "confidence": 1.0, "status": "approved"},
                                 [{"chunk_id": chunk.chunk_id, "document_id": chunk.material_id,
                                   "revision_id": chunk.revision_id, "evidence_start": 0, "evidence_end": len(TEXT)}])

    assert created["source"] == "manual" and created["locked"] is True and created["revision"] == 1
    assert graph.store.node(scope, "kp-m")["name"] == "双端队列"
    [evidence] = GraphReader(graph.repo).evidence(scope, "teacher", ["kp-m"])
    assert (evidence.chunk_id, evidence.document_id) == (chunk.chunk_id, "doc-1")
    assert (evidence.evidence_start, evidence.evidence_end) == (0, len(TEXT))
    rows = graph.q("MATCH (:KnowledgePoint {course_id: $c, kp_id: 'kp-m'})-[e:EVIDENCED_BY]->(c:Chunk) "
                   "RETURN e.task_id AS task, c.revision_id AS rev", c=graph.course)
    assert rows == [{"task": None, "rev": REVISION}]
    assert _props(graph, "kp-m")["contrib_tasks"] == []


@live
def test_chapter_visibility(graph):
    graph.q("CREATE (:Chapter {course_id: $c, version_id: 'draft', chapter_id: 'ch-1', title: '栈', `order`: 1, "
            "contrib_manual: false, contrib_tasks: [$t]})", c=graph.course, t=TASK)
    assert graph.store.chapter_visible(_draft(graph.course), "ch-1") is True
    assert graph.store.chapter_visible(_draft(graph.course, ()), "ch-1") is False
    assert graph.store.chapter_visible(_draft(graph.course), "ch-2") is False
