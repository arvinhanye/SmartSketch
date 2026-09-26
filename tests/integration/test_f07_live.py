"""F07 against a real Neo4j: ``GraphReader``'s draft visibility (V) and published-copy queries.

Gated like the other live graph suites by ``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD``.
"""

from __future__ import annotations

import json
import os
import uuid
from types import SimpleNamespace

import pytest

from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_read import GraphReader, NodeEvidence
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
live = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV), reason="isolated Neo4j fixture not configured")

_SEED = """
UNWIND $nodes AS n
CREATE (:KnowledgePoint {course_id: $c, version_id: n.v, kp_id: n.id, name: n.id, type: 'concept',
                         definition: 'd', status: 'draft', source: 'ai', confidence: 0.9, locked: false,
                         revision: 1, contrib_manual: n.manual, contrib_tasks: n.tasks})
"""
@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "f07-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    def node(kp_id, *, version="draft", tasks=(), manual=False):
        q(_SEED, c=course, nodes=[{"v": version, "id": kp_id, "tasks": list(tasks), "manual": manual}])

    def rel(kind, a, b, *, version="draft", tasks=(), manual=False, **props):
        q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $a}}), "
          f"(b:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $b}}) "
          f"CREATE (a)-[r:{kind}]->(b) SET r += $p",
          c=course, v=version, a=a, b=b,
          p={"course_id": course, "version_id": version, "rel_id": f"rel_{a}_{b}", "status": "draft",
             "source": "ai", "confidence": 0.8, "contrib_tasks": list(tasks), "contrib_manual": manual, **props})

    def evidence(kp_id, chunk_id, task_id, start, *, version="draft"):
        q("MATCH (n:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $k}) "
          "MERGE (ch:Chunk {course_id: $c, chunk_id: $chunk}) ON CREATE SET ch.document_id = 'doc1' "
          "CREATE (n)-[e:EVIDENCED_BY {chunk_id: $chunk, evidence_start: $s, evidence_end: $s + 2}]->(ch) "
          "SET e.task_id = $t",
          c=course, v=version, k=kp_id, chunk=chunk_id, t=task_id, s=start)

    try:
        yield SimpleNamespace(course=course, reader=GraphReader(Neo4jRepository(driver)), q=q, node=node,
                              rel=rel, evidence=evidence)
    finally:
        q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)
        driver.close()


def _draft(graph, v):
    return GraphScope(graph.course, "draft", effective_task_ids=list(v))


@live
def test_live_draft_nodes_and_edges_follow_effective_tasks(graph):
    graph.node("manual", manual=True)
    graph.node("ok", tasks=["t-ok"])
    graph.node("mixed", tasks=["t-running", "t-ok"])
    graph.node("hidden", tasks=["t-running"])
    graph.rel("PREREQUISITE", "manual", "ok", tasks=["t-ok"])
    graph.rel("RELATED_TO", "ok", "mixed", tasks=["t-running"])  # relation itself not visible
    graph.rel("EXAMPLE_OF", "ok", "hidden", manual=True)  # endpoint not visible
    graph.rel("CONTAINS", "manual", "mixed", manual=True)

    scope = _draft(graph, ["t-ok"])
    assert [p["kp_id"] for p in graph.reader.nodes(scope, "teacher")] == ["manual", "mixed", "ok"]
    edges = {(e["type"], e["from_id"], e["to_id"]) for e in graph.reader.edges(scope, "teacher")}
    assert edges == {("PREREQUISITE", "manual", "ok"), ("CONTAINS", "manual", "mixed")}
    assert {(e["from_id"], e["to_id"]) for e in graph.reader.edges(scope, "teacher", ["ok"])} == {("manual", "ok")}

    empty = _draft(graph, [])
    assert [p["kp_id"] for p in graph.reader.nodes(empty, "teacher")] == ["manual"]
    assert graph.reader.edges(empty, "teacher") == []


@live
def test_live_draft_evidence_skips_links_from_invisible_tasks(graph):
    graph.node("a", tasks=["t-ok"], manual=True)
    graph.evidence("a", "c1", "t-ok", 0)
    graph.evidence("a", "c2", "t-running", 4)
    graph.evidence("a", "c3", None, 8)
    rows = graph.reader.evidence(_draft(graph, ["t-ok"]), "teacher", ["a"])
    assert rows == [NodeEvidence("a", "c1", "doc1", 0, 2), NodeEvidence("a", "c3", "doc1", 8, 10)]


@live
def test_live_published_copy_is_read_whole_and_isolated_by_version_and_course(graph):
    graph.node("a", version="ver-1")
    graph.node("b", version="ver-1")
    graph.node("draft-only", tasks=["t-ok"])
    graph.rel("PREREQUISITE", "a", "b", version="ver-1", source_pairs=[json.dumps(["t-x", "c1"])])
    graph.evidence("a", "c1", "t-gone", 0, version="ver-1")
    graph.q("CREATE (:KnowledgePoint {course_id: 'other-' + $c, version_id: 'ver-1', kp_id: 'a', name: 'x'})",
            c=graph.course)
    graph.q("CREATE (:Chapter {course_id: $c, version_id: 'ver-1', chapter_id: 'ch1', title: '第一章', order: 1})",
            c=graph.course)
    try:
        scope = GraphScope(graph.course, "ver-1")
        assert [p["kp_id"] for p in graph.reader.nodes(scope, "student")] == ["a", "b"]
        [edge] = graph.reader.edges(scope, "student")
        assert (edge["type"], edge["from_id"], edge["to_id"]) == ("PREREQUISITE", "a", "b")
        assert edge["p"]["source_pairs"] == [json.dumps(["t-x", "c1"])]
        assert [e.chunk_id for e in graph.reader.evidence(scope, "student", ["a"])] == ["c1"]
        assert [p["chapter_id"] for p in graph.reader.chapters(scope, "student")] == ["ch1"]
    finally:
        graph.q("MATCH (n {course_id: 'other-' + $c}) DETACH DELETE n", c=graph.course)


@live
def test_live_student_can_never_read_the_draft(graph):
    graph.node("a", manual=True)
    with pytest.raises(GraphScopeError):
        graph.reader.nodes(_draft(graph, []), "student")
