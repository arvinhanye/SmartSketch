"""J02 graph retrieval against a published Neo4j copy."""
from __future__ import annotations

import os
import uuid

import pytest

from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_search import search_graph
from app.repositories.neo4j import Neo4jRepository
from app.services.versions.resolver import PublishedVersion

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
live = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV), reason="isolated Neo4j fixture not configured")


@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "j02-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)

    def q(query, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w", database_="neo4j").records]

    def node(kp_id, *, version="v1", course_id=None, name=None, aliases=None):
        q("CREATE (:KnowledgePoint {course_id: $c, version_id: $v, kp_id: $id, name: $name, aliases: $aliases})",
          c=course_id or course, v=version, id=kp_id, name=name or kp_id, aliases=aliases or [])

    def edge(a, b, kind="PREREQUISITE", *, version="v1", rel_id=None):
        q(f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $a}}), "
          f"(b:KnowledgePoint {{course_id: $c, version_id: $v, kp_id: $b}}) "
          f"CREATE (a)-[:{kind} {{course_id: $c, version_id: $v, rel_id: $rid}}]->(b)",
          c=course, v=version, a=a, b=b, rid=rel_id or a + "-" + b)

    try:
        yield course, Neo4jRepository(driver), node, edge, q
    finally:
        q("MATCH (n) WHERE n.course_id = $c OR n.course_id = $foreign DETACH DELETE n",
          c=course, foreign="foreign-" + course)
        driver.close()


def bound(course, version="v1"):
    return PublishedVersion(course, version, 1, frozenset()).graph_scope()


def test_requires_search_term_and_bounded_limits():
    with pytest.raises(ValueError):
        search_graph(None, bound("c"))
    for options in ({"max_hops": 3}, {"max_nodes": 33}, {"max_edges": 129}, {"max_hops": -1}):
        with pytest.raises(ValueError):
            search_graph(None, bound("c"), term="graph", **options)


def test_bounded_traversal_uses_one_request_scope():
    class Repo:
        def __init__(self):
            self.calls = []

        def read(self, query, scope, *, reader, parameters):
            self.calls.append((scope.course_id, scope.version_id, reader, parameters))
            if "AS from_id" in query:
                return [{"from_id": "a", "to_id": "b", "type": "RELATED_TO", "rel_id": "ab"}]
            if "AS kp_id" in query:
                return [{"node": {"kp_id": "b"}}]
            return [{"node": {"kp_id": "a"}}]

    repo = Repo()
    result = search_graph(repo, bound("course-1", "version-1"), kp_id="a", max_hops=1, max_nodes=2)
    assert [n["kp_id"] for n in result.nodes] == ["a", "b"]
    assert [(e["from_id"], e["to_id"]) for e in result.edges] == [("a", "b")]
    assert len(repo.calls) == 3
    assert {(course, version, reader) for course, version, reader, _ in repo.calls} == {
        ("course-1", "version-1", "student")}
    assert repo.calls[1][3]["limit"] == 1


@live
def test_search_expands_two_hops_and_preserves_direction(graph):
    course, repo, node, edge, _ = graph
    for kp in ("a", "b", "c", "d"):
        node(kp, name="Graphs" if kp == "a" else kp)
    edge("b", "a")
    edge("b", "c", "RELATED_TO")
    edge("c", "d")
    result = search_graph(repo, bound(course), term="graph")
    assert [n["kp_id"] for n in result.nodes] == ["a", "b", "c"]
    assert [(e["from_id"], e["to_id"], e["type"]) for e in result.edges] == [
        ("b", "a", "PREREQUISITE"), ("b", "c", "RELATED_TO")]


@live
def test_search_enforces_course_version_and_empty_result(graph):
    course, repo, node, edge, _ = graph
    node("a", name="Tree", aliases=["arbor"])
    node("old", version="v0", name="Tree")
    node("draft", version="draft", name="Tree")
    node("foreign", course_id="foreign-" + course, name="Tree")
    assert [n["kp_id"] for n in search_graph(repo, bound(course), term="ARBOR").nodes] == ["a"]
    assert [n["kp_id"] for n in search_graph(repo, bound(course), kp_id="foreign", term="Tree").nodes] == ["a"]
    assert search_graph(repo, bound(course), term="missing").nodes == []
    assert search_graph(repo, bound(course), term="missing").edges == []


@live
def test_search_caps_nodes_and_edges_deterministically(graph):
    course, repo, node, edge, _ = graph
    node("hub")
    for i in range(12):
        kp = f"n{i:02d}"
        node(kp)
        edge("hub", kp)
    result = search_graph(repo, bound(course), kp_id="hub", max_hops=1, max_nodes=4, max_edges=2)
    assert [n["kp_id"] for n in result.nodes] == ["hub", "n00", "n01", "n02"]
    assert [(e["from_id"], e["to_id"]) for e in result.edges] == [("hub", "n00"), ("hub", "n01")]
