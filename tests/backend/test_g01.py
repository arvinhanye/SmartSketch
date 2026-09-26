"""G01 publish snapshot: publish set, blocking reasons, canonical form, digest and round trip.

Acceptance: stable field order; missing endpoints / sources / cycles are rejected; a full
round trip loses no attribute (specs/teacher-review-publish.md V3, PUB-8～PUB-11).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import random
from pathlib import Path

import jsonschema
import pytest
import yaml

from app.services.versions.snapshot import (
    DraftChapter,
    DraftEdge,
    DraftGraph,
    DraftNode,
    Excluded,
    Revision,
    SnapshotBlocked,
    SnapshotFormatError,
    build_snapshot,
    canonical_bytes,
    digest_of,
    load_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
COURSE = "course-1"
REV = Revision("rev-1", "mat-1", "sha256:" + "a" * 64, "txt/1+chunk/1@1500-200")
CHUNKS = {"ch-a": "rev-1", "ch-b": "rev-1", "ch-old": "rev-gone"}


def node(kp_id, status="draft", **extra):
    fields = dict(kp_id=kp_id, name=f"{kp_id} 名称", type="concept", definition=f"{kp_id} 的定义", status=status,
                  source_refs=("ch-a",))
    fields.update(extra)
    return DraftNode(**fields)


def edge(rel_id, a, b, kind="PREREQUISITE", status="draft", **extra):
    return DraftEdge(rel_id=rel_id, type=kind, from_id=a, to_id=b, status=status, **extra)


def graph(nodes, edges=(), chapters=(), revisions=(REV,), chunks=None):
    return DraftGraph(COURSE, list(revisions), list(chapters), list(nodes), list(edges),
                      CHUNKS if chunks is None else chunks)


def reasons(draft):
    with pytest.raises(SnapshotBlocked) as caught:
        build_snapshot(draft)
    return [r.to_dict() for r in caught.value.reasons]


# --- publish set -----------------------------------------------------------------------------


def test_pub8_low_confidence_node_and_edge_are_excluded_with_cascade_counts():
    draft = graph(
        [node("a"), node("b", "approved"), node("c"), node("x", "low_confidence")],
        [edge("r1", "a", "b"), edge("r2", "b", "c", status="low_confidence"),
         edge("r3", "x", "a", status="approved"), edge("r4", "b", "x", "RELATED_TO", status="approved"),
         edge("r5", "a", "c", status="rejected")],
    )
    built = build_snapshot(draft)
    assert built.excluded == Excluded(low_confidence_nodes=1, low_confidence_edges=1, cascaded_edges=2)
    assert [n["kp_id"] for n in built.snapshot.data["nodes"]] == ["a", "b", "c"]
    assert [e["rel_id"] for e in built.snapshot.data["edges"]] == ["r1"]


def test_rejected_nodes_are_excluded_but_not_counted_while_their_edges_cascade():
    built = build_snapshot(graph([node("a"), node("z", "rejected")], [edge("r1", "a", "z")]))
    assert built.excluded == Excluded(0, 0, 1)
    assert [n["kp_id"] for n in built.snapshot.data["nodes"]] == ["a"]


def test_pub9_isolated_and_look_alike_nodes_are_published():
    built = build_snapshot(graph([node("a", name="栈"), node("b", name="栈"), node("lonely")]))
    assert [n["kp_id"] for n in built.snapshot.data["nodes"]] == ["a", "b", "lonely"]


def test_chapters_are_those_referenced_plus_their_ancestors():
    chapters = [DraftChapter("ch1", "第一章", 1), DraftChapter("ch1.1", "1.1", 2, parent_id="ch1"),
                DraftChapter("ch2", "第二章", 3), DraftChapter("ch3", "第三章", 4)]
    built = build_snapshot(graph([node("a", chapter_id="ch1.1"), node("x", "low_confidence", chapter_id="ch3")],
                                 chapters=chapters))
    assert built.snapshot.data["chapters"] == [
        {"chapter_id": "ch1", "order": 1, "parent_id": None, "title": "第一章"},
        {"chapter_id": "ch1.1", "order": 2, "parent_id": "ch1", "title": "1.1"},
    ]


# --- blocking reasons ------------------------------------------------------------------------


def test_cycle_in_publish_set_blocks_with_closed_path():
    draft = graph([node("a"), node("b"), node("c")],
                  [edge("r1", "a", "b"), edge("r2", "b", "c", status="approved"), edge("r3", "c", "a")])
    assert reasons(draft) == [{"kind": "cycle", "cycle": ["a", "b", "c", "a"]}]


def test_cycle_broken_by_exclusion_does_not_block():
    draft = graph([node("a"), node("b"), node("c")],
                  [edge("r1", "a", "b"), edge("r2", "b", "c", status="low_confidence"), edge("r3", "c", "a")])
    assert build_snapshot(draft).excluded.low_confidence_edges == 1


def test_non_prerequisite_loops_are_not_cycles():
    draft = graph([node("a"), node("b")], [edge("r1", "a", "b", "RELATED_TO"), edge("r2", "b", "a", "RELATED_TO")])
    assert len(build_snapshot(draft).snapshot.data["edges"]) == 2


def test_missing_endpoint_blocks_even_for_low_confidence_edges():
    draft = graph([node("a")], [edge("r1", "a", "ghost"), edge("r2", "ghost", "a", status="low_confidence"),
                                edge("r3", "a", "ghost", status="rejected")])
    assert reasons(draft) == [{"kind": "dangling_endpoint", "relation_id": "r1"},
                              {"kind": "dangling_endpoint", "relation_id": "r2"}]


def test_invalid_source_refs_block_for_nodes_and_edges_in_the_publish_set():
    draft = graph(
        [node("a", source_refs=("ch-a", "ch-foreign")), node("b", source_refs=("ch-old",)),
         node("x", "low_confidence", source_refs=("ch-foreign",))],
        [edge("r1", "a", "b", source_refs=("ch-b", "ch-missing"))],
    )
    assert reasons(draft) == [
        {"kind": "invalid_source_ref", "kp_id": "a", "chunk_id": "ch-foreign"},
        {"kind": "invalid_source_ref", "kp_id": "b", "chunk_id": "ch-old"},
        {"kind": "invalid_source_ref", "relation_id": "r1", "chunk_id": "ch-missing"},
    ]


def test_manual_entries_may_have_no_sources():
    built = build_snapshot(graph([node("a", source_refs=())], [edge("r1", "a", "a", "RELATED_TO")]))
    assert built.snapshot.data["nodes"][0]["source_refs"] == []


def test_empty_publish_set_blocks():
    assert reasons(graph([node("x", "low_confidence")])) == [{"kind": "empty_graph"}]
    assert reasons(graph([])) == [{"kind": "empty_graph"}]


def test_invalid_lineage_blocks():
    assert reasons(graph([node("a", merged_from=("a",))])) == [{"kind": "invalid_lineage", "kp_id": "a"}]
    assert reasons(graph([node("a", merged_from=("b",)), node("b")])) == [{"kind": "invalid_lineage", "kp_id": "a"}]
    assert reasons(graph([node("a", merged_from=("old",)), node("b", merged_from=("old",))])) == [
        {"kind": "invalid_lineage", "kp_id": "a"}, {"kind": "invalid_lineage", "kp_id": "b"}]
    # An excluded node's lineage leaves the version with it (dormant sources).
    built = build_snapshot(graph([node("a", merged_from=("old",)), node("x", "low_confidence", merged_from=("old",))]))
    assert built.snapshot.data["nodes"][0]["merged_from"] == ["old"]


def test_all_reasons_are_reported_together_in_a_stable_order():
    draft = graph([node("a", source_refs=("ch-missing",), merged_from=("a",)), node("b")],
                  [edge("r0", "b", "ghost"), edge("r1", "a", "b"), edge("r2", "b", "a")])
    kinds = [r["kind"] for r in reasons(draft)]
    assert kinds == ["cycle", "dangling_endpoint", "invalid_source_ref", "invalid_lineage"]


def test_block_reasons_match_the_contract():
    spec = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
    schemas = json.loads(json.dumps(spec["components"]["schemas"]).replace("#/components/schemas/", "#/$defs/"))
    validator = jsonschema.Draft202012Validator({"$defs": schemas, "$ref": "#/$defs/PublishBlockedDetails"})
    draft = graph([node("a", source_refs=("nope",), merged_from=("a",)), node("b")],
                  [edge("r0", "b", "ghost"), edge("r1", "a", "b"), edge("r2", "b", "a")])
    with pytest.raises(SnapshotBlocked) as caught:
        build_snapshot(draft)
    validator.validate(caught.value.details())
    for reason in reasons(graph([])):
        validator.validate({"reasons": [reason]})


# --- canonical form and digest (PUB-10, PUB-11) ---------------------------------------------


def _rich_draft():
    return graph(
        [node("b", aliases=("LIFO 表", "栈结构", "LIFO 表"), difficulty=0.4, importance=0.8, chapter_id="ch1",
              source_refs=("ch-b", "ch-a", "ch-a"), merged_from=("old-2", "old-1")),
         node("a", type="theorem", definition="引号\"与换行\n", source_refs=("ch-a",)),
         node("x", "low_confidence")],
        [edge("r2", "a", "b", "RELATED_TO", status="approved", source_refs=("ch-b", "ch-a")),
         edge("r1", "a", "b")],
        chapters=[DraftChapter("ch1", "第一章 栈", 1)],
        revisions=[REV, Revision("rev-0", "mat-0", "sha256:" + "b" * 64, "pdf/1+chunk/1@1500-200")],
        chunks={"ch-a": "rev-1", "ch-b": "rev-0"},
    )


def test_canonical_bytes_follow_the_spec_rules():
    snapshot = build_snapshot(_rich_draft()).snapshot
    text = snapshot.canonical.decode("utf-8")
    assert text.startswith('{"chapters":[{"chapter_id":"ch1","order":1,"parent_id":null,"title":"第一章 栈"}],'
                           '"course_id":"course-1","edges":[')
    assert '": ' not in text and ', "' not in text and "\n" not in text
    assert "\\u" not in text
    b = snapshot.data["nodes"][1]
    assert list(b) == sorted(b)
    assert b["aliases"] == ["LIFO 表", "栈结构"] and b["source_refs"] == ["ch-a", "ch-b"]
    assert b["merged_from"] == ["old-1", "old-2"] and b["difficulty"] == 0.4
    a = snapshot.data["nodes"][0]
    assert a["difficulty"] is None and a["chapter_id"] is None and a["aliases"] == []
    assert [r["revision_id"] for r in snapshot.data["revisions"]] == ["rev-0", "rev-1"]
    assert [e["rel_id"] for e in snapshot.data["edges"]] == ["r1", "r2"]
    for field in ("status", "confidence", "locked", "source", "revision", "level"):
        assert f'"{field}"' not in text
    assert snapshot.digest == digest_of(snapshot.canonical)
    assert snapshot.digest.startswith("sha256:") and len(snapshot.digest) == 71


def test_pub10_order_does_not_change_the_digest():
    base = _rich_draft()
    rng = random.Random(7)
    for _ in range(5):
        nodes, edges = list(base.nodes), list(base.edges)
        rng.shuffle(nodes)
        rng.shuffle(edges)
        nodes = [dataclasses.replace(n, aliases=tuple(reversed(n.aliases)),
                                     source_refs=tuple(reversed(n.source_refs))) for n in nodes]
        shuffled = dataclasses.replace(base, nodes=nodes, edges=edges, revisions=list(reversed(base.revisions)))
        assert build_snapshot(shuffled).snapshot.digest == build_snapshot(base).snapshot.digest


@pytest.mark.parametrize("change", [
    lambda d: dataclasses.replace(d, nodes=[dataclasses.replace(d.nodes[0], name="新名称"), *d.nodes[1:]]),
    lambda d: dataclasses.replace(d, nodes=[dataclasses.replace(d.nodes[0], aliases=("另一个",)), *d.nodes[1:]]),
    lambda d: dataclasses.replace(d, nodes=[dataclasses.replace(d.nodes[0], difficulty=0.5), *d.nodes[1:]]),
    lambda d: dataclasses.replace(d, nodes=[dataclasses.replace(d.nodes[0], chapter_id=None), *d.nodes[1:]]),
    lambda d: dataclasses.replace(d, edges=[dataclasses.replace(d.edges[0], source_refs=("ch-a",)), *d.edges[1:]]),
    lambda d: dataclasses.replace(d, chapters=[DraftChapter("ch1", "第一章 栈与队列", 1)]),
    lambda d: dataclasses.replace(d, nodes=[dataclasses.replace(d.nodes[0], merged_from=("old-1",)), *d.nodes[1:]]),
])
def test_pub10_any_visible_field_changes_the_digest(change):
    base = _rich_draft()
    assert build_snapshot(change(base)).snapshot.digest != build_snapshot(base).snapshot.digest


def test_pub10_status_and_confidence_only_changes_keep_the_digest():
    base = _rich_draft()
    approved = dataclasses.replace(base, nodes=[dataclasses.replace(n, status="approved") if n.status == "draft"
                                                else n for n in base.nodes],
                                   edges=[dataclasses.replace(e, status="draft") for e in base.edges])
    assert build_snapshot(approved).snapshot.digest == build_snapshot(base).snapshot.digest


def test_pub11_a_new_revision_alone_changes_the_digest():
    base = _rich_draft()
    more = dataclasses.replace(base, revisions=[*base.revisions, Revision("rev-2", "mat-2", "sha256:" + "c" * 64, "v")])
    assert build_snapshot(more).snapshot.digest != build_snapshot(base).snapshot.digest


def test_digest_of_is_sha256_of_the_canonical_bytes():
    assert canonical_bytes({"b": [1, None], "a": "栈"}) == '{"a":"栈","b":[1,null]}'.encode()
    assert digest_of(b"{}") == "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"


# --- round trip ------------------------------------------------------------------------------


def test_round_trip_keeps_every_attribute():
    built = build_snapshot(_rich_draft()).snapshot
    loaded = load_snapshot(built.canonical)
    assert loaded == built
    assert load_snapshot(built.canonical.decode("utf-8")).digest == built.digest
    b = next(n for n in loaded.data["nodes"] if n["kp_id"] == "b")
    assert b == {"kp_id": "b", "name": "b 名称", "aliases": ["LIFO 表", "栈结构"], "type": "concept",
                 "definition": "b 的定义", "difficulty": 0.4, "importance": 0.8, "chapter_id": "ch1",
                 "source_refs": ["ch-a", "ch-b"], "merged_from": ["old-1", "old-2"]}


@pytest.mark.parametrize("tamper", [
    lambda d: d.pop("revisions"),
    lambda d: d.update(extra=1),
    lambda d: d["nodes"][0].pop("merged_from"),
    lambda d: d["nodes"][0].update(status="draft"),
    lambda d: d["edges"][0].update(type="IS_A"),
    lambda d: d.update(snapshot_format=2),
    lambda d: d["nodes"].reverse(),
    lambda d: d["nodes"][1]["aliases"].reverse(),
    lambda d: d["nodes"][0].update(difficulty=1.5),
    lambda d: d["chapters"][0].update(order=-1),
    lambda d: d.update(course_id=""),
])
def test_load_rejects_malformed_or_non_canonical_snapshots(tamper):
    data = copy.deepcopy(dict(build_snapshot(_rich_draft()).snapshot.data))
    tamper(data)
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with pytest.raises(SnapshotFormatError):
        load_snapshot(raw)


def test_load_rejects_non_canonical_spacing_and_bad_json():
    canonical = build_snapshot(_rich_draft()).snapshot.canonical
    with pytest.raises(SnapshotFormatError):
        load_snapshot(json.dumps(json.loads(canonical), ensure_ascii=False, sort_keys=True))
    with pytest.raises(SnapshotFormatError):
        load_snapshot(json.dumps(json.loads(canonical), sort_keys=True, separators=(",", ":")))  # \\u escapes
    for bad in (b"\xff", b"{", b'{"a":NaN}'):
        with pytest.raises(SnapshotFormatError):
            load_snapshot(bad)


# --- malformed input -------------------------------------------------------------------------


@pytest.mark.parametrize("draft", [
    graph([node("a"), node("a")]),
    graph([node("a")], [edge("r1", "a", "a", "RELATED_TO"), edge("r1", "a", "a", "RELATED_TO")]),
    graph([node("a", status="published")]),
    graph([node("a", type="lemma")]),
    graph([node("a")], [edge("r1", "a", "a", "IS_A")]),
    graph([node("a", importance=float("nan"))]),
    graph([node("a", difficulty=True)]),
    graph([node("a", name=" ")]),
    graph([node("a", aliases="栈")]),
    graph([node("a")], revisions=[REV, REV]),
])
def test_malformed_draft_is_a_format_error_not_a_publish_reason(draft):
    with pytest.raises(SnapshotFormatError):
        build_snapshot(draft)
