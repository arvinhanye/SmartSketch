"""E06：补漏实体抽取（gleaning）——原块 + 首轮（E05）实体 → 遗漏实体差量。

依据：``docs/atomic-task-plan.md`` E06（不开启时零调用；只加遗漏不复制已有实体；预算和轮数有上限）、
``docs/architecture-review-2026-09-22.md``「两阶段抽取……补漏独立开关」、``docs/integrations.md``
「模型接入规则（A07）」（输出不合规修复一次；预算被拒走所在环节既有失败路径；调用记录）。

流程：

1. **开关**：``enabled`` 默认 ``False``。关闭时不渲染提示词、不调用客户端（经 E04 包装时也就不预写
   ``model_calls``），直接返回 ``StopReason.DISABLED``。文档只写了「补漏独立开关」，没有登记环境变量，
   因此开关以构造参数提供，由编排方（E12）决定取值来源（见交接待决）。
2. 输入为 D09 ``ChunkIdentity``、块文本（哈希须与身份一致）与首轮 ``EntityCandidate``（须属于同一块）。
   空白块直接返回 ``EMPTY_CHUNK``，不调用模型。
3. 每轮用 E01 装载器渲染 ``extract_entities_gleaning@GLEANING_PROMPT_VERSION``：``chunk_text`` 为块文本，
   ``entities_json`` 为「首轮 + 此前各轮新增」的 ``[{"name", "type"}]`` JSON 数组；单条 user 消息、JSON 格式、
   声明的输出上限。输出解析与逐条校验**复用 E05**（``_parse``、``_validate``：五类闭集、长度、置信度、
   证据为块文本连续子串、出处对齐），不合规时同一模型、同一消息修复一次（``purpose = "repair"``），
   仍不合规则停止并返回 ``OUTPUT_INVALID``（带 E05 ``ExtractionFailure``）。
4. **去重**：候选名称经 ``entity_name_key``（NFKC、``casefold``、去掉全部空白）与已知集合比对，
   命中即丢弃并计入 ``duplicates``；同一回复内、跨轮次同样去重（保留先出现者）。类型不参与比对：
   同名不同类型视为同一知识点，归并交 E08/E10。
5. **轮数**：``max_rounds`` 取 ``1..MAX_ROUNDS_HARD_LIMIT``，默认 ``DEFAULT_MAX_ROUNDS``。某轮没有新增
   （全部重复、全部被丢弃或空数组）即提前停止（``NO_NEW_ENTITIES``）；跑满即 ``MAX_ROUNDS``。
6. **预算**：每次调用经注入的客户端（E04 ``ModelCallPolicy.bind`` 返回的 ``BoundModelClient``）发出；
   策略在调用前拒绝（``BudgetExceededError``，未发请求）时停止，返回已得差量与 ``BUDGET_EXCEEDED``，
   ``ok`` 为假、``error_code = "BUDGET_EXCEEDED"``：按 A07「抽取阶段（实体、补漏、关系）：本次块尝试失败」，
   由编排方把它当作本次块尝试失败处理。其他 ``ModelCallError``/``PolicyError`` 原样抛出（与 E05 一致，
   交 E04/E12 按 L1/L2 与阶段级临时故障处理）。

日志只写块 ID、轮数、调用数、新增/重复/丢弃计数与停止原因；块文本、实体名称、定义、证据、提示词与
模型输出都不进入日志或 ``repr``。
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from app.services.ai.client import Message, ModelClient, ModelRequest, ModelResult
from app.services.ai.entities import (
    REPAIR_PURPOSE,
    DropReason,
    EntityCandidate,
    ExtractionFailure,
    _OutputRejected,
    _parse,
    _validate,
)
from app.services.ai.policy import BudgetExceededError
from app.services.ai.prompts import PromptLibrary, PromptTemplate
from app.services.chunk_identity import ChunkIdentity, cache_model_id, text_sha256

__all__ = [
    "DEFAULT_MAX_ROUNDS",
    "GLEANING_PROMPT_PURPOSE",
    "GLEANING_PROMPT_VERSION",
    "MAX_ROUNDS_HARD_LIMIT",
    "EntityGleaner",
    "GleaningResult",
    "StopReason",
    "entity_name_key",
]

logger = logging.getLogger(__name__)

#: 提示词用途与本模块固定使用的版本；改模板须同时升此版本与 ``prompts/MANIFEST.md``。
GLEANING_PROMPT_PURPOSE: Final = "extract_entities_gleaning"
GLEANING_PROMPT_VERSION: Final = 2

#: 默认补漏轮数与硬上限。构造参数超出 ``1..MAX_ROUNDS_HARD_LIMIT`` 即报错，不静默截断。
DEFAULT_MAX_ROUNDS: Final = 1
MAX_ROUNDS_HARD_LIMIT: Final = 3

_BUDGET_EXCEEDED_CODE: Final = "BUDGET_EXCEEDED"
_WHITESPACE = re.compile(r"\s+")


def entity_name_key(name: str) -> str:
    """确定性的名称比对键：NFKC（全半角）→ ``casefold``（大小写）→ 去掉全部空白。"""
    return _WHITESPACE.sub("", unicodedata.normalize("NFKC", name).casefold())


class StopReason(StrEnum):
    DISABLED = "disabled"
    EMPTY_CHUNK = "empty_chunk"
    NO_NEW_ENTITIES = "no_new_entities"
    MAX_ROUNDS = "max_rounds"
    BUDGET_EXCEEDED = "budget_exceeded"
    OUTPUT_INVALID = "output_invalid"


_NOT_OK: Final = frozenset({StopReason.BUDGET_EXCEEDED, StopReason.OUTPUT_INVALID})


@dataclass(frozen=True)
class GleaningResult:
    """一个块的补漏结果。``added`` 只含首轮没有的新实体（差量）；``ok`` 为假即本次块尝试失败。"""

    chunk_id: str
    added: tuple[EntityCandidate, ...]
    stop_reason: StopReason
    rounds: int
    model_calls: int
    duplicates: int
    dropped: dict[DropReason, int] = field(hash=False)
    failure: ExtractionFailure | None
    prompt_purpose: str
    prompt_version: int
    prompt_sha256: str | None
    model_id: str | None

    @property
    def ok(self) -> bool:
        return self.stop_reason not in _NOT_OK

    @property
    def error_code(self) -> str | None:
        """契约 ``ErrorCode``：仅预算被拒时为 ``BUDGET_EXCEEDED``；输出不合规见 ``failure``。"""
        return _BUDGET_EXCEEDED_CODE if self.stop_reason is StopReason.BUDGET_EXCEEDED else None


def _is_int(value: object) -> bool:
    return type(value) is int


class _Stop(Exception):
    def __init__(self, reason: StopReason, failure: ExtractionFailure | None = None) -> None:
        super().__init__(reason.value)
        self.reason = reason
        self.failure = failure


class EntityGleaner:
    """补漏实体抽取服务。``client`` 通常是 E04 ``ModelCallPolicy.bind(...)`` 返回的客户端。"""

    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        max_output_tokens: int,
        enabled: bool = False,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        prompts: PromptLibrary | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if not isinstance(client, ModelClient):
            raise TypeError("client must implement ModelClient")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not _is_int(max_output_tokens) or max_output_tokens < 1:
            raise ValueError("max_output_tokens must be an int >= 1")
        if not _is_int(max_rounds) or not 1 <= max_rounds <= MAX_ROUNDS_HARD_LIMIT:
            raise ValueError(f"max_rounds must be an int in 1..{MAX_ROUNDS_HARD_LIMIT}")
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._enabled = enabled
        self._max_rounds = max_rounds
        self._timeout_seconds = timeout_seconds
        self._prompts = prompts if prompts is not None else PromptLibrary()

    def __repr__(self) -> str:
        return (f"EntityGleaner(model={self._model!r}, enabled={self._enabled}, "
                f"max_rounds={self._max_rounds})")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    def prompt(self) -> PromptTemplate:
        return self._prompts.get(GLEANING_PROMPT_PURPOSE, GLEANING_PROMPT_VERSION)

    def glean(
        self, identity: ChunkIdentity, text: str, first_pass: Sequence[EntityCandidate]
    ) -> GleaningResult:
        if not isinstance(identity, ChunkIdentity):
            raise TypeError(f"identity must be ChunkIdentity, got {type(identity).__name__}")
        if not isinstance(text, str):
            raise TypeError("text must be str")
        known_entities = tuple(first_pass)
        for candidate in known_entities:
            if not isinstance(candidate, EntityCandidate):
                raise TypeError("first_pass items must be EntityCandidate")
            if candidate.source.chunk_id != identity.chunk_id or candidate.source.course_id != identity.course_id:
                raise ValueError(f"first_pass candidate does not belong to chunk {identity.chunk_id}")
        if text_sha256(text) != identity.text_sha256:
            raise ValueError(f"text does not match identity.text_sha256 of chunk {identity.chunk_id}")

        if not self._enabled:
            return self._finish(identity, StopReason.DISABLED, None, (), 0, 0, 0, {}, None, None)
        if not text.strip():
            return self._finish(identity, StopReason.EMPTY_CHUNK, None, (), 0, 0, 0, {}, None, None)

        template = self.prompt()
        known: list[dict[str, str]] = [{"name": c.name, "type": c.type} for c in known_entities]
        seen = {entity_name_key(c.name) for c in known_entities}
        added: list[EntityCandidate] = []
        dropped: dict[DropReason, int] = {}
        duplicates = 0
        calls = 0
        rounds = 0
        last: ModelResult | None = None
        stop = StopReason.MAX_ROUNDS
        failure: ExtractionFailure | None = None

        try:
            for _ in range(self._max_rounds):
                rounds += 1
                rendered = template.render(
                    {"chunk_text": text, "entities_json": json.dumps(known, ensure_ascii=False)}
                )
                messages = (Message("user", rendered.text),)
                result, calls = self._call(messages, calls)
                last = result
                try:
                    items = _parse(result)
                except _OutputRejected:
                    result, calls = self._call(messages, calls, repair_of=result)
                    last = result
                    try:
                        items = _parse(result)
                    except _OutputRejected as rejected:
                        raise _Stop(StopReason.OUTPUT_INVALID, ExtractionFailure(rejected.reason, 2)) from None
                candidates, round_dropped = _validate(items, identity, text)
                for reason, count in round_dropped.items():
                    dropped[reason] = dropped.get(reason, 0) + count
                new = 0
                for candidate in candidates:
                    key = entity_name_key(candidate.name)
                    if key in seen:
                        duplicates += 1
                        continue
                    seen.add(key)
                    added.append(candidate)
                    known.append({"name": candidate.name, "type": candidate.type})
                    new += 1
                if new == 0:
                    stop = StopReason.NO_NEW_ENTITIES
                    break
        except _Stop as stopped:
            stop, failure = stopped.reason, stopped.failure

        return self._finish(identity, stop, template, tuple(added), rounds, calls, duplicates, dropped,
                            failure, last)

    def _call(
        self, messages: tuple[Message, ...], calls: int, *, repair_of: ModelResult | None = None
    ) -> tuple[ModelResult, int]:
        if repair_of is None:
            request = self._request(GLEANING_PROMPT_PURPOSE, self._model, messages)
        else:  # 同一模型、同一消息修复一次（integrations「输出不合规」行）
            request = self._request(REPAIR_PURPOSE, repair_of.model_requested, messages)
        try:
            result = self._client.complete(request)
        except BudgetExceededError:
            raise _Stop(StopReason.BUDGET_EXCEEDED) from None
        return result, calls + 1

    def _request(self, purpose: str, model: str, messages: tuple[Message, ...]) -> ModelRequest:
        return ModelRequest(
            purpose=purpose,
            model=model,
            messages=messages,
            max_output_tokens=self._max_output_tokens,
            response_format="json",
            timeout_seconds=self._timeout_seconds,
        )

    def _finish(
        self,
        identity: ChunkIdentity,
        stop: StopReason,
        template: PromptTemplate | None,
        added: tuple[EntityCandidate, ...],
        rounds: int,
        calls: int,
        duplicates: int,
        dropped: dict[DropReason, int],
        failure: ExtractionFailure | None,
        last: ModelResult | None,
    ) -> GleaningResult:
        result = GleaningResult(
            chunk_id=identity.chunk_id,
            added=added,
            stop_reason=stop,
            rounds=rounds,
            model_calls=calls,
            duplicates=duplicates,
            dropped=dropped,
            failure=failure,
            prompt_purpose=GLEANING_PROMPT_PURPOSE,
            prompt_version=GLEANING_PROMPT_VERSION,
            prompt_sha256=template.sha256 if template is not None else None,
            model_id=cache_model_id(last) if last is not None else None,
        )
        logger.info(
            "gleaning chunk_id=%s stop=%s rounds=%d calls=%d added=%d duplicates=%d dropped=%d",
            identity.chunk_id, stop.value, rounds, calls, len(added), duplicates, sum(dropped.values()),
        )
        return result
