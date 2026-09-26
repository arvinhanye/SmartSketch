"""E11：关系两阶段抽取（小节实体 ID 表 + 来源块 → 四类关系候选）。

验收（docs/atomic-task-plan.md E11）：悬空端点/跨课/自环/重复边拦截；仅提及不判前置；方向反例。
只用 E02 fake 客户端，不需要密钥，不发网络。
"""

from __future__ import annotations

import json

import pytest

from app.services.ai.client import ModelServerError
from app.services.ai.entities import REPAIR_PURPOSE, FailureReason
from app.services.ai.fake import BAD_JSON_TEXT, FakeModelClient
from app.services.ai.prompts import PromptLibrary
from app.services.ai.relations import (
    PREREQUISITE_CUES,
    RELATION_PROMPT_PURPOSE,
    RELATION_PROMPT_VERSION,
    RELATION_TYPES,
    RelationCandidate,
    RelationDropReason,
    RelationExtraction,
    RelationExtractor,
    SectionEntity,
    SourceChunk,
)
from app.services.chunk_identity import assign_chunk_identities, revision_parser_version
from app.services.chunking import chunk_blocks, chunking_version
from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator

MODEL = "extract-model-2026-01"
MAX_OUT = 4000
COURSE = "course_ds"

P_REC = "学习快速排序之前需要先掌握递归。递归是函数调用自身的方法。"
P_QUEUE = "队列是一种先进先出的线性表。银行排队是队列的例子。本章同时介绍栈和队列。"

REC, QS, QUEUE, BANK, STACK = "kp_rec", "kp_qs", "kp_queue", "kp_bank", "kp_stack"


def _chunk(text: str, doc: str = "doc_1", course_id: str = COURSE, page: int = 3) -> SourceChunk:
    blocks = [ParsedBlock(0, text, SourceLocator(page=page, section_titles=("第3章", "3.1 小节")))]
    (semantic,) = chunk_blocks(blocks)
    revision = RevisionKey(doc, "sha256:" + "b" * 64, revision_parser_version("pdf/1", chunking_version()))
    (identity,) = assign_chunk_identities(course_id, revision, [semantic])
    return SourceChunk(identity, semantic.text)


def _entities(course_id: str = COURSE) -> list[SectionEntity]:
    return [
        SectionEntity(REC, course_id, "递归", "method"),
        SectionEntity(QS, course_id, "快速排序", "method"),
        SectionEntity(QUEUE, course_id, "队列", "concept"),
        SectionEntity(BANK, course_id, "银行排队", "example"),
        SectionEntity(STACK, course_id, "栈", "concept"),
    ]


def _chunks() -> list[SourceChunk]:
    return [_chunk(P_REC, "doc_1", page=3), _chunk(P_QUEUE, "doc_2", page=7)]


def _rel(from_id: str, to_id: str, type_: str, evidence: str, **extra: object) -> dict[str, object]:
    item: dict[str, object] = {"from_id": from_id, "to_id": to_id, "type": type_, "evidence": evidence}
    item.update(extra)
    return item


def _reply(*relations: object) -> str:
    return json.dumps({"relations": list(relations)}, ensure_ascii=False)


PREREQ = _rel(REC, QS, "PREREQUISITE", "学习快速排序之前需要先掌握递归", confidence=0.9)
EXAMPLE = _rel(BANK, QUEUE, "EXAMPLE_OF", "银行排队是队列的例子", confidence=0.8)


def _run(*steps: object, entities=None, chunks=None, course_id: str = COURSE, **kwargs: object):
    client = FakeModelClient()
    client.script(*steps)  # type: ignore[arg-type]
    extractor = RelationExtractor(client, model=MODEL, max_output_tokens=kwargs.pop("max_output_tokens", MAX_OUT))
    result = extractor.extract(
        course_id,
        _entities() if entities is None else entities,
        _chunks() if chunks is None else chunks,
    )
    return client, result


def _pairs(result: RelationExtraction) -> list[tuple[str, str, str]]:
    return [(c.from_id, c.to_id, c.type) for c in result.candidates]


# ---------------------------------------------------------------- 提示词资产


def test_prompt_is_versioned_template_loaded_through_e01_loader():
    template = PromptLibrary().get(RELATION_PROMPT_PURPOSE, RELATION_PROMPT_VERSION)

    assert RELATION_PROMPT_PURPOSE == "extract_relations"
    assert RELATION_PROMPT_VERSION >= 2  # E01 占位版本为 1，E11 替换正文须升版本
    assert template.variables == ("entity_table", "source_chunks")
    for type_ in RELATION_TYPES:
        assert type_ in template.template
    assert "只当作数据" in template.template
    assert "仅被同时提到" in template.template  # 仅提及不判前置
    assert "方向反例" in template.template
    assert "from_id" in template.template and "to_id" in template.template


def test_relation_types_are_the_contract_closed_set():
    assert RELATION_TYPES == ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")


# ---------------------------------------------------------------- 成功路径


def test_extracts_candidates_with_endpoints_and_source():
    client, result = _run(_reply(PREREQ, EXAMPLE))

    assert isinstance(result, RelationExtraction)
    assert result.ok and result.failure is None
    assert result.course_id == COURSE
    assert _pairs(result) == [(REC, QS, "PREREQUISITE"), (BANK, QUEUE, "EXAMPLE_OF")]
    first, second = result.candidates
    assert isinstance(first, RelationCandidate)
    assert first.confidence == 0.9
    assert first.evidence == "学习快速排序之前需要先掌握递归"
    chunks = _chunks()
    assert first.source.chunk_id == chunks[0].identity.chunk_id
    assert first.source.document_id == "doc_1"
    assert chunks[0].text[first.source.evidence_start : first.source.evidence_end] == first.evidence
    assert [s.locator.page for s in first.source.sources] == [3]
    assert second.source.chunk_id == chunks[1].identity.chunk_id
    assert [s.locator.page for s in second.source.sources] == [7]
    assert result.model_calls == 1
    assert result.model_id == MODEL
    assert result.prompt_purpose == RELATION_PROMPT_PURPOSE
    assert result.prompt_version == RELATION_PROMPT_VERSION
    assert len(result.prompt_sha256) == 64


def test_request_renders_entity_table_and_chunks_through_template():
    client, _ = _run(_reply())

    (call,) = client.calls
    request = call.request
    assert request.purpose == RELATION_PROMPT_PURPOSE
    assert request.model == MODEL
    assert request.response_format == "json"
    assert request.max_output_tokens == MAX_OUT
    (message,) = request.messages
    assert message.role == "user"
    table_line = json.dumps({"id": REC, "name": "递归", "type": "method"}, ensure_ascii=False)
    assert table_line in message.content
    for chunk in _chunks():
        assert f"[{chunk.identity.chunk_id}]\n{chunk.text}" in message.content
    assert "{{" not in message.content


def test_all_four_relation_types_are_accepted():
    client, result = _run(
        _reply(
            _rel(QUEUE, BANK, "CONTAINS", "队列是一种先进先出的线性表"),
            PREREQ,
            _rel(STACK, QUEUE, "RELATED_TO", "本章同时介绍栈和队列"),
            EXAMPLE,
        )
    )

    assert {c.type for c in result.candidates} == set(RELATION_TYPES)
    assert result.dropped == {}


def test_empty_relations_array_is_ok():
    _, result = _run(_reply())

    assert result.ok and result.candidates == () and result.dropped == {}


def test_missing_confidence_is_kept_as_none():
    _, result = _run(_reply(_rel(REC, QS, "PREREQUISITE", "学习快速排序之前需要先掌握递归")))

    assert result.candidates[0].confidence is None


def test_fewer_than_two_entities_or_no_text_makes_no_call():
    client, result = _run(entities=_entities()[:1])
    assert result.ok and result.candidates == () and result.model_calls == 0
    assert client.calls == ()

    client, result = _run(chunks=[])
    assert result.ok and result.model_calls == 0 and client.calls == ()


# ---------------------------------------------------------------- 端点拦截：悬空、跨课、自环、重复


def test_dangling_endpoint_is_dropped():
    _, result = _run(
        _reply(
            _rel(REC, "kp_missing", "PREREQUISITE", "学习快速排序之前需要先掌握递归"),
            _rel("递归", QS, "PREREQUISITE", "学习快速排序之前需要先掌握递归"),  # 用名称代替 ID
            PREREQ,
        )
    )

    assert _pairs(result) == [(REC, QS, "PREREQUISITE")]
    assert result.dropped == {RelationDropReason.DANGLING_ENDPOINT: 2}


def test_endpoint_from_another_course_is_dangling():
    # 模型给出别的课程的知识点 ID：不在本小节实体表内，按悬空拦截。
    _, result = _run(_reply(_rel(REC, "other_course_kp_qs", "PREREQUISITE", "学习快速排序之前需要先掌握递归")))

    assert result.candidates == ()
    assert result.dropped == {RelationDropReason.DANGLING_ENDPOINT: 1}


def test_entity_from_another_course_is_rejected_before_calling_model():
    client = FakeModelClient()
    entities = _entities() + [SectionEntity("kp_x", "course_other", "堆", "concept")]

    with pytest.raises(ValueError, match="another course"):
        RelationExtractor(client, model=MODEL, max_output_tokens=MAX_OUT).extract(COURSE, entities, _chunks())
    assert client.calls == ()


def test_chunk_from_another_course_is_rejected_before_calling_model():
    client = FakeModelClient()
    chunks = _chunks() + [_chunk("堆是一种完全二叉树。", "doc_9", course_id="course_other")]

    with pytest.raises(ValueError, match="another course"):
        RelationExtractor(client, model=MODEL, max_output_tokens=MAX_OUT).extract(COURSE, _entities(), chunks)
    assert client.calls == ()


def test_self_loop_is_dropped():
    _, result = _run(_reply(_rel(REC, REC, "PREREQUISITE", "学习快速排序之前需要先掌握递归"), PREREQ))

    assert _pairs(result) == [(REC, QS, "PREREQUISITE")]
    assert result.dropped == {RelationDropReason.SELF_LOOP: 1}


def test_duplicate_edge_keeps_first_valid_one():
    _, result = _run(
        _reply(
            _rel(REC, QS, "PREREQUISITE", "不在资料里的证据"),  # 首条不合格，不占去重位
            PREREQ,
            _rel(REC, QS, "PREREQUISITE", "学习快速排序之前需要先掌握递归", confidence=0.2),
        )
    )

    assert _pairs(result) == [(REC, QS, "PREREQUISITE")]
    assert result.candidates[0].confidence == 0.9
    assert result.dropped == {
        RelationDropReason.EVIDENCE_NOT_IN_SOURCES: 1,
        RelationDropReason.DUPLICATE: 1,
    }


def test_related_to_is_undirected_for_duplicates():
    _, result = _run(
        _reply(
            _rel(STACK, QUEUE, "RELATED_TO", "本章同时介绍栈和队列"),
            _rel(QUEUE, STACK, "RELATED_TO", "本章同时介绍栈和队列"),
        )
    )

    assert _pairs(result) == [(STACK, QUEUE, "RELATED_TO")]
    assert result.dropped == {RelationDropReason.DUPLICATE: 1}


def test_same_pair_with_different_types_or_reverse_prerequisite_are_not_duplicates():
    # 反向前置 A→B 与 B→A 不在此去重：二元环交 F13 按 ADR-009 降级送审。
    _, result = _run(
        _reply(
            PREREQ,
            _rel(QS, REC, "PREREQUISITE", "学习快速排序之前需要先掌握递归"),
            _rel(REC, QS, "RELATED_TO", "学习快速排序之前需要先掌握递归"),
        )
    )

    assert _pairs(result) == [
        (REC, QS, "PREREQUISITE"),
        (QS, REC, "PREREQUISITE"),
        (REC, QS, "RELATED_TO"),
    ]


def test_duplicate_entity_ids_in_input_are_rejected():
    entities = _entities() + [SectionEntity(REC, COURSE, "递归调用", "method")]

    with pytest.raises(ValueError, match="duplicate entity_id"):
        RelationExtractor(FakeModelClient(), model=MODEL, max_output_tokens=MAX_OUT).extract(
            COURSE, entities, _chunks()
        )


# ---------------------------------------------------------------- 仅提及不判前置


def test_co_mention_is_not_prerequisite():
    # 「本章同时介绍栈和队列」只是并列提及，没有先修表述。
    _, result = _run(_reply(_rel(STACK, QUEUE, "PREREQUISITE", "本章同时介绍栈和队列", confidence=0.7)))

    assert result.candidates == ()
    assert result.dropped == {RelationDropReason.PREREQUISITE_WITHOUT_CUE: 1}


def test_co_mention_can_still_be_related_to():
    _, result = _run(_reply(_rel(STACK, QUEUE, "RELATED_TO", "本章同时介绍栈和队列")))

    assert _pairs(result) == [(STACK, QUEUE, "RELATED_TO")]


@pytest.mark.parametrize(
    "text",
    [
        "掌握递归后才能学习快速排序。",
        "快速排序建立在递归的基础上。",
        "Quicksort REQUIRES recursion.",
    ],
)
def test_prerequisite_cues_are_matched_after_normalization(text):
    chunk = _chunk(text, "doc_3")
    _, result = _run(_reply(_rel(REC, QS, "PREREQUISITE", text.rstrip("。."))), chunks=[chunk])

    assert _pairs(result) == [(REC, QS, "PREREQUISITE")]


def test_prerequisite_cue_list_is_nonempty_and_has_no_blank_entries():
    assert PREREQUISITE_CUES
    assert all(cue.strip() == cue and cue for cue in PREREQUISITE_CUES)


# ---------------------------------------------------------------- 方向反例


def test_prerequisite_direction_is_kept_as_given_not_swapped():
    _, result = _run(_reply(PREREQ))

    (candidate,) = result.candidates
    assert (candidate.from_id, candidate.to_id) == (REC, QS)


def test_reversed_example_of_is_dropped_not_flipped():
    # 例子类实体（银行排队）必须在 from 端；反过来即方向颠倒。
    _, result = _run(_reply(_rel(QUEUE, BANK, "EXAMPLE_OF", "银行排队是队列的例子")))

    assert result.candidates == ()
    assert result.dropped == {RelationDropReason.REVERSED_DIRECTION: 1}


def test_example_of_between_two_non_example_entities_is_kept():
    _, result = _run(_reply(_rel(QS, REC, "EXAMPLE_OF", "递归是函数调用自身的方法")))

    assert _pairs(result) == [(QS, REC, "EXAMPLE_OF")]


# ---------------------------------------------------------------- 逐条校验


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        ("not an object", RelationDropReason.NOT_OBJECT),
        (_rel(REC, QS, "prerequisite", "学习快速排序之前需要先掌握递归"), RelationDropReason.INVALID_TYPE),
        (_rel(REC, QS, "RELATED", "学习快速排序之前需要先掌握递归"), RelationDropReason.INVALID_TYPE),
        (_rel(REC, QS, "APPLIES_TO", "学习快速排序之前需要先掌握递归"), RelationDropReason.INVALID_TYPE),
        ({"from_id": 1, "to_id": QS, "type": "PREREQUISITE", "evidence": "x"}, RelationDropReason.INVALID_ENDPOINT),
        (_rel(REC, QS, "PREREQUISITE", "   "), RelationDropReason.INVALID_EVIDENCE),
        (_rel(REC, QS, "PREREQUISITE", "递" * 501), RelationDropReason.INVALID_EVIDENCE),
        (_rel(REC, QS, "PREREQUISITE", "快速排序需要先掌握递归"), RelationDropReason.EVIDENCE_NOT_IN_SOURCES),
        (
            _rel(REC, QS, "PREREQUISITE", "学习快速排序之前需要先掌握递归", confidence=1.5),
            RelationDropReason.INVALID_CONFIDENCE,
        ),
        (
            _rel(REC, QS, "PREREQUISITE", "学习快速排序之前需要先掌握递归", confidence=True),
            RelationDropReason.INVALID_CONFIDENCE,
        ),
    ],
)
def test_invalid_items_are_dropped_and_counted(item, reason):
    _, result = _run(_reply(item, EXAMPLE))

    assert result.ok
    assert _pairs(result) == [(BANK, QUEUE, "EXAMPLE_OF")]
    assert result.dropped == {reason: 1}
    assert result.model_calls == 1  # 条目级问题不触发修复


def test_evidence_spanning_two_chunks_is_rejected():
    _, result = _run(_reply(_rel(REC, QUEUE, "RELATED_TO", "递归是函数调用自身的方法。队列")))

    assert result.dropped == {RelationDropReason.EVIDENCE_NOT_IN_SOURCES: 1}


# ---------------------------------------------------------------- 整体输出不合规：修复一次


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (BAD_JSON_TEXT, FailureReason.INVALID_JSON),
        ('{"entities": []}', FailureReason.INVALID_STRUCTURE),
        ('[{"from_id": "kp_rec"}]', FailureReason.INVALID_STRUCTURE),
    ],
)
def test_bad_output_is_repaired_once_then_fails(bad, reason):
    client, result = _run(bad, bad)

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason is reason
    assert result.failure.attempts == 2
    assert result.candidates == ()
    assert result.model_calls == 2
    first, second = client.calls
    assert second.request.purpose == REPAIR_PURPOSE
    assert second.request.model == first.request.model
    assert second.request.messages == first.request.messages


def test_truncated_output_counts_as_non_compliant():
    # fake 按声明的输出上限截断并置 finish_reason = length；即使截断后碰巧可解析也不采信。
    client, result = _run(_reply(PREREQ), _reply(PREREQ), max_output_tokens=10)

    assert result.failure is not None and result.failure.reason is FailureReason.TRUNCATED
    assert result.model_calls == 2 and result.candidates == ()


def test_repair_success_is_used():
    client, result = _run(BAD_JSON_TEXT, _reply(PREREQ))

    assert result.ok
    assert _pairs(result) == [(REC, QS, "PREREQUISITE")]
    assert result.model_calls == 2


def test_model_call_errors_propagate():
    client = FakeModelClient()
    client.script(ModelServerError("boom"))

    with pytest.raises(ModelServerError):
        RelationExtractor(client, model=MODEL, max_output_tokens=MAX_OUT).extract(COURSE, _entities(), _chunks())


# ---------------------------------------------------------------- 输入与泄露


def test_text_must_match_identity():
    chunk = _chunks()[0]
    forged = SourceChunk(chunk.identity, chunk.text + "篡改")

    with pytest.raises(ValueError, match="text_sha256"):
        RelationExtractor(FakeModelClient(), model=MODEL, max_output_tokens=MAX_OUT).extract(
            COURSE, _entities(), [forged]
        )


def test_unknown_entity_type_is_rejected():
    entities = _entities() + [SectionEntity("kp_y", COURSE, "某物", "Concept")]

    with pytest.raises(ValueError, match="unknown type"):
        RelationExtractor(FakeModelClient(), model=MODEL, max_output_tokens=MAX_OUT).extract(
            COURSE, entities, _chunks()
        )


def test_constructor_validates_arguments():
    with pytest.raises(TypeError):
        RelationExtractor(object(), model=MODEL, max_output_tokens=MAX_OUT)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RelationExtractor(FakeModelClient(), model=" ", max_output_tokens=MAX_OUT)
    with pytest.raises(ValueError):
        RelationExtractor(FakeModelClient(), model=MODEL, max_output_tokens=0)


def test_repr_does_not_leak_text_names_or_evidence():
    _, result = _run(_reply(PREREQ))

    rendered = repr(result) + repr(_entities()) + repr(_chunks())
    for secret in ("学习快速排序之前需要先掌握递归", "递归", "银行排队", P_QUEUE):
        assert secret not in rendered
