"""G03 against a real Neo4j: materialize a snapshot as an isolated version graph with vectors.

Acceptance: students keep reading the old version while a new one is built; a vector from
another space or with the wrong dimensions fails; retrying the same version does not
duplicate the graph (specs/teacher-review-publish.md V5 P8/P9, V12).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.repositories.graph_migrations import VectorSpaceError, apply_migrations, vector_property
from app.repositories.graph_read import GraphReader
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient
from app.services.versions.materialize import (
    MaterializeError,
    VerificationError,
    drop_version,
    embed_snapshot_nodes,
    materialize,
    node_embedding_text,
    verify,
)
from app.services.versions.snapshot import (
    DraftChapter,
    DraftEdge,
    DraftGraph,
    DraftNode,
    Revision,
    build_snapshot,
)

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
live = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV), reason="isolated Neo4j fixture not configured")

SPACE = "fake/4"


@dataclass(frozen=True)
class Vec:
    values: tuple[float, ...]
    space: str = SPACE


def embedder():
    return EmbeddingAdapter(Settings(EMBEDDING_MODE="fake", EMBEDDING_MODEL="", EMBEDDING_DIMENSIONS=4,
                                     EMBEDDING_BATCH_SIZE=8), FakeEmbeddingClient())


def snapshot_for(course, *, extra_node=False, name="栈"):
    nodes = [DraftNode("a", name, "concept", "后进先出的线性表", "approved", aliases=("LIFO",), chapter_id="ch1",
                       difficulty=0.4, source_refs=("c1", "c2")),
             DraftNode("b", "队列", "concept", "先进先出", "draft", source_refs=("c2",), merged_from=("old",)),
             DraftNode("x", "低置信", "concept", "d", "low_confidence")]
    if extra_node:
        nodes.append(DraftNode("c", "双端队列", "method", "两端进出", "draft"))
    edges = [DraftEdge("r1", "PREREQUISITE", "a", "b", "draft", source_refs=("c1",)),
             DraftEdge("r2", "RELATED_TO", "b", "a", "approved"),
             DraftEdge("r3", "EXAMPLE_OF", "x", "a", "draft")]
    draft = DraftGraph(course, [Revision("rev1", "m1", "sha256:" + "a" * 64, "p")],
                       [DraftChapter("ch1", "第一章", 1)], nodes, edges, {"c1": "rev1", "c2": "rev1"})
    return build_snapshot(draft).snapshot


@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "g03-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    q("UNWIND ['c1', 'c2'] AS id CREATE (:Chunk {course_id: $c, chunk_id: id, revision_id: 'rev1'})", c=course)
    try:
        yield SimpleNamespace(course=course, repo=Neo4jRepository(driver), q=q)
    finally:
        q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)
        driver.close()


def counts(graph, version_id):
    [row] = graph.q(
        "MATCH (n {course_id: $c, version_id: $v}) WITH count(n) AS nodes "
        "OPTIONAL MATCH ()-[r {course_id: $c, version_id: $v}]->() WITH nodes, count(r) AS rels "
        "OPTIONAL MATCH (:KnowledgePoint {course_id: $c, version_id: $v})-[e:EVIDENCED_BY]->() "
        "RETURN nodes, rels, count(e) AS evidence", c=graph.course, v=version_id)
    return row


def build(graph, snapshot, version_id, vectors=None):
    vectors = embed_snapshot_nodes(embedder(), snapshot) if vectors is None else vectors
    return materialize(graph.repo, snapshot, version_id, vectors, lambda: SPACE)


@live
def test_live_materialize_then_verify_round_trips_the_snapshot(graph):
    snapshot = snapshot_for(graph.course)
    result = build(graph, snapshot, "ver-1")
    assert (result.chapters, result.nodes, result.edges, result.evidence) == (1, 2, 2, 3)
    verify(graph.repo, snapshot, "ver-1", SPACE)
    [node] = graph.q(f"MATCH (k:KnowledgePoint {{course_id: $c, version_id: 'ver-1', kp_id: 'a'}}) "
                     f"RETURN properties(k) AS p", c=graph.course)
    props = node["p"]
    assert len(props[vector_property(SPACE)]) == 4
    for draft_only in ("status", "confidence", "locked", "source", "revision", "contrib_tasks"):
        assert draft_only not in props


@live
def test_live_retry_rebuilds_without_duplicates(graph):
    first = snapshot_for(graph.course)
    build(graph, first, "ver-1")
    before = counts(graph, "ver-1")
    build(graph, first, "ver-1")
    assert counts(graph, "ver-1") == before
    changed = snapshot_for(graph.course, extra_node=True)
    build(graph, changed, "ver-1")  # a retried attempt always rebuilds from its own snapshot
    verify(graph.repo, changed, "ver-1", SPACE)
    assert counts(graph, "ver-1")["nodes"] == before["nodes"] + 1


@live
def test_live_students_keep_reading_the_old_version_while_a_new_one_builds(graph):
    old = snapshot_for(graph.course)
    build(graph, old, "ver-1")
    build(graph, snapshot_for(graph.course, extra_node=True, name="新栈"), "ver-2")
    reader = GraphReader(graph.repo)
    names = {p["name"] for p in reader.nodes(GraphScope(graph.course, "ver-1"), "student")}
    assert names == {"栈", "队列"}
    assert all("embedding" not in key for p in reader.nodes(GraphScope(graph.course, "ver-1"), "student")
               for key in p)


@live
@pytest.mark.parametrize("bad", [Vec((0.1, 0.2, 0.3, 0.4), space="real/other/4"),
                                 Vec((0.1, 0.2, 0.3)), Vec((0.1, float("nan"), 0.3, 0.4))])
def test_live_foreign_or_malformed_vectors_fail_before_writing(graph, bad):
    snapshot = snapshot_for(graph.course)
    vectors = dict(embed_snapshot_nodes(embedder(), snapshot))
    vectors["a"] = bad
    with pytest.raises(VectorSpaceError):
        build(graph, snapshot, "ver-1", vectors)
    assert counts(graph, "ver-1")["nodes"] == 0


@live
def test_live_missing_vector_or_chunk_rolls_everything_back(graph):
    snapshot = snapshot_for(graph.course)
    vectors = dict(embed_snapshot_nodes(embedder(), snapshot))
    with pytest.raises(VectorSpaceError):
        build(graph, snapshot, "ver-1", {k: v for k, v in vectors.items() if k != "b"})
    graph.q("MATCH (c:Chunk {course_id: $c, chunk_id: 'c2'}) DELETE c", c=graph.course)
    with pytest.raises(MaterializeError):
        build(graph, snapshot, "ver-1", vectors)
    assert counts(graph, "ver-1") == {"nodes": 0, "rels": 0, "evidence": 0}


@live
def test_live_verify_detects_drift_and_wrong_space(graph):
    snapshot = snapshot_for(graph.course)
    build(graph, snapshot, "ver-1")
    with pytest.raises(VerificationError):
        verify(graph.repo, snapshot, "ver-1", "real/m/4")  # vectors are not in that space
    graph.q("MATCH (k:KnowledgePoint {course_id: $c, version_id: 'ver-1', kp_id: 'b'}) SET k.name = '改过'",
            c=graph.course)
    with pytest.raises(VerificationError):
        verify(graph.repo, snapshot, "ver-1", SPACE)


@live
def test_live_drop_version_removes_only_that_version(graph):
    snapshot = snapshot_for(graph.course)
    build(graph, snapshot, "ver-1")
    build(graph, snapshot, "ver-2")
    drop_version(graph.repo, graph.course, "ver-2")
    drop_version(graph.repo, graph.course, "ver-2")
    assert counts(graph, "ver-2")["nodes"] == 0 and counts(graph, "ver-1")["nodes"] == 3
    assert graph.q("MATCH (c:Chunk {course_id: $c}) RETURN count(c) AS n", c=graph.course) == [{"n": 2}]
    with pytest.raises(ValueError):
        drop_version(graph.repo, graph.course, "draft")


def test_embedding_text_and_vectors_follow_the_snapshot():
    snapshot = snapshot_for("course-1")
    vectors = embed_snapshot_nodes(embedder(), snapshot)
    assert set(vectors) == {"a", "b"} and all(v.space == SPACE for v in vectors.values())
    assert node_embedding_text(snapshot.data["nodes"][0]) == "栈\n后进先出的线性表"


def test_materialize_refuses_the_draft_scope():
    with pytest.raises(ValueError):
        materialize(None, snapshot_for("course-1"), "draft", {}, lambda: SPACE)  # type: ignore[arg-type]


@live
def test_live_published_copy_reads_through_the_f07_service(graph, tmp_path):
    from app.repositories.sqlite import migrate
    from app.services.graph.read import GraphFilter, ReadTarget, read_graph, read_knowledge_point

    url = f"sqlite:///{(tmp_path / 's.sqlite3').as_posix()}"
    migrate(url)
    snapshot = snapshot_for(graph.course)
    build(graph, snapshot, "ver-1")
    target = ReadTarget(GraphScope(graph.course, "ver-1"), "student", 1)
    exchange = read_graph(GraphReader(graph.repo), url, target, GraphFilter())
    assert {(n.id, n.status.value, n.level) for n in exchange.nodes} == {("a", "approved", 0), ("b", "approved", 1)}
    assert {(e.root.type.value, e.root.from_id, e.root.to_id) for e in exchange.edges} == {
        ("PREREQUISITE", "a", "b"), ("RELATED_TO", "b", "a")}
    assert [c.id for c in exchange.chapters] == ["ch1"]
    with pytest.raises(Exception):  # chunks are not in this SQLite: no locatable source
        read_knowledge_point(GraphReader(graph.repo), url, target, "a")
