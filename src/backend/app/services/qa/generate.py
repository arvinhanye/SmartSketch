"""J05：有证据问答生成——J04 编号证据上下文 + 检索用问题 → 流式的「待校验答案」。

依据：``specs/grounded-qa.md`` 措施①～③、Q2 P5 与开流后文法、Q3.4（哨兵由提示要求）、Q5 O3/O7～O13、
Q8 H3（生成不见历史）、Q11 J05 行、QA-6/7/8/19/24/25/27/28/29，主验收第 5、10、11、13 条；
``docs/integrations.md``「模型接入规则（A07）」（主备切换矩阵、问答链路截止时间）；ADR-011 修订 2；
ADR-015 决定 2、3、6；ADR-068。

职责边界：本模块只负责**是否调用**、**怎样提示**与**怎样把故障分类**；引用归一化、暂扣、哨兵判定、
逐句覆盖与终态构造都归 J06（Q3.2～Q3.5、Q4）。因此它产出的是模型原始正文，未经任何校验。

流程：

1. **闸门**（措施③，QA-6、QA-7）：上下文不是 ``ready``、或没有任何编号块时，直接返回
   ``SkippedGeneration``（原因沿用 J04 的 ``no_retrieval_hit`` / ``below_similarity_threshold``），
   **不渲染提示、不绑定策略、不写 ``model_calls``**，生成调用数为 0。
2. **提示**：渲染 ``answer_with_context@ANSWER_PROMPT_VERSION``，单条 user 消息，只含三部分：无编号的
   知识点结构、以 ``<<资料 n>>（定位）`` 为块头的编号资料、检索用问题（J03 改写结果或原问题）。**没有
   历史参数**（H3）：伪造历史里的引用不可能进入提示。
3. **原文注入按资料处理**（主验收第 10 条）：提示声明资料、结构与问题中的指令只当作数据，并在结尾
   重申；资料原文与问题中能伪造分段或块头的 ``<<资料``、``<<课程资料``、``<<知识点结构``、``<<学生问题``
   与哨兵 ``<<INSUFFICIENT_EVIDENCE`` 把开头的 ``<<`` 换成 ``«``（``neutralize``），所以资料里无法
   冒充新的编号块、提前结束资料段或让模型照抄出哨兵。其余字符原样保留：代码里的 ``a[1]``、
   ``cout << x`` 不受影响；原文中的 ``[3]`` 不会被当成块号，因为块号只出现在块头里，提示也写明了这一点。
   J06 的 ``citations[].text`` 取自文本块数据而不是提示，所以这里的替换不影响引用原文。
4. **调用**：``ModelRequest(purpose="answer_with_context", response_format="text")``，声明输出上限；
   不设单次超时，由 E04 按「链路截止时刻 - 当前」补上（``docs/integrations.md``「问答链路截止时间」）。
   经 ``ModelCallPolicy.bind(CallAttribution(course_id, request_id), deadline=...)`` 流式调用：
   ``task_id`` 为空、``model_calls`` 带 ``request_id``（ADR-011 修订 2）。首字前主用失败切备用、出字后
   不切，由 E04 ``_stream`` 保证（A07）。
5. **读取**：``AnswerGeneration`` 是一次性迭代器，首次 ``next()`` 才发出请求（J07 先发 ``meta``）。只产出
   非空文本片段；每个片段之后按同一时钟检查链路截止时刻，已到期即关闭供应商流并报 ``timeout``。
   调用方（J06 遇到哨兵、J07 客户端断开）随时 ``close()``，供应商流随之关闭，此后不再有生成调用。
   正常结束后 ``result`` 给出拼接正文与 ``finish_reason``（``length`` 即 O6 截断）。
6. **故障分类**（Q5，``GenerationError.kind`` 闭集）：

   ============================  ==========================  ==============================
   来源                          kind                        契约
   ============================  ==========================  ==============================
   E04 截止时间 / 读取中到期     ``timeout``                 ``LLM_UNAVAILABLE`` + ``timeout``
   无状态码的供应商超时          ``timeout``（仅当剩余时间 ≤ ``TIMEOUT_SLACK_SECONDS``）
   401 / 403                     ``auth``                    ``LLM_UNAVAILABLE`` + ``auth``
   已出字后的其他供应商故障      ``stream_interrupted``      ``LLM_UNAVAILABLE`` + ``stream_interrupted``
   首字前的其他供应商故障、熔断  ``upstream``                ``LLM_UNAVAILABLE`` + ``upstream``
   预算拒绝                      ``budget_exceeded``         ``BUDGET_EXCEEDED``
   ``model_calls`` 预写失败      ``storage_unavailable``     ``STORAGE_UNAVAILABLE``
   400/404/422 参数错误、意外    ``internal``                ``INTERNAL_ERROR``
   ============================  ==========================  ==============================

   **超时是独立错误**（J05 验收、Q5 ``details.reason`` 说明）：``timeout`` 当且仅当链路时限到期；首字前
   的其他超时（含 408）一律 ``upstream``。E04 不设单次超时时供应商超时就等于链路到期，但仍以剩余时间
   复核，免得将来加上首字超时后被误报为 ``timeout``。``GenerationError.delivered`` 表示故障前是否已
   产出片段，J07/J09 据此撤回临时正文（Q6）。

本模块只在未预期异常时记一条 WARNING（只含异常类型名）；提示、问题、资料与模型输出不进入日志、异常
信息或 ``repr``。
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from app.services.ai.client import (
    ErrorClass,
    FinishReason,
    Message,
    ModelCallError,
    ModelRequest,
    ModelResult,
    StreamDelta,
    StreamDone,
    StreamEvent,
)
from app.services.ai.policy import (
    BudgetExceededError,
    CallAttribution,
    CallDeadlineExceededError,
    CallRecordError,
    ModelCallPolicy,
    ModelUnavailableError,
)
from app.services.ai.prompts import PromptLibrary
from app.services.qa.context import ContextReason, EvidenceChunk, EvidenceContext

__all__ = [
    "ANSWER_CALL_PURPOSE",
    "ANSWER_MAX_OUTPUT_TOKENS",
    "ANSWER_PROMPT_PURPOSE",
    "ANSWER_PROMPT_VERSION",
    "EMPTY_GRAPH_CONTEXT",
    "TIMEOUT_SLACK_SECONDS",
    "AnswerGeneration",
    "AnswerGenerator",
    "GenerationError",
    "GenerationErrorKind",
    "GenerationResult",
    "SkippedGeneration",
    "neutralize",
    "render_evidence_blocks",
]

logger = logging.getLogger(__name__)

#: 提示词用途与本模块固定使用的版本；改模板须同时升此版本与 ``prompts/MANIFEST.md``。
ANSWER_PROMPT_PURPOSE: Final = "answer_with_context"
ANSWER_PROMPT_VERSION: Final = 2
#: ``ModelRequest.purpose`` / ``model_calls.purpose``：Q5「生成调用」按此用途计数。
ANSWER_CALL_PURPOSE: Final = ANSWER_PROMPT_PURPOSE
#: 输出上限（暂定值，ADR-068 待决 1）：约 800～1000 个汉字的回答，覆盖分点讲解；超出即 O6 截断。
ANSWER_MAX_OUTPUT_TOKENS: Final = 1024
#: 供应商超时时，剩余链路时间不超过此值才算链路时限到期（两套单调时钟的读数误差）。
TIMEOUT_SLACK_SECONDS: Final = 0.25
#: 没有图谱结构上下文时的占位行，避免提示里出现空段。
EMPTY_GRAPH_CONTEXT: Final = "（无）"

# 资料、结构与问题里能伪造分段、块头或哨兵的开头：<< 后（可有空白）接这些词。全角 ＜ 一并处理。
_FORGEABLE: Final = re.compile(r"[<＜]{2}(?=\s*(?:资料|课程资料|知识点结构|学生问题|INSUFFICIENT_EVIDENCE))")
_NEUTRAL: Final = "«"


class GenerationErrorKind(StrEnum):
    """生成故障的闭集（Q5 O7～O13）。"""

    UPSTREAM = "upstream"
    STREAM_INTERRUPTED = "stream_interrupted"
    TIMEOUT = "timeout"
    AUTH = "auth"
    BUDGET_EXCEEDED = "budget_exceeded"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    INTERNAL = "internal"


_LLM_UNAVAILABLE_KINDS: Final = frozenset({
    GenerationErrorKind.UPSTREAM,
    GenerationErrorKind.STREAM_INTERRUPTED,
    GenerationErrorKind.TIMEOUT,
    GenerationErrorKind.AUTH,
})
_CODES: Final = {
    GenerationErrorKind.BUDGET_EXCEEDED: "BUDGET_EXCEEDED",
    GenerationErrorKind.STORAGE_UNAVAILABLE: "STORAGE_UNAVAILABLE",
    GenerationErrorKind.INTERNAL: "INTERNAL_ERROR",
}


class GenerationError(Exception):
    """生成失败。``code`` 与 ``details_reason`` 直接对应契约 ``Error``；信息不含任何正文。"""

    def __init__(self, kind: GenerationErrorKind, *, delivered: bool) -> None:
        self.kind = kind
        self.delivered = delivered
        super().__init__(f"answer generation failed: {kind.value} (delivered={delivered})")

    @property
    def code(self) -> str:
        return "LLM_UNAVAILABLE" if self.kind in _LLM_UNAVAILABLE_KINDS else _CODES[self.kind]

    @property
    def details_reason(self) -> str | None:
        """问答 ``LLM_UNAVAILABLE`` 的 ``details.reason``；其他错误码没有。"""
        return self.kind.value if self.kind in _LLM_UNAVAILABLE_KINDS else None

    @property
    def is_timeout(self) -> bool:
        return self.kind is GenerationErrorKind.TIMEOUT


@dataclass(frozen=True)
class SkippedGeneration:
    """P5 拒答：没有调用生成模型（Q5 O1、O2）。"""

    reason: ContextReason
    model_called: bool = False


@dataclass(frozen=True)
class GenerationResult:
    """一次正常结束的生成。``text`` 为全部产出片段的逐字拼接（未经 J06 校验）。"""

    text: str = field(repr=False)
    finish_reason: FinishReason
    model_responded: str | None

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


def neutralize(text: str) -> str:
    """把能伪造提示分段、块头或哨兵的 ``<<`` 换成 ``«``；长度不增加，其余字符原样保留。"""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return _FORGEABLE.sub(_NEUTRAL, text)


def _block(chunk: EvidenceChunk) -> str:
    return f"<<资料 {chunk.index}>>（{chunk.locator}）\n{neutralize(chunk.text)}"


def render_evidence_blocks(context: EvidenceContext) -> str:
    """编号资料段：块头 ``<<资料 n>>（定位）``，n 与 J04 编号相同，块间空一行。"""
    return "\n\n".join(_block(chunk) for chunk in context.chunks)


def _is_seconds(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value)


class AnswerGeneration:
    """一次生成的流：迭代得到非空文本片段；首次迭代才发请求。只能迭代一次。"""

    def __init__(self, open_stream: Callable[[], Generator[StreamEvent, None, None]],
                 remaining: Callable[[], float]) -> None:
        self._open_stream = open_stream
        self._remaining = remaining
        self._inner: Generator[StreamEvent, None, None] | None = None
        self._started = False
        self._closed = False
        self._parts: list[str] = []
        self.delivered = False
        self.result: GenerationResult | None = None

    def __repr__(self) -> str:
        return f"AnswerGeneration(started={self._started}, delivered={self.delivered}, done={self.result is not None})"

    def __iter__(self) -> Iterator[str]:
        if self._started:
            raise RuntimeError("AnswerGeneration can be iterated only once")
        self._started = True
        return self._run()

    def close(self) -> None:
        """停止生成并关闭供应商流（J06 识别到哨兵、J07 客户端断开）。可重复调用。"""
        self._closed = True
        if self._inner is not None:
            self._inner.close()

    def _fail(self, kind: GenerationErrorKind) -> GenerationError:
        return GenerationError(kind, delivered=self.delivered)

    def _classify(self, error: BaseException) -> GenerationErrorKind:
        if isinstance(error, CallDeadlineExceededError):
            return GenerationErrorKind.TIMEOUT
        if isinstance(error, BudgetExceededError):
            return GenerationErrorKind.BUDGET_EXCEEDED
        if isinstance(error, CallRecordError):
            return GenerationErrorKind.STORAGE_UNAVAILABLE
        if isinstance(error, ModelUnavailableError):
            return GenerationErrorKind.STREAM_INTERRUPTED if self.delivered else GenerationErrorKind.UPSTREAM
        if isinstance(error, ModelCallError):
            if error.error_class is ErrorClass.AUTH:
                return GenerationErrorKind.AUTH
            if error.error_class is ErrorClass.INVALID_REQUEST:
                return GenerationErrorKind.INTERNAL
            if (error.error_class is ErrorClass.TIMEOUT and error.status_code is None
                    and self._remaining() <= TIMEOUT_SLACK_SECONDS):
                return GenerationErrorKind.TIMEOUT
            return GenerationErrorKind.STREAM_INTERRUPTED if self.delivered else GenerationErrorKind.UPSTREAM
        logger.warning("answer generation failed unexpectedly (%s)", type(error).__name__)
        return GenerationErrorKind.INTERNAL

    def _run(self) -> Generator[str, None, None]:
        if self._closed:
            return
        try:
            self._inner = self._open_stream()
            for event in self._inner:
                if isinstance(event, StreamDone):
                    result: ModelResult = event.result
                    self.result = GenerationResult("".join(self._parts), result.finish_reason,
                                                   result.model_responded)
                    return
                if isinstance(event, StreamDelta) and event.text:
                    self._parts.append(event.text)
                    self.delivered = True
                    yield event.text
                    if self._closed:
                        return
                    if self._remaining() <= 0:
                        # 链路到期：不再读取，关闭供应商流；已生成部分不成为答案（O9）。
                        self._inner.close()
                        raise self._fail(GenerationErrorKind.TIMEOUT)
            raise self._fail(GenerationErrorKind.STREAM_INTERRUPTED if self.delivered
                             else GenerationErrorKind.UPSTREAM)
        except GenerationError:
            raise
        except GeneratorExit:
            raise
        except Exception as error:
            raise self._fail(self._classify(error)) from None
        finally:
            if self._inner is not None:
                self._inner.close()


class AnswerGenerator:
    """有证据问答生成服务。每个进程一个实例，与 J03 共用同一个 ``ModelCallPolicy``。

    ``deadline`` 与 ``clock`` 同一时间轴（默认 ``time.monotonic``，须与策略时钟一致），取「收到请求时刻 +
    ``LLM_CHAT_TIMEOUT_SECONDS``」。``model`` 取 ``LLM_CHAT_MODEL``。
    """

    def __init__(
        self,
        policy: ModelCallPolicy,
        *,
        model: str,
        user_id: str | None = None,
        prompts: PromptLibrary | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_output_tokens: int = ANSWER_MAX_OUTPUT_TOKENS,
    ) -> None:
        if not isinstance(policy, ModelCallPolicy):
            raise TypeError("policy must be a ModelCallPolicy")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if type(max_output_tokens) is not int or max_output_tokens < 1:
            raise ValueError("max_output_tokens must be an int >= 1")
        self._policy = policy
        self._model = model
        #: personal 模式：本实例只服务这一个用户，调用记录与日预算归属于他（ADR-080）
        self._user_id = user_id
        self._clock = clock
        self._max_output_tokens = max_output_tokens
        # 装配时就取模板：缺文件或版本不符应在启动时暴露。
        self._template = (prompts if prompts is not None else PromptLibrary()).get(
            ANSWER_PROMPT_PURPOSE, ANSWER_PROMPT_VERSION
        )

    def render_prompt(self, question: str, context: EvidenceContext) -> str:
        """生成提示正文（J06/K03 复核与评测用）；只含结构上下文、编号资料与问题。"""
        graph = neutralize(context.graph.text.strip()) or EMPTY_GRAPH_CONTEXT
        return self._template.render({
            "graph_context": graph,
            "context": render_evidence_blocks(context),
            "question": neutralize(question.strip()),
        }).text

    def generate(
        self,
        question: str,
        context: EvidenceContext,
        *,
        course_id: str,
        request_id: str,
        deadline: float,
    ) -> AnswerGeneration | SkippedGeneration:
        """闸门关闭时返回 ``SkippedGeneration``（不调用模型）；否则返回尚未发请求的 ``AnswerGeneration``。"""
        if not isinstance(question, str):
            raise TypeError("question must be str")
        if not isinstance(context, EvidenceContext):
            raise TypeError("context must be an EvidenceContext")
        for name, value in (("course_id", course_id), ("request_id", request_id)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not _is_seconds(deadline):
            raise ValueError("deadline must be a finite number")
        if not context.covered or not context.chunks:
            return SkippedGeneration(context.reason or ContextReason.NO_RETRIEVAL_HIT)
        if not question.strip():
            raise ValueError("question must not be blank")

        request = ModelRequest(
            purpose=ANSWER_CALL_PURPOSE,
            model=self._model,
            messages=(Message("user", self.render_prompt(question, context)),),
            max_output_tokens=self._max_output_tokens,
            response_format="text",
        )
        client = self._policy.bind(CallAttribution(course_id=course_id, request_id=request_id,
                                                         user_id=self._user_id), deadline=deadline)
        return AnswerGeneration(lambda: client.stream(request), lambda: deadline - self._clock())
