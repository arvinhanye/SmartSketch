from __future__ import annotations

import pytest
import json
from pathlib import Path

from app.services.qa.citations import CitationStream, Evidence, not_covered
from app.services.versions.resolver import PublishedVersion


VERSION = PublishedVersion("course-a", "version-a", 3, frozenset({"revision-a"}))


def evidence(index: int, **changes: object) -> Evidence:
    values = dict(index=index, chunk_id=f"chunk-{index}", document_id="doc-a", course_id="course-a",
                  revision_id="revision-a", text="原文内容", page=2, section_path=None)
    values.update(changes)
    return Evidence(**values)


def stream(*items: Evidence) -> CitationStream:
    return CitationStream(VERSION, "request-a", items)


def finish(parts: list[str], *items: Evidence, truncated: bool = False):
    parser = stream(*items)
    deltas = [parser.feed(part) for part in parts]
    deltas.append(parser.finish())
    return parser, "".join(deltas), parser.finalize(latency_ms=7, truncated=truncated)


def test_valid_citations_normalize_and_resolve_from_server_source():
    parser, answer, final = finish(["栈是线性表[1,", "3]。操作见【2】。"], evidence(1), evidence(2), evidence(3))
    assert answer == "栈是线性表[1][3]。操作见[2]。"
    assert final["status"] == "answered"
    assert final["answer"] == answer
    assert [c["index"] for c in final["citations"]] == [1, 3, 2]
    assert final["citations"][0] == {"index": 1, "chunk_id": "chunk-1", "document_id": "doc-a", "page": 2, "text": "原文内容"}
    assert final["graph_version"] == 3 and final["request_id"] == "request-a"
    assert parser.unknown_count == 0


@pytest.mark.parametrize("raw, expected, unknown", [
    ("结论[1，9]。", "结论[1]。", 1),
    ("结论[2、2]。", "结论。", 1),
    ("结论[0][01][1-3][１][1a][a][注]。", "结论[a][注]。", 5),
    ("结论［1］。", "结论[1]。", 0),
    ("结论[1，1]。", "结论[1]。", 0),
])
def test_marker_closed_set(raw, expected, unknown):
    parser, answer, final = finish([raw], evidence(1))
    assert answer == expected
    assert parser.unknown_count == unknown
    assert final["status"] == ("answered" if "[1]" in answer else "not_covered")
    if final["status"] == "not_covered":
        assert final["citations"] == []


def test_scope_recheck_excludes_foreign_old_and_unlocatable(caplog):
    parser, answer, final = finish(["结论[1][2][3][4]。"], evidence(1), evidence(2, course_id="other"),
                                   evidence(3, revision_id="old"), evidence(4, page=None, section_path=" "))
    assert answer == "结论[1]。"
    assert final["status"] == "answered"
    assert [c["index"] for c in final["citations"]] == [1]
    assert parser.integrity_rejections == 3
    assert parser.unknown_count == 3
    assert len([r for r in caplog.records if "J06 rejected" in r.message]) == 3


def test_section_locator_does_not_emit_invalid_page():
    _, _, final = finish(["结论[1]。"], evidence(1, page=0, section_path="第3章"))
    assert final["status"] == "answered"
    assert final["citations"][0]["section_path"] == "第3章"
    assert "page" not in final["citations"][0]


def test_no_valid_marker_withdraws_temporary_answer_and_classifies():
    parser, delta, final = finish(["错误结论[9]。"], evidence(1))
    assert delta == "错误结论。"
    assert final["status"] == "not_covered" and final["reason"] == "all_citations_invalidated"
    assert final["citations"] == [] and "错误结论" not in final["answer"]
    assert parser.invalidation_subtype == "unknown_only"


def test_sentinel_across_chunks_stops_without_delta():
    parser = stream(evidence(1))
    assert parser.feed(" \n<<INSUFF") == ""
    assert parser.feed("ICIENT_EVIDENCE>>hidden") == ""
    assert parser.stop_supplier
    assert parser.finish() == ""
    final = parser.finalize(latency_ms=1)
    assert final["reason"] == "insufficient_evidence" and "hidden" not in final["answer"]


def test_middle_sentinel_removed_and_prefix_divergence_passes():
    _, answer, final = finish(["<<INSIGHT>>结论[1]。中间<<INSUFFICIENT_EVIDENCE>>仍是结论[1]。"], evidence(1))
    assert answer == "<<INSIGHT>>结论[1]。中间仍是结论[1]。"
    assert final["status"] == "answered"


def test_code_and_unclosed_marker_are_plain_text():
    _, answer, final = finish(["`a[1]`\n```py\nx[2]\n```\n结论[", "1]。"], evidence(1), evidence(2))
    assert answer == "`a[1]`\n```py\nx[2]\n```\n结论[1]。"
    assert [c["index"] for c in final["citations"]] == [1]
    _, answer, final = finish(["结论[1]。尾部[12"], evidence(1))
    assert answer.endswith("[12")
    assert final["status"] == "not_covered"


@pytest.mark.parametrize("case", json.loads((Path(__file__).parents[1] / "fixtures/qa_code_spans.json").read_text(encoding="utf-8")))
def test_shared_code_span_fixture(case):
    _, answer, final = finish([case["text"]], evidence(1), evidence(2))
    assert answer == case["text"]
    assert [c["index"] for c in final["citations"]] == case["citations"]
    assert final["status"] == case["status"]


def test_marker_split_at_every_character_emits_only_validated_text():
    raw = "结论[1][9]。另见［2］。"
    parser, answer, final = finish(list(raw), evidence(1), evidence(2))
    assert answer == "结论[1]。另见[2]。"
    assert final["answer"] == answer
    assert parser.unknown_count == 1


@pytest.mark.parametrize("raw, covered, count", [
    ("栈是线性表[1]。太阳由奶酪构成。", False, 1),
    ("栈是线性表[1]。栈只能在一端操作[1]。", True, 0),
    ("栈是线性表。[1]", True, 0),
    ("栈是线性表。[1]太阳由奶酪构成。", False, 1),
    ("## 栈\n栈是线性表[1]。", True, 0),
    ("π 约为 3.14[1]。", True, 0),
    ("栈是线性表[1]。\n```\npush(x)\n```", True, 0),
    ("栈的操作如下：\n- 入栈[1]\n- 出栈", False, 2),
])
def test_each_claim_unit_must_be_cited(raw, covered, count):
    parser, _, final = finish([raw], evidence(1))
    assert (final["status"] == "answered") is covered
    assert parser.uncited_units == count
    if not covered:
        assert parser.invalidation_subtype == "uncited_sentence"


def test_truncation_still_checks_tail_unit():
    parser, _, final = finish(["结论[1]。未完成"], evidence(1), truncated=True)
    assert parser.truncated and parser.invalidation_subtype == "uncited_sentence"
    assert final["status"] == "not_covered"


@pytest.mark.parametrize("reason", ["no_retrieval_hit", "below_similarity_threshold", "insufficient_evidence", "all_citations_invalidated"])
def test_not_covered_templates_never_contain_model_output(reason):
    final = not_covered(reason, graph_version=3, request_id="request-a", latency_ms=0)
    assert final["reason"] == reason and final["citations"] == []
    assert final["answer"] and "secret-model-token" not in final["answer"]
