"""Storage projection roundtrip and visible scope, independent of model quality."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.repositories.neo4j import GraphScope, GraphScopeError


def snapshot():
    return dict(course_id="c", nodes=[dict(kp_id="a", course_id="c", name="A", contrib_tasks=["t"])],
        edges=[], chapters=[], evidence=[dict(kp_id="a", chunk_id="ch", document_id="d", revision_id="r",
        props=dict(task_id="t", chunk_id="ch", evidence_start=0, evidence_end=1))])


def test_projection_writer_refuses_legacy_or_published_targets():
    from app.repositories.graph_projection import write_snapshot
    for scope in (GraphScope("c", "draft", ()), GraphScope("c", "published")):
        tx = SimpleNamespace(scope=scope, run=lambda *a: pytest.fail("must reject before writing"))
        with pytest.raises(GraphScopeError): write_snapshot(tx, snapshot())


def test_projection_writer_does_not_trust_payload_scope_and_preserves_input():
    from app.repositories.graph_projection import write_snapshot
    data = snapshot(); original = deepcopy(data)
    calls = []
    def run(q, p=None):
        calls.append((q, p))
        return [dict(seq=1)] if "DraftWriteGuard" in q else []
    tx = SimpleNamespace(scope=GraphScope("c", "draft", ("t",), storage_version_id="draftgen_one"),
                         run=run)
    write_snapshot(tx, data)
    assert data == original and calls
    assert all("$course_id" in q and "$version_id" in q and "$effective_task_ids" in q for q, _ in calls)
    data["nodes"][0]["course_id"] = "other"
    calls.clear()
    with pytest.raises(ValueError): write_snapshot(tx, data)
    assert not calls


def test_read_normalizes_storage_version_and_preserves_evidence_contributors():
    from app.repositories.graph_projection import read_snapshot
    def read(query, scope, **kwargs):
        if "fusion:nodes" in query:
            return [dict(p=dict(kp_id="a", course_id="c", version_id="draftgen_one", contrib_tasks=["t"]))]
        if "fusion:evidence" in query:
            return [dict(kp_id="a", chunk_id="ch", document_id="d", revision_id="r",
                         props=dict(task_id="t", evidence_start=0, evidence_end=1))]
        return []
    result = read_snapshot(SimpleNamespace(read=read), GraphScope("c", "draft", ("t",), storage_version_id="draftgen_one"))
    assert "version_id" not in result["nodes"][0]
    assert result["evidence"][0]["props"]["task_id"] == "t"


def test_published_version_cleanup_never_discovers_draft_generations():
    from app.repositories.graph_read import stored_version_ids
    repo = SimpleNamespace(read=lambda *a, **kw: [dict(version_id="draftgen_one"), dict(version_id="published")])
    assert stored_version_ids(repo, "c") == {"published"}
