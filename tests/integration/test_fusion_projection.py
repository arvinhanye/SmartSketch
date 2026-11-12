"""Physical generations roundtrip on an isolated Neo4j, without modifying the old draft."""
from copy import deepcopy
import pytest
from app.repositories.graph_projection import read_snapshot, write_snapshot
from app.repositories.graph_read import GraphReader, stored_version_ids
from app.repositories.neo4j import GraphScope, GraphScopeError
from tests.integration.test_f13 import graph, live


def data(course):
    return dict(course_id=course, nodes=[dict(kp_id=k, course_id=course, name=k, definition="definition",
        type="concept", status="draft", locked=False, contrib_manual=False, contrib_tasks=["t"],
        aliases=[], revision=1) for k in ("a", "b")], chapters=[],
        edges=[dict(type="RELATED_TO", from_id="a", to_id="b", p=dict(course_id=course,
            rel_id="r", status="draft", source="ai", contrib_tasks=["t"], contrib_manual=False,
            source_pairs=['["t","ch"]'], revision=1))],
        evidence=[dict(kp_id="a", chunk_id="ch", document_id="d", revision_id="rev",
                       props=dict(task_id="t", chunk_id="ch", evidence_start=0, evidence_end=2))])


@live
def test_generation_is_invisible_to_legacy_draft_roundtrips_and_is_idempotent(graph):
    raw = data(graph.course)
    new = GraphScope(graph.course, "draft", ("t",), storage_version_id="draftgen_roundtrip")
    old = GraphScope(graph.course, "draft", ("t",))
    graph.repo.write_transaction(new, lambda tx: write_snapshot(tx, raw))
    assert read_snapshot(graph.repo, new) == raw
    assert not GraphReader(graph.repo).nodes(old, "teacher")
    graph.repo.write_transaction(new, lambda tx: write_snapshot(tx, raw))
    assert read_snapshot(graph.repo, new) == raw
    assert not stored_version_ids(graph.repo, graph.course)
    with pytest.raises(GraphScopeError): GraphReader(graph.repo).nodes(new, "student")
    changed = deepcopy(raw); changed["nodes"][0]["name"] = "bad overwrite"
    with pytest.raises(ValueError):
        graph.repo.write_transaction(new, lambda tx: write_snapshot(tx, changed))
    assert read_snapshot(graph.repo, new) == raw


@live
def test_failed_projection_transaction_leaves_no_partial_generation(graph):
    scope = GraphScope(graph.course, "draft", ("t",), storage_version_id="draftgen_rollback")
    def work(tx):
        write_snapshot(tx, data(graph.course))
        raise RuntimeError("simulated failure before commit")
    with pytest.raises(RuntimeError): graph.repo.write_transaction(scope, work)
    assert not read_snapshot(graph.repo, scope)["nodes"]
