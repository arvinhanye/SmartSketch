"""E05：块级实体抽取——一个语义块 → 有来源的规范实体候选。

依据：``specs/course-knowledge-graph.md``（知识点字段、证据链）、``src/contracts/api.v1.yaml``
``KnowledgePointType``（五类闭集）、``docs/integrations.md``「模型接入规则」（输出不合规在同一模型
修复一次，不走 L1、不计熔断）、``specs/task-processing.md`` §8.3 L2（修复后仍不合规即本次块尝试失败）。

流程：

1. 输入为 D09 ``ChunkIdentity`` 与块文本；文本的 ``text_sha256`` 必须与身份一致（防止调用方配错块）。
   空白块直接返回空列表，不调用模型。
2. 用 E01 装载器渲染 ``extract_entities@ENTITY_PROMPT_VERSION``，以单条 user 消息、JSON 格式、
   声明的输出上限经注入的 ``ModelClient`` 调用一次。E04 的预算、退避、主备切换由注入的客户端负责，
   本模块不重试调用错误：``ModelCallError`` 原样抛出，交 E04/E12 按 L1/L2 处理。
3. 输出不合规（坏 JSON、顶层结构不对、``finish_reason = length`` 截断）时，用同一模型、同一消息
   发一次修复调用（``purpose = REPAIR_PURPOSE``）；仍不合规则返回 ``failure``（可机读原因），不抛异常。
   修复调用不内联新的提示词正文：MANIFEST 规定提示词只经装载器取用，专用修复模板见交接待决。
4. 逐条校验候选：类型限五类闭集，名称/定义/证据为字符串且去首尾空白后长度在范围内，置信度可空、
   否则为 [0, 1] 内的有限数；证据必须是块文本的连续子串（精确匹配，不做空白或标点归一）。
   不合格的条目丢弃并按原因计数，不触发修复。
5. 候选带来源：课程、资料、修订、块 ID，证据在块文本中的半开区间（首次出现），以及证据覆盖到的
   D08 ``ChunkSource``（据此取页码与章节路径；无法对齐时退回整块全部出处）。
6. 成功结果带 D09 抽取缓存键（课程、块、文本哈希、提示词用途/版本/摘要、实际给出结果的模型 ID）；
   本模块不读写缓存存储（见交接待决）。

本模块不记录日志；块文本、定义与证据不进入任何 ``repr``，失败信息只含原因码。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from app.services.ai.client import Message, ModelClient, ModelOutputError, ModelRequest, ModelResult
from app.services.ai.prompts import PromptLibrary, PromptTemplate
from app.services.chunk_identity import ChunkIdentity, cache_model_id, extraction_cache_key, text_sha256
from app.services.chunking import ChunkSource

__all__ = [
    "DEFINITION_MAX_CHARS",
    "ENTITY_PROMPT_PURPOSE",
    "ENTITY_PROMPT_VERSION",
    "ENTITY_TYPES",
    "EVIDENCE_MAX_CHARS",
    "NAME_MAX_CHARS",
    "REPAIR_PURPOSE",
    "DropReason",
    "EntityCandidate",
    "EntityExtraction",
    "EntityExtractor",
    "EntitySource",
    "ExtractionFailure",
    "FailureReason",
]

#: 提示词用途与本模块固定使用的版本；改模板须同时升此版本与 ``prompts/MANIFEST.md``。
ENTITY_PROMPT_PURPOSE: Final = "extract_entities"
ENTITY_PROMPT_VERSION: Final = 2
#: 修复调用的 ``ModelRequest.purpose``（E02 接口注释的示例值；E03 用途枚举待定，见交接待决）。
REPAIR_PURPOSE: Final = "repair"

#: 契约 ``KnowledgePointType``（S2 表 6.3 的五类知识点），闭集、小写、顺序与契约一致。
ENTITY_TYPES: Final = ("concept", "theorem", "formula", "method", "example")
_ENTITY_TYPE_SET: Final = frozenset(ENTITY_TYPES)

# 长度上限（字符数，去首尾空白后计）。规格未给具体值，本任务暂定并写入提示词 v2，待签收（交接待决）。
NAME_MAX_CHARS: Final = 64
DEFINITION_MAX_CHARS: Final = 500
EVIDENCE_MAX_CHARS: Final = 500

_SECTION_SEPARATOR: Final = "\n\n"  # D08 ``_render`` 拼接来源段的分隔符


class DropReason(StrEnum):
    """单条候选被丢弃的原因（计数用，不触发修复）。"""

    NOT_OBJECT = "not_object"
    INVALID_NAME = "invalid_name"
    INVALID_TYPE = "invalid_type"
    INVALID_DEFINITION = "invalid_definition"
    INVALID_EVIDENCE = "invalid_evidence"
    EVIDENCE_NOT_IN_CHUNK = "evidence_not_in_chunk"
    INVALID_CONFIDENCE = "invalid_confidence"


class FailureReason(StrEnum):
    """整块输出不合规的原因（修复一次后仍不合规）。"""

    INVALID_JSON = "invalid_json"
    INVALID_STRUCTURE = "invalid_structure"
    TRUNCATED = "truncated"


@dataclass(frozen=True)
class EntitySource:
    """候选的出处。``evidence_start``/``evidence_end`` 是块文本中的半开字符区间。"""

    course_id: str
    document_id: str
    revision_id: str
    chunk_id: str
    evidence_start: int
    evidence_end: int
    sources: tuple[ChunkSource, ...]


@dataclass(frozen=True)
class EntityCandidate:
    name: str
    type: str
    definition: str = field(repr=False)
    evidence: str = field(repr=False)
    confidence: float | None
    source: EntitySource


@dataclass(frozen=True)
class ExtractionFailure:
    reason: FailureReason
    attempts: int


@dataclass(frozen=True)
class EntityExtraction:
    """一个块的抽取结果。``failure`` 非空即本次块尝试失败（L2），``candidates`` 为空。"""

    chunk_id: str
    candidates: tuple[EntityCandidate, ...]
    dropped: dict[DropReason, int] = field(hash=False)
    failure: ExtractionFailure | None
    prompt_purpose: str
    prompt_version: int
    prompt_sha256: str
    model_id: str | None
    cache_key: str | None
    model_calls: int

    @property
    def ok(self) -> bool:
        return self.failure is None


class _OutputRejected(Exception):
    def __init__(self, reason: FailureReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _is_int(value: object) -> bool:
    return type(value) is int


class EntityExtractor:
    """块级实体抽取服务。``client`` 可以是 E02 fake、E03 适配器或 E04 包装后的客户端。"""

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
        if not isinstance(model, str) or not model.strip():
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
        return self._prompts.get(ENTITY_PROMPT_PURPOSE, ENTITY_PROMPT_VERSION)

    def cache_key(self, identity: ChunkIdentity, model_id: str | None = None) -> str:
        """D09 抽取缓存键；查找时 ``model_id`` 取将要请求的模型（默认本实例的模型）。"""
        template = self.prompt()
        return extraction_cache_key(
            identity,
            prompt_purpose=template.purpose,
            prompt_version=template.version,
            prompt_sha256=template.sha256,
            model_id=self._model if model_id is None else model_id,
        )

    def extract(self, identity: ChunkIdentity, text: str) -> EntityExtraction:
        if not isinstance(identity, ChunkIdentity):
            raise TypeError(f"identity must be ChunkIdentity, got {type(identity).__name__}")
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if text_sha256(text) != identity.text_sha256:
            raise ValueError(f"text does not match identity.text_sha256 of chunk {identity.chunk_id}")
        template = self.prompt()

        def outcome(
            candidates: tuple[EntityCandidate, ...],
            dropped: dict[DropReason, int],
            failure: ExtractionFailure | None,
            result: ModelResult | None,
            calls: int,
        ) -> EntityExtraction:
            model_id = cache_model_id(result) if result is not None else None
            return EntityExtraction(
                chunk_id=identity.chunk_id,
                candidates=candidates,
                dropped=dropped,
                failure=failure,
                prompt_purpose=template.purpose,
                prompt_version=template.version,
                prompt_sha256=template.sha256,
                model_id=model_id,
                cache_key=self.cache_key(identity, model_id) if failure is None and model_id is not None else None,
                model_calls=calls,
            )

        if not text.strip():
            return outcome((), {}, None, None, 0)

        rendered = template.render({"chunk_text": text})
        messages = (Message("user", rendered.text),)
        result = self._client.complete(self._request(ENTITY_PROMPT_PURPOSE, self._model, messages))
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

        candidates, dropped = _validate(items, identity, text)
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


# ---------------------------------------------------------------- 输出解析与校验


def _parse(result: ModelResult) -> list[Any]:
    if result.finish_reason == "length":
        raise _OutputRejected(FailureReason.TRUNCATED)
    try:
        data = result.json()
    except ModelOutputError:
        raise _OutputRejected(FailureReason.INVALID_JSON) from None
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise _OutputRejected(FailureReason.INVALID_STRUCTURE)
    return data["entities"]


def _text_field(value: object, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > max_chars:
        return None
    return value


def _confidence(value: object) -> tuple[bool, float | None]:
    if value is None:
        return True, None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False, None
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        return False, None
    return True, number


def _validate(
    items: list[Any], identity: ChunkIdentity, text: str
) -> tuple[tuple[EntityCandidate, ...], dict[DropReason, int]]:
    candidates: list[EntityCandidate] = []
    dropped: dict[DropReason, int] = {}
    layout = _layout(identity.sources, text)

    def drop(reason: DropReason) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for item in items:
        if not isinstance(item, dict):
            drop(DropReason.NOT_OBJECT)
            continue
        name = _text_field(item.get("name"), NAME_MAX_CHARS)
        if name is None:
            drop(DropReason.INVALID_NAME)
            continue
        type_ = item.get("type")
        if not isinstance(type_, str) or type_ not in _ENTITY_TYPE_SET:
            drop(DropReason.INVALID_TYPE)
            continue
        definition = _text_field(item.get("definition"), DEFINITION_MAX_CHARS)
        if definition is None:
            drop(DropReason.INVALID_DEFINITION)
            continue
        evidence = _text_field(item.get("evidence"), EVIDENCE_MAX_CHARS)
        if evidence is None:
            drop(DropReason.INVALID_EVIDENCE)
            continue
        valid, confidence = _confidence(item.get("confidence"))
        if not valid:
            drop(DropReason.INVALID_CONFIDENCE)
            continue
        start = text.find(evidence)
        if start < 0:
            drop(DropReason.EVIDENCE_NOT_IN_CHUNK)
            continue
        end = start + len(evidence)
        candidates.append(
            EntityCandidate(
                name=name,
                type=type_,
                definition=definition,
                evidence=evidence,
                confidence=confidence,
                source=EntitySource(
                    course_id=identity.course_id,
                    document_id=identity.document_id,
                    revision_id=identity.revision_id,
                    chunk_id=identity.chunk_id,
                    evidence_start=start,
                    evidence_end=end,
                    sources=_sources_for(layout, identity.sources, start, end),
                ),
            )
        )
    return tuple(candidates), dropped


# ---------------------------------------------------------------- 证据 → 出处


def _layout(sources: tuple[ChunkSource, ...], text: str) -> list[tuple[int, int, ChunkSource]] | None:
    """按 D08 的拼接方式（每段「章节路径\\n正文」，段间两个换行）重建各出处在块文本中的区间。

    区间含该段的章节路径前缀。重建总长与块文本不符（上游格式变化）时返回 ``None``，
    调用方退回整块全部出处，宁可粗也不指错位置。
    """
    segments: list[tuple[int, int, ChunkSource]] = []
    position = 0
    for index, source in enumerate(sources):
        if index:
            position += len(_SECTION_SEPARATOR)
        path = source.locator.section_path
        length = (len(path) + 1 if path else 0) + (source.end - source.start)
        segments.append((position, position + length, source))
        position += length
    if position != len(text):
        return None
    return segments


def _sources_for(
    layout: list[tuple[int, int, ChunkSource]] | None, sources: tuple[ChunkSource, ...], start: int, end: int
) -> tuple[ChunkSource, ...]:
    if layout is None:
        return sources
    hit = tuple(source for seg_start, seg_end, source in layout if seg_start < end and start < seg_end)
    return hit or sources
