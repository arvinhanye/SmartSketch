"""E11：关系两阶段抽取的第二阶段——小节实体 ID 表 + 来源块 → 四类关系候选。

依据：``docs/architecture-review-2026-09-22.md``「两阶段抽取：块级实体 → 小节实体表 → 关系；实体规范化后
再约束关系端点；结构校验失败修复一次」、``specs/course-knowledge-graph.md``（四类关系闭集、``PREREQUISITE``
语义、DAG-9「自动候选自环在抽取规则校验阶段直接删除」）、``docs/integrations.md``「模型接入规则」
（输出不合规在同一模型修复一次）、``docs/atomic-task-plan.md`` E11 验收（悬空端点/跨课/自环/重复边拦截；
仅提及不判前置；方向反例）。

流程：

1. 输入为课程 ID、同一小节已规范化（E08～E10 之后）的 ``SectionEntity`` 表与该小节的来源块
   （D09 ``ChunkIdentity`` + 块文本）。**课程隔离**：任一实体或块不属于该课程、块文本哈希与身份不符、
   实体 ID 重复或实体类型不在五类闭集内，都是调用方错误，抛 ``ValueError``，不调用模型。
   草稿可见性 V 的过滤由调用方（E12）在取实体表时完成（ADR-011 修订 1），本模块不读图库。
2. 实体少于两个或没有非空白来源块时，不可能有关系，直接返回空结果、0 次调用。
3. 用 E01 装载器渲染 ``extract_relations@RELATION_PROMPT_VERSION``：``entity_table`` 为
   ``[{"id","name","type"}]`` JSON（每行一项），``source_chunks`` 为「[块 ID]\\n块文本」段落。
   单条 user 消息、JSON 格式、声明的输出上限，经注入的 ``ModelClient`` 调用一次。E04 的预算、退避、
   主备切换由注入的客户端负责；``ModelCallError``（含预算拒绝）原样抛出，与 E05 一致。
4. 输出不合规（坏 JSON、没有 ``relations`` 数组、``finish_reason = length`` 截断）时，同一模型、同一
   消息修复一次（``purpose = REPAIR_PURPOSE``）；仍不合规返回 ``failure``，不抛异常。
5. 逐条校验（不合格丢弃并按原因计数，不触发修复）：
   - 类型限 ``RELATION_TYPES`` 闭集，只接受大写原样；
   - ``from_id``/``to_id`` 必须是实体表中的 ID（悬空端点丢弃；他课 ID 不在表内，同样视为悬空）；
   - 自环（两端相同）删除；
   - 证据必须是某个来源块文本的连续子串（精确匹配），并据此定位块与 D08 出处；
   - **仅提及不判前置**：``PREREQUISITE`` 的证据须含 ``PREREQUISITE_CUES`` 中的先修表述，
     否则丢弃（宁缺勿错：前置边进入 DAG 与学习路径，误判代价高）；
   - **方向**：``EXAMPLE_OF`` 的 ``to_id`` 是例子类实体而 ``from_id`` 不是时，判为方向颠倒并丢弃，
     不擅自翻转；
   - 重复边：同一 ``(from_id, to_id, type)`` 只保留首条合格者；``RELATED_TO`` 无方向，``A→B`` 与
     ``B→A`` 视为同一条。
6. 候选带出处（课程、资料、修订、块 ID、证据半开区间、证据覆盖的 D08 ``ChunkSource``），状态、
   置信度阈值、成环降级都不在本模块判定（F04/F13 与 D-08）。

本模块不记录日志；块文本、实体名称与证据不进入任何 ``repr``，失败信息只含原因码。
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from app.services.ai.client import Message, ModelClient, ModelOutputError, ModelRequest, ModelResult
from app.services.ai.entities import (
    ENTITY_TYPES,
    EVIDENCE_MAX_CHARS,
    REPAIR_PURPOSE,
    ExtractionFailure,
    FailureReason,
    _confidence,
    _layout,
    _OutputRejected,
    _sources_for,
    _text_field,
)
from app.services.ai.prompts import PromptLibrary, PromptTemplate
from app.services.chunk_identity import ChunkIdentity, cache_model_id, text_sha256
from app.services.chunking import ChunkSource

__all__ = [
    "PREREQUISITE_CUES",
    "RELATION_PROMPT_PURPOSE",
    "RELATION_PROMPT_VERSION",
    "RELATION_TYPES",
    "RelationCandidate",
    "RelationDropReason",
    "RelationExtraction",
    "RelationExtractor",
    "RelationSource",
    "SectionEntity",
    "SourceChunk",
]

#: 提示词用途与本模块固定使用的版本；改模板须同时升此版本与 ``prompts/MANIFEST.md``。
RELATION_PROMPT_PURPOSE: Final = "extract_relations"
RELATION_PROMPT_VERSION: Final = 2

#: 契约 ``RelationType``（ADR-008），闭集、大写、顺序与契约一致。
RELATION_TYPES: Final = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")
_RELATION_TYPE_SET: Final = frozenset(RELATION_TYPES)
_ENTITY_TYPE_SET: Final = frozenset(ENTITY_TYPES)
_EXAMPLE_TYPE: Final = "example"

#: 先修表述（NFKC + casefold 后按子串匹配）。规格未给清单，本任务暂定，见交接待决。
PREREQUISITE_CUES: Final = (
    "先修",
    "前置",
    "前提",
    "基础",
    "先学",
    "先掌握",
    "先了解",
    "先理解",
    "需要先",
    "必须先",
    "之前需",
    "之前要",
    "之前应",
    "之前必须",
    "后才",
    "才能",
    "依赖于",
    "建立在",
    "prerequisite",
    "requires",
    "depends on",
    "builds on",
    "before learning",
)
_CUES_FOLDED: Final = tuple(unicodedata.normalize("NFKC", cue).casefold() for cue in PREREQUISITE_CUES)


class RelationDropReason(StrEnum):
    """单条关系被丢弃的原因（计数用，不触发修复）。"""

    NOT_OBJECT = "not_object"
    INVALID_TYPE = "invalid_type"
    INVALID_ENDPOINT = "invalid_endpoint"
    DANGLING_ENDPOINT = "dangling_endpoint"
    SELF_LOOP = "self_loop"
    INVALID_EVIDENCE = "invalid_evidence"
    EVIDENCE_NOT_IN_SOURCES = "evidence_not_in_sources"
    INVALID_CONFIDENCE = "invalid_confidence"
    PREREQUISITE_WITHOUT_CUE = "prerequisite_without_cue"
    REVERSED_DIRECTION = "reversed_direction"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class SectionEntity:
    """小节实体表的一项：融合后的知识点 ID（草稿 ``kp_id`` 或 E12 约定的临时 ID）。"""

    entity_id: str
    course_id: str
    name: str = field(repr=False)
    type: str


@dataclass(frozen=True)
class SourceChunk:
    identity: ChunkIdentity
    text: str = field(repr=False)


@dataclass(frozen=True)
class RelationSource:
    """关系的出处。``evidence_start``/``evidence_end`` 是所在块文本中的半开字符区间。"""

    course_id: str
    document_id: str
    revision_id: str
    chunk_id: str
    evidence_start: int
    evidence_end: int
    sources: tuple[ChunkSource, ...]


@dataclass(frozen=True)
class RelationCandidate:
    from_id: str
    to_id: str
    type: str
    evidence: str = field(repr=False)
    confidence: float | None
    source: RelationSource


@dataclass(frozen=True)
class RelationExtraction:
    """一个小节的关系抽取结果。``failure`` 非空即本次尝试失败（L2），``candidates`` 为空。"""

    course_id: str
    candidates: tuple[RelationCandidate, ...]
    dropped: dict[RelationDropReason, int] = field(hash=False)
    failure: ExtractionFailure | None
    prompt_purpose: str
    prompt_version: int
    prompt_sha256: str
    model_id: str | None
    model_calls: int

    @property
    def ok(self) -> bool:
        return self.failure is None


def _is_int(value: object) -> bool:
    return type(value) is int


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


class RelationExtractor:
    """小节级关系抽取服务。``client`` 可以是 E02 fake、E03 适配器或 E04 包装后的客户端。"""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        max_output_tokens: int,
        prompts: PromptLibrary | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if not isinstance(client, ModelClient):
            raise TypeError("client must implement ModelClient")
        if not _nonblank(model):
            raise ValueError("model must be a non-empty string")
        if not _is_int(max_output_tokens) or max_output_tokens < 1:
            raise ValueError("max_output_tokens must be an int >= 1")
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._timeout_seconds = timeout_seconds
        self._prompts = prompts if prompts is not None else PromptLibrary()

    @property
    def model(self) -> str:
        return self._model

    def prompt(self) -> PromptTemplate:
        return self._prompts.get(RELATION_PROMPT_PURPOSE, RELATION_PROMPT_VERSION)

    def extract(
        self, course_id: str, entities: Sequence[SectionEntity], chunks: Sequence[SourceChunk]
    ) -> RelationExtraction:
        entity_types = _check_entities(course_id, entities)
        chunks = _check_chunks(course_id, chunks)
        template = self.prompt()

        def outcome(
            candidates: tuple[RelationCandidate, ...],
            dropped: dict[RelationDropReason, int],
            failure: ExtractionFailure | None,
            result: ModelResult | None,
            calls: int,
        ) -> RelationExtraction:
            return RelationExtraction(
                course_id=course_id,
                candidates=candidates,
                dropped=dropped,
                failure=failure,
                prompt_purpose=template.purpose,
                prompt_version=template.version,
                prompt_sha256=template.sha256,
                model_id=cache_model_id(result) if result is not None else None,
                model_calls=calls,
            )

        texts = tuple(chunk for chunk in chunks if chunk.text.strip())
        if len(entities) < 2 or not texts:
            return outcome((), {}, None, None, 0)

        rendered = template.render(
            {"entity_table": _render_entities(entities), "source_chunks": _render_chunks(texts)}
        )
        messages = (Message("user", rendered.text),)
        result = self._client.complete(self._request(RELATION_PROMPT_PURPOSE, self._model, messages))
        calls = 1
        try:
            items = _parse(result)
        except _OutputRejected:
            # 同一模型、同一消息修复一次（integrations「输出不合规」行）。
            result = self._client.complete(self._request(REPAIR_PURPOSE, result.model_requested, messages))
            calls = 2
            try:
                items = _parse(result)
            except _OutputRejected as rejected:
                return outcome((), {}, ExtractionFailure(rejected.reason, calls), result, calls)

        candidates, dropped = _validate(items, entity_types, texts)
        return outcome(candidates, dropped, None, result, calls)

    def _request(self, purpose: str, model: str, messages: tuple[Message, ...]) -> ModelRequest:
        return ModelRequest(
            purpose=purpose,
            model=model,
            messages=messages,
            max_output_tokens=self._max_output_tokens,
            response_format="json",
            timeout_seconds=self._timeout_seconds,
        )


# ---------------------------------------------------------------- 输入校验与渲染


def _check_entities(course_id: str, entities: Sequence[SectionEntity]) -> dict[str, str]:
    if not _nonblank(course_id):
        raise ValueError("course_id must be a non-empty string")
    types: dict[str, str] = {}
    for entity in entities:
        if not isinstance(entity, SectionEntity):
            raise TypeError(f"entities must be SectionEntity, got {type(entity).__name__}")
        if entity.course_id != course_id:
            raise ValueError(f"entity {entity.entity_id!r} belongs to another course")
        if not _nonblank(entity.entity_id) or entity.entity_id != entity.entity_id.strip():
            raise ValueError("entity_id must be a non-empty string without surrounding whitespace")
        if not _nonblank(entity.name):
            raise ValueError(f"entity {entity.entity_id!r} has an empty name")
        if entity.type not in _ENTITY_TYPE_SET:
            raise ValueError(f"entity {entity.entity_id!r} has an unknown type")
        if entity.entity_id in types:
            raise ValueError(f"duplicate entity_id {entity.entity_id!r}")
        types[entity.entity_id] = entity.type
    return types


def _check_chunks(course_id: str, chunks: Sequence[SourceChunk]) -> tuple[SourceChunk, ...]:
    seen: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, SourceChunk) or not isinstance(chunk.identity, ChunkIdentity):
            raise TypeError("chunks must be SourceChunk with a ChunkIdentity")
        identity = chunk.identity
        if identity.course_id != course_id:
            raise ValueError(f"chunk {identity.chunk_id} belongs to another course")
        if not isinstance(chunk.text, str) or text_sha256(chunk.text) != identity.text_sha256:
            raise ValueError(f"text does not match identity.text_sha256 of chunk {identity.chunk_id}")
        if identity.chunk_id in seen:
            raise ValueError(f"duplicate chunk {identity.chunk_id}")
        seen.add(identity.chunk_id)
    return tuple(chunks)


def _render_entities(entities: Sequence[SectionEntity]) -> str:
    rows = (
        json.dumps({"id": e.entity_id, "name": e.name.strip(), "type": e.type}, ensure_ascii=False)
        for e in entities
    )
    return "[\n" + ",\n".join(rows) + "\n]"


def _render_chunks(chunks: Sequence[SourceChunk]) -> str:
    return "\n\n".join(f"[{chunk.identity.chunk_id}]\n{chunk.text}" for chunk in chunks)


# ---------------------------------------------------------------- 输出解析与校验


def _parse(result: ModelResult) -> list[Any]:
    if result.finish_reason == "length":
        raise _OutputRejected(FailureReason.TRUNCATED)
    try:
        data = result.json()
    except ModelOutputError:
        raise _OutputRejected(FailureReason.INVALID_JSON) from None
    if not isinstance(data, dict) or not isinstance(data.get("relations"), list):
        raise _OutputRejected(FailureReason.INVALID_STRUCTURE)
    return data["relations"]


def _has_prerequisite_cue(evidence: str) -> bool:
    folded = unicodedata.normalize("NFKC", evidence).casefold()
    return any(cue in folded for cue in _CUES_FOLDED)


def _edge_key(from_id: str, to_id: str, type_: str) -> tuple[str, str, str]:
    if type_ == "RELATED_TO" and to_id < from_id:
        from_id, to_id = to_id, from_id
    return from_id, to_id, type_


def _validate(
    items: list[Any], entity_types: dict[str, str], chunks: tuple[SourceChunk, ...]
) -> tuple[tuple[RelationCandidate, ...], dict[RelationDropReason, int]]:
    candidates: list[RelationCandidate] = []
    dropped: dict[RelationDropReason, int] = {}
    seen: set[tuple[str, str, str]] = set()
    layouts: dict[str, list[tuple[int, int, ChunkSource]] | None] = {}

    def drop(reason: RelationDropReason) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for item in items:
        if not isinstance(item, dict):
            drop(RelationDropReason.NOT_OBJECT)
            continue
        type_ = item.get("type")
        if not isinstance(type_, str) or type_ not in _RELATION_TYPE_SET:
            drop(RelationDropReason.INVALID_TYPE)
            continue
        from_id, to_id = item.get("from_id"), item.get("to_id")
        if not isinstance(from_id, str) or not isinstance(to_id, str):
            drop(RelationDropReason.INVALID_ENDPOINT)
            continue
        if from_id not in entity_types or to_id not in entity_types:
            drop(RelationDropReason.DANGLING_ENDPOINT)
            continue
        if from_id == to_id:
            drop(RelationDropReason.SELF_LOOP)
            continue
        evidence = _text_field(item.get("evidence"), EVIDENCE_MAX_CHARS)
        if evidence is None:
            drop(RelationDropReason.INVALID_EVIDENCE)
            continue
        valid, confidence = _confidence(item.get("confidence"))
        if not valid:
            drop(RelationDropReason.INVALID_CONFIDENCE)
            continue
        located = _locate(evidence, chunks)
        if located is None:
            drop(RelationDropReason.EVIDENCE_NOT_IN_SOURCES)
            continue
        if type_ == "PREREQUISITE" and not _has_prerequisite_cue(evidence):
            drop(RelationDropReason.PREREQUISITE_WITHOUT_CUE)
            continue
        if (
            type_ == "EXAMPLE_OF"
            and entity_types[to_id] == _EXAMPLE_TYPE
            and entity_types[from_id] != _EXAMPLE_TYPE
        ):
            drop(RelationDropReason.REVERSED_DIRECTION)
            continue
        key = _edge_key(from_id, to_id, type_)
        if key in seen:
            drop(RelationDropReason.DUPLICATE)
            continue
        seen.add(key)

        chunk, start = located
        end = start + len(evidence)
        identity = chunk.identity
        if identity.chunk_id not in layouts:
            layouts[identity.chunk_id] = _layout(identity.sources, chunk.text)
        candidates.append(
            RelationCandidate(
                from_id=from_id,
                to_id=to_id,
                type=type_,
                evidence=evidence,
                confidence=confidence,
                source=RelationSource(
                    course_id=identity.course_id,
                    document_id=identity.document_id,
                    revision_id=identity.revision_id,
                    chunk_id=identity.chunk_id,
                    evidence_start=start,
                    evidence_end=end,
                    sources=_sources_for(layouts[identity.chunk_id], identity.sources, start, end),
                ),
            )
        )
    return tuple(candidates), dropped


def _locate(evidence: str, chunks: tuple[SourceChunk, ...]) -> tuple[SourceChunk, int] | None:
    for chunk in chunks:
        start = chunk.text.find(evidence)
        if start >= 0:
            return chunk, start
    return None
