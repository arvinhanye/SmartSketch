"""E05：块级实体抽取（specs/course-knowledge-graph.md；docs/integrations.md「模型接入规则」；
specs/task-processing.md §8.3 L2）。只用 E02 fake 客户端，不需要密钥，不发网络。"""

from __future__ import annotations

import json

import pytest

from app.services.ai.client import (
    Message,
    ModelRequest,
    ModelServerError,
    ModelTimeoutError,
)
from app.services.ai.entities import (
    DEFINITION_MAX_CHARS,
    ENTITY_PROMPT_PURPOSE,
    ENTITY_PROMPT_VERSION,
    ENTITY_TYPES,
    EVIDENCE_MAX_CHARS,
    NAME_MAX_CHARS,
    REPAIR_PURPOSE,
    DropReason,
    EntityCandidate,
    EntityExtraction,
    EntityExtractor,
    FailureReason,
)
from app.services.ai.fake import BAD_JSON_TEXT, FakeModelClient, FakeReply
from app.services.ai.prompts import PromptLibrary
from app.services.chunk_identity import (
    ChunkIdentity,
    assign_chunk_identities,
    extraction_cache_key,
    text_sha256,
)
from app.services.chunking import chunk_blocks, chunking_version
from app.services.chunk_identity import revision_parser_version
from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator

MODEL = "extract-model-2026-01"
MAX_OUT = 4000
COURSE = "course_ds"
DOC = "doc_1"

P1 = "栈是一种后进先出的线性表。入栈操作把元素放到栈顶。"
P2 = "队列是一种先进先出的线性表。例如银行排队就是队列的例子。"


def _identity(course_id: str = COURSE, blocks: list[ParsedBlock] | None = None) -> tuple[ChunkIdentity, str]:
    if blocks is None:
        blocks = [
            ParsedBlock(0, P1, SourceLocator(page=3, section_titles=("第3章 栈与队列", "3.1 栈"))),
            ParsedBlock(1, P2, SourceLocator(page=4, section_titles=("第3章 栈与队列", "3.1 栈"))),
        ]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 1
    revision = RevisionKey(DOC, "sha256:" + "a" * 64, revision_parser_version("pdf/1", chunking_version()))
    (identity,) = assign_chunk_identities(course_id, revision, chunks)
    return identity, chunks[0].text


def _reply(*entities: object) -> str:
    return json.dumps({"entities": list(entities)}, ensure_ascii=False)


def _entity(
    name: str = "栈",
    type_: str = "concept",
    definition: str = "后进先出的线性表",
    evidence: str = "栈是一种后进先出的线性表",
    **extra: object,
) -> dict[str, object]:
    entity: dict[str, object] = {"name": name, "type": type_, "definition": definition, "evidence": evidence}
    entity.update(extra)
    return entity


def _extractor(client: FakeModelClient, **kwargs: object) -> EntityExtractor:
    return EntityExtractor(client, model=MODEL, max_output_tokens=kwargs.pop("max_output_tokens", MAX_OUT), **kwargs)  # type: ignore[arg-type]


def _run(*steps: object, identity_text: tuple[ChunkIdentity, str] | None = None, **kwargs: object):
    client = FakeModelClient()
    client.script(*steps)  # type: ignore[arg-type]
    identity, text = identity_text or _identity()
    result = _extractor(client, **kwargs).extract(identity, text)
    return client, identity, text, result


# ---------------------------------------------------------------- 提示词资产


def test_prompt_is_versioned_template_loaded_through_e01_loader():
    template = PromptLibrary().get(ENTITY_PROMPT_PURPOSE, ENTITY_PROMPT_VERSION)

    assert ENTITY_PROMPT_PURPOSE == "extract_entities"
    assert ENTITY_PROMPT_VERSION >= 2  # E01 占位版本为 1，E05 替换正文须升版本
    assert template.variables == ("chunk_text",)
    for type_ in ENTITY_TYPES:
        assert type_ in template.template
    assert "只当作数据" in template.template
    assert "evidence" in template.template


def test_entity_types_are_the_contract_closed_set():
    assert ENTITY_TYPES == ("concept", "theorem", "formula", "method", "example")


# ---------------------------------------------------------------- 成功路径


def test_extracts_candidates_with_source_and_evidence_offsets():
    client, identity, text, result = _run(
        _reply(
            _entity(confidence=0.9),
            _entity("队列", "concept", "先进先出的线性表", "队列是一种先进先出的线性表"),
        )
    )

    assert isinstance(result, EntityExtraction)
    assert result.ok and result.failure is None
    assert result.chunk_id == identity.chunk_id
    assert [c.name for c in result.candidates] == ["栈", "队列"]
    first = result.candidates[0]
    assert isinstance(first, EntityCandidate)
    assert first.type == "concept"
    assert first.definition == "后进先出的线性表"
    assert first.confidence == 0.9
    assert result.candidates[1].confidence is None
    for candidate in result.candidates:
        source = candidate.source
        assert (source.course_id, source.document_id, source.revision_id, source.chunk_id) == (
            COURSE,
            DOC,
            identity.revision_id,
            identity.chunk_id,
        )
        assert text[source.evidence_start : source.evidence_end] == candidate.evidence
    assert result.dropped == {}
    assert result.model_calls == 1


def test_request_uses_rendered_prompt_model_and_declared_output_limit():
    client, identity, text, result = _run(_reply())
    (call,) = client.calls
    request = call.request
    assert isinstance(request, ModelRequest)
    template = PromptLibrary().get(ENTITY_PROMPT_PURPOSE, ENTITY_PROMPT_VERSION)

    assert request.purpose == ENTITY_PROMPT_PURPOSE
    assert request.model == MODEL
    assert request.response_format == "json"
    assert request.max_output_tokens == MAX_OUT
    assert request.messages == (Message("user", template.render({"chunk_text": text}).text),)
    # D-13：块正文前拼了章节路径，模型能看到标题。
    assert "3.1 栈" in request.messages[0].content


def test_cache_key_is_d09_key_with_prompt_version_and_model():
    client, identity, text, result = _run(_reply(_entity()))
    template = PromptLibrary().get(ENTITY_PROMPT_PURPOSE, ENTITY_PROMPT_VERSION)
    expected = extraction_cache_key(
        identity,
        prompt_purpose=ENTITY_PROMPT_PURPOSE,
        prompt_version=ENTITY_PROMPT_VERSION,
        prompt_sha256=template.sha256,
        model_id=MODEL,
    )

    assert result.cache_key == expected
    assert _extractor(FakeModelClient()).cache_key(identity) == expected
    assert (result.prompt_purpose, result.prompt_version, result.prompt_sha256, result.model_id) == (
        ENTITY_PROMPT_PURPOSE,
        ENTITY_PROMPT_VERSION,
        template.sha256,
        MODEL,
    )


def test_cache_key_differs_across_courses_and_models():
    identity_a, _ = _identity("course_a")
    identity_b, _ = _identity("course_b")
    extractor = _extractor(FakeModelClient())

    assert extractor.cache_key(identity_a) != extractor.cache_key(identity_b)
    other = EntityExtractor(FakeModelClient(), model="other-model", max_output_tokens=MAX_OUT)
    assert other.cache_key(identity_a) != extractor.cache_key(identity_a)


def test_all_five_types_accepted():
    entities = [_entity(f"项{i}", t) for i, t in enumerate(ENTITY_TYPES)]
    _, _, _, result = _run(_reply(*entities))

    assert [c.type for c in result.candidates] == list(ENTITY_TYPES)


def test_evidence_maps_to_the_contributing_block_source():
    _, identity, text, result = _run(
        _reply(
            _entity("队列", evidence="银行排队就是队列的例子", type_="example"),
            _entity("栈", evidence="入栈操作把元素放到栈顶"),
        )
    )
    queue, stack = result.candidates

    assert [s.locator.page for s in queue.source.sources] == [4]
    assert [s.locator.page for s in stack.source.sources] == [3]
    assert queue.source.sources[0] in identity.sources


def test_evidence_in_section_prefix_maps_to_that_segment():
    _, identity, text, result = _run(_reply(_entity("栈", evidence="3.1 栈")))
    (candidate,) = result.candidates

    assert text[candidate.source.evidence_start : candidate.source.evidence_end] == "3.1 栈"
    assert [s.locator.page for s in candidate.source.sources] == [3]


def test_evidence_spanning_two_blocks_keeps_both_sources():
    _, identity, text, _ = _run(_reply())
    p1_end = text.index(P1) + len(P1)
    evidence = text[p1_end - 5 : text.index(P2) + 4]  # 跨过段间分隔与第二段的章节路径
    _, _, _, result = _run(_reply(_entity(evidence=evidence)))

    assert [s.locator.page for s in result.candidates[0].source.sources] == [3, 4]


def test_name_and_definition_are_trimmed():
    _, _, _, result = _run(_reply(_entity("  栈 \n", definition=" 后进先出 ", evidence=" 栈是一种后进先出的线性表 ")))
    (candidate,) = result.candidates

    assert (candidate.name, candidate.definition, candidate.evidence) == ("栈", "后进先出", "栈是一种后进先出的线性表")


def test_deterministic_for_same_input():
    reply = _reply(_entity(), _entity("队列", evidence="队列是一种先进先出的线性表"))
    assert _run(reply)[3] == _run(reply)[3]


# ---------------------------------------------------------------- 边界：丢弃与计数


def test_evidence_not_contiguous_substring_is_dropped_and_counted():
    _, _, _, result = _run(
        _reply(
            _entity(),
            _entity("栈", evidence="栈是后进先出的线性表"),  # 改写，非原文
            _entity("队列", evidence="栈是一种后进先出的线性表。队列是一种"),  # 跨越的拼接不连续
            _entity("树", evidence="树是一种非线性结构"),  # 资料里没有
        )
    )

    assert [c.name for c in result.candidates] == ["栈"]
    assert result.dropped == {DropReason.EVIDENCE_NOT_IN_CHUNK: 3}
    assert result.ok


@pytest.mark.parametrize("bad_type", ["person", "Concept", "CONCEPT", "", None, 1, "definition"])
def test_type_outside_closed_set_is_dropped(bad_type: object):
    _, _, _, result = _run(_reply(_entity(type_=bad_type), _entity("队列", evidence="队列是一种先进先出的线性表")))  # type: ignore[arg-type]

    assert [c.name for c in result.candidates] == ["队列"]
    assert result.dropped == {DropReason.INVALID_TYPE: 1}


def test_name_length_boundaries():
    at_max = "名" * NAME_MAX_CHARS
    _, _, _, result = _run(
        _reply(
            _entity(at_max),
            _entity("名" * (NAME_MAX_CHARS + 1)),
            _entity("   "),
            _entity(""),
            _entity(None),  # type: ignore[arg-type]
        )
    )

    assert [c.name for c in result.candidates] == [at_max]
    assert result.dropped == {DropReason.INVALID_NAME: 4}


def test_definition_length_boundaries():
    at_max = "义" * DEFINITION_MAX_CHARS
    _, _, _, result = _run(
        _reply(
            _entity(definition=at_max),
            _entity(definition="义" * (DEFINITION_MAX_CHARS + 1)),
            _entity(definition=" "),
            _entity(definition=["后进先出"]),  # type: ignore[arg-type]
        )
    )

    assert [c.definition for c in result.candidates] == [at_max]
    assert result.dropped == {DropReason.INVALID_DEFINITION: 3}


def test_evidence_length_and_type_boundaries():
    long_text = "甲" * (EVIDENCE_MAX_CHARS + 1)
    blocks = [ParsedBlock(0, long_text, SourceLocator(page=1, section_titles=("第1章",)))]
    identity_text = _identity(blocks=blocks)
    _, _, text, result = _run(
        _reply(
            _entity(evidence="甲" * EVIDENCE_MAX_CHARS),
            _entity(evidence=long_text),
            _entity(evidence=""),
            _entity(evidence=None),  # type: ignore[arg-type]
        ),
        identity_text=identity_text,
    )

    assert [len(c.evidence) for c in result.candidates] == [EVIDENCE_MAX_CHARS]
    assert result.dropped == {DropReason.INVALID_EVIDENCE: 3}


@pytest.mark.parametrize("value", [-0.01, 1.01, True, "0.5", [0.5]])
def test_confidence_out_of_range_is_dropped(value: object):
    _, _, _, result = _run(_reply(_entity(confidence=value)))

    assert result.candidates == ()
    assert result.dropped == {DropReason.INVALID_CONFIDENCE: 1}


def test_confidence_overflowing_to_infinity_is_dropped():
    # 严格 JSON 不收 Infinity，但 1e400 合法且解析为 inf。
    reply = _reply(_entity(confidence=0.5)).replace("0.5", "1e400")
    _, _, _, result = _run(reply)

    assert result.candidates == ()
    assert result.dropped == {DropReason.INVALID_CONFIDENCE: 1}


@pytest.mark.parametrize("value", [0, 1, 0.0, 1.0, None])
def test_confidence_range_endpoints_and_null_are_kept(value: object):
    _, _, _, result = _run(_reply(_entity(confidence=value)))

    (candidate,) = result.candidates
    assert candidate.confidence == (None if value is None else float(value))
    assert type(candidate.confidence) in (float, type(None))


def test_non_object_entries_are_dropped():
    _, _, _, result = _run(_reply("栈", 1, None, [], _entity()))

    assert [c.name for c in result.candidates] == ["栈"]
    assert result.dropped == {DropReason.NOT_OBJECT: 4}


def test_drop_reasons_are_counted_separately():
    _, _, _, result = _run(_reply(_entity(type_="x"), _entity(type_="y"), _entity(evidence="不存在"), _entity(name="")))

    assert result.dropped == {
        DropReason.INVALID_TYPE: 2,
        DropReason.EVIDENCE_NOT_IN_CHUNK: 1,
        DropReason.INVALID_NAME: 1,
    }


# ---------------------------------------------------------------- 空块与无实体


@pytest.mark.parametrize("text", ["", "   \n\t "])
def test_empty_chunk_returns_empty_list_without_calling_model(text: str):
    identity, _ = _identity()
    identity = ChunkIdentity(
        course_id=identity.course_id,
        document_id=identity.document_id,
        revision_id=identity.revision_id,
        chunk_id=identity.chunk_id,
        ordinal=identity.ordinal,
        text_sha256=text_sha256(text),
        sources=identity.sources,
    )
    client = FakeModelClient()
    result = _extractor(client).extract(identity, text)

    assert result.ok
    assert result.candidates == ()
    assert result.model_calls == 0
    assert client.calls == ()


def test_model_reporting_no_entities_returns_empty_list():
    client, _, _, result = _run('{"entities": []}')

    assert result.ok and result.candidates == () and result.dropped == {}
    assert len(client.calls) == 1


# ---------------------------------------------------------------- 失败路径：修复最多一次


def test_bad_json_is_repaired_once_with_same_model_and_prompt():
    client, identity, text, result = _run(BAD_JSON_TEXT, _reply(_entity()))
    first, repair = client.calls

    assert result.ok
    assert [c.name for c in result.candidates] == ["栈"]
    assert result.model_calls == 2
    assert repair.request.purpose == REPAIR_PURPOSE
    assert isinstance(repair.request, ModelRequest) and isinstance(first.request, ModelRequest)
    assert repair.request.model == first.request.model == MODEL
    assert repair.request.messages == first.request.messages
    assert repair.request.max_output_tokens == MAX_OUT
    assert repair.request.response_format == "json"
    assert result.cache_key == _extractor(FakeModelClient()).cache_key(identity)


def test_bad_json_twice_fails_machine_readably_after_exactly_two_calls():
    client, _, _, result = _run(BAD_JSON_TEXT, "not json at all", _reply(_entity()))

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason == FailureReason.INVALID_JSON
    assert result.failure.reason == "invalid_json"
    assert result.failure.attempts == 2
    assert result.candidates == ()
    assert result.cache_key is None
    assert result.model_calls == 2
    assert len(client.calls) == 2
    assert client.pending == 1  # 第三次脚本从未被消费


@pytest.mark.parametrize(
    "bad",
    [
        "[]",
        '"entities"',
        "{}",
        '{"entities": {"name": "栈"}}',
        '{"entities": null}',
        '{"entity": []}',
        '{"entities": [], "fake": NaN}',
    ],
)
def test_invalid_structure_is_repaired_then_fails(bad: str):
    client, _, _, result = _run(bad, bad)

    expected = FailureReason.INVALID_JSON if "NaN" in bad else FailureReason.INVALID_STRUCTURE
    assert result.failure is not None and result.failure.reason == expected
    assert len(client.calls) == 2


def test_invalid_structure_then_valid_repair_succeeds():
    _, _, _, result = _run('{"entity": []}', _reply(_entity()))

    assert result.ok and len(result.candidates) == 1


def test_fake_default_json_output_is_not_accepted_as_entities():
    # E02 fake 的默认 JSON 输出没有 entities：结构不合规，修复一次后失败（见交接待决）。
    client = FakeModelClient()
    identity, text = _identity()
    result = _extractor(client).extract(identity, text)

    assert result.failure is not None and result.failure.reason == FailureReason.INVALID_STRUCTURE
    assert len(client.calls) == 2


def test_truncated_output_counts_as_non_compliant():
    long_reply = _reply(*[_entity() for _ in range(20)])
    client, _, _, result = _run(long_reply, long_reply, max_output_tokens=len(long_reply) - 1)

    assert result.failure is not None and result.failure.reason == FailureReason.TRUNCATED
    assert len(client.calls) == 2


def test_truncated_then_repaired():
    long_reply = _reply(*[_entity() for _ in range(3)])
    short_reply = _reply(_entity())
    client, _, _, result = _run(long_reply, short_reply, max_output_tokens=len(short_reply) + 5)

    assert result.ok and len(result.candidates) == 1


def test_item_level_drops_do_not_trigger_repair():
    client, _, _, result = _run(_reply(_entity(type_="bad")))

    assert result.ok and result.candidates == ()
    assert len(client.calls) == 1


def test_model_call_errors_propagate_without_repair():
    client = FakeModelClient()
    client.script(ModelTimeoutError(MODEL))
    identity, text = _identity()
    with pytest.raises(ModelTimeoutError):
        _extractor(client).extract(identity, text)
    assert len(client.calls) == 1


def test_repair_call_error_propagates():
    client = FakeModelClient()
    client.script(BAD_JSON_TEXT, ModelServerError(MODEL))
    identity, text = _identity()
    with pytest.raises(ModelServerError):
        _extractor(client).extract(identity, text)
    assert len(client.calls) == 2


# ---------------------------------------------------------------- 输入校验与不泄露


def test_text_must_match_identity_hash():
    client = FakeModelClient()
    identity, text = _identity()
    with pytest.raises(ValueError):
        _extractor(client).extract(identity, text + "篡改")
    assert client.calls == ()


def test_identity_type_is_checked():
    with pytest.raises(TypeError):
        _extractor(FakeModelClient()).extract("rev_x-0", "文本")  # type: ignore[arg-type]


@pytest.mark.parametrize("kwargs", [{"model": ""}, {"model": "  "}, {"max_output_tokens": 0}, {"max_output_tokens": True}])
def test_constructor_rejects_bad_settings(kwargs: dict[str, object]):
    params: dict[str, object] = {"model": MODEL, "max_output_tokens": MAX_OUT}
    params.update(kwargs)
    with pytest.raises(ValueError):
        EntityExtractor(FakeModelClient(), **params)  # type: ignore[arg-type]


def test_constructor_rejects_non_client():
    with pytest.raises(TypeError):
        EntityExtractor(object(), model=MODEL, max_output_tokens=MAX_OUT)  # type: ignore[arg-type]


def test_reprs_do_not_leak_course_text():
    _, _, text, result = _run(_reply(_entity()))
    _, _, _, failed = _run(BAD_JSON_TEXT, BAD_JSON_TEXT)

    for shown in (repr(result), repr(result.candidates[0]), repr(failed), repr(failed.failure)):
        assert "后进先出" not in shown
        assert "栈是一种" not in shown
