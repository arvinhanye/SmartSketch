"""J03：多轮问题改写——有限历史 + 当前问题 → 检索用问题；任何故障都退回原问题（P3「不失败」）。

依据：``specs/grounded-qa.md`` Q2 P3、Q8 H1～H3、Q11 J03 行、QA-19、主验收边界第 7 条；
``docs/integrations.md``「模型接入规则（A07）」（预算被拒与超出剩余时间均按本任务降级、
``LLM_CHAT_TIMEOUT_SECONDS`` 为整条问答链路的时限、调用记录）；ADR-011 修订 2；ADR-015 决定 6。

流程：

1. **历史校验**：每个回合只接受 ``user`` / ``assistant`` 两种角色（契约 ``ChatTurn.role`` 是闭集，
   P1 已按 422 拒绝其他角色）。本模块对 ``system``、``tool`` 等其他角色同样**拒绝**（``ValueError``，
   在任何模型调用之前），不静默剔除：越过 P1 到达这里说明装配有缺陷，应当暴露而不是悄悄改变对话。
   错误信息不回显回合内容。
2. **历史清洗**：助手回合剔除全部类标记（规格 Q1 定义：``[…]``、``【…】``、``［…］`` 内只含数字、
   空白、``,，、``、``-–~``，至少一个数字、总长 ≤ 32）与哨兵 ``<<INSUFFICIENT_EVIDENCE>>``，反复剔除
   直到不再出现（防止嵌套拼出新标记）。与 J06 不同，这里**不区分代码片段**：历史只供改写，丢掉代码里的
   ``a[1]`` 代价很小，且避免再写一份须与 J06/J09 保持一致的代码片段判定。学生回合保持原话（H2 只要求
   助手回合）。每次发言的空白（含换行）压成单个空格，防止在历史里伪造「学生：/助教：」行。清洗后为空的
   回合丢弃。
3. **历史裁剪**：单回合超过 ``MAX_TURN_CHARS`` 保留开头并以「…」结尾；只看最近 ``MAX_HISTORY_TURNS``
   个回合，再从最新往前累加，总字符超过 ``MAX_HISTORY_CHARS`` 即停（保留连续的最近一段）。
4. **跳过调用**（不计费，退回原问题）：问题为空白、清洗后无历史、问题超过 ``MAX_QUESTION_CHARS``、
   链路剩余时间扣除留给检索与生成的 ``reserve_seconds`` 后不足 ``min_seconds``。
5. **调用**：渲染 ``rewrite_query@REWRITE_PROMPT_VERSION``，单条 user 消息、文本格式、声明输出上限，
   单次超时取 ``min(timeout_seconds, 剩余时间 - reserve_seconds)``；经 E04 ``ModelCallPolicy`` 以
   ``CallAttribution(course_id, request_id)`` 绑定后调用——``task_id`` 为空，``model_calls`` 记录带
   ``request_id``，``purpose = "rewrite_query"``。绑定时传入截止时间「链路截止 - ``reserve_seconds``」
   （E04 截止时间，``docs/integrations.md``「问答链路截止时间」），E04 的重试与退避因此也不会
   挤占留给检索与生成的时间。
6. **降级**：预算拒绝、预写失败、熔断、超时（含 E04 因截止时间终止）、其他供应商错误、未预期异常，以及输出为空、多行、过长
   （含 ``finish_reason = length``）、含哨兵/控制字符/问题中没有的类标记，都返回原问题并给出闭集原因
   ``RewriteReason``；模型原样返回问题（无需改写或无法补全指代）记为 ``unchanged``，指代词随原问题保留。

本模块只在未预期异常时记一条 WARNING（只含异常类型名）；问题、历史与模型输出不进入日志或 ``repr``。
"""

from __future__ import annotations

import logging
import math
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Final, Literal

from app.services.ai.client import ErrorClass, Message, ModelCallError, ModelRequest, ModelResult
from app.services.ai.policy import (
    BudgetExceededError,
    CallAttribution,
    CallDeadlineExceededError,
    CallRecordError,
    ModelCallPolicy,
    ModelUnavailableError,
)
from app.services.ai.prompts import PromptLibrary

__all__ = [
    "HISTORY_ROLES",
    "INSUFFICIENT_EVIDENCE_SENTINEL",
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_TURNS",
    "MAX_QUESTION_CHARS",
    "MAX_TURN_CHARS",
    "REWRITE_CALL_PURPOSE",
    "REWRITE_MAX_CHARS",
    "REWRITE_MAX_OUTPUT_TOKENS",
    "REWRITE_MIN_SECONDS",
    "REWRITE_PROMPT_PURPOSE",
    "REWRITE_PROMPT_VERSION",
    "REWRITE_RESERVE_SECONDS",
    "REWRITE_TIMEOUT_SECONDS",
    "HistoryTurn",
    "QueryRewrite",
    "QueryRewriter",
    "RewriteReason",
    "prepare_history",
    "strip_citation_markers",
]

logger = logging.getLogger(__name__)

#: 提示词用途与本模块固定使用的版本；改模板须同时升此版本与 ``prompts/MANIFEST.md``。
REWRITE_PROMPT_PURPOSE: Final = "rewrite_query"
REWRITE_PROMPT_VERSION: Final = 2
#: ``ModelRequest.purpose`` / ``model_calls.purpose``：沿用 E05 先例取提示词用途名（E03 用途枚举待定）。
REWRITE_CALL_PURPOSE: Final = REWRITE_PROMPT_PURPOSE

# ---- 暂定值（规格「多轮对话保留轮数」待细化；理由见 docs/handoffs/claude-j03.md 待决 1）----
#: 最多看最近 6 个回合（约 3 轮问答）：指代几乎总指向最近一两轮，更早的内容增加费用与跑题风险。
MAX_HISTORY_TURNS: Final = 6
#: 历史总字符上限（清洗后计）：约 2k token 以内，改写调用的输入成本与延迟可控。
MAX_HISTORY_CHARS: Final = 2000
#: 单回合字符上限：长回答保留开头（主题通常在开头给出），截断处以「…」结尾。
MAX_TURN_CHARS: Final = 800
#: 超过此长度的问题不改写：长问题通常已自足，且改写结果容易超出输出上限。
MAX_QUESTION_CHARS: Final = 200
#: 改写结果的字符上限与声明的输出 token 上限。
REWRITE_MAX_CHARS: Final = 300
REWRITE_MAX_OUTPUT_TOKENS: Final = 300
#: 改写调用的单次超时上限、为检索与生成保留的链路时间、值得发起一次调用的最短时间（秒）。
REWRITE_TIMEOUT_SECONDS: Final = 3.0
REWRITE_RESERVE_SECONDS: Final = 8.0
REWRITE_MIN_SECONDS: Final = 0.5

#: 规格 Q1「哨兵」。
INSUFFICIENT_EVIDENCE_SENTINEL: Final = "<<INSUFFICIENT_EVIDENCE>>"
HISTORY_ROLES: Final = frozenset({"user", "assistant"})

_ROLE_LABELS: Final = {"user": "学生", "assistant": "助教"}
_TRUNCATION_MARK: Final = "…"
_MARKER_MAX_CHARS: Final = 32
# 规格 Q1「类标记」：括号内只含数字（半角/全角）、空白（不含换行）、分隔符与区间符，至少一个数字。
_MARKER_CHAR = r"[0-9０-９,，、\-–~ \t　 ]"
_MARKER_BODY = rf"{_MARKER_CHAR}*[0-9０-９]{_MARKER_CHAR}*"
_CLASS_MARKER: Final = re.compile(rf"\[{_MARKER_BODY}\]|【{_MARKER_BODY}】|［{_MARKER_BODY}］")
_QUOTE_PAIRS: Final = (("“", "”"), ('"', '"'), ("「", "」"), ("『", "』"), ("‘", "’"), ("'", "'"))


class RewriteReason(StrEnum):
    """使用原问题的原因（闭集，供 J04/J05/J10 记录）。``None`` 表示已改写。"""

    NO_HISTORY = "no_history"  # 无历史或清洗后为空：无需改写，不调用模型
    BLANK_QUESTION = "blank_question"  # 问题只有空白，不调用模型
    QUESTION_TOO_LONG = "question_too_long"  # 超过 MAX_QUESTION_CHARS，不调用模型
    NO_TIME = "no_time"  # 链路剩余时间不足，不调用模型
    BUDGET_EXCEEDED = "budget_exceeded"  # E04 预算拒绝（未发请求）
    TIMEOUT = "timeout"  # 供应商超时（含 L1 重试后仍超时）
    MODEL_ERROR = "model_error"  # 其他供应商错误或主备均熔断
    CALL_RECORD_FAILED = "call_record_failed"  # model_calls 预写失败（未发请求）
    UNEXPECTED_ERROR = "unexpected_error"  # 未预期异常
    EMPTY_OUTPUT = "empty_output"
    MULTILINE_OUTPUT = "multiline_output"
    OUTPUT_TOO_LONG = "output_too_long"  # 超过 REWRITE_MAX_CHARS 或被输出上限截断
    INVALID_OUTPUT = "invalid_output"  # 含哨兵、控制字符或问题中没有的类标记
    UNCHANGED = "unchanged"  # 模型原样返回问题：无需改写或指代无法补全


@dataclass(frozen=True)
class HistoryTurn:
    """一次发言。构造即校验角色闭集（``user`` / ``assistant``）。"""

    role: Literal["user", "assistant"]
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or self.role not in HISTORY_ROLES:
            raise ValueError("history turn role must be 'user' or 'assistant'")
        if not isinstance(self.content, str):
            raise ValueError("history turn content must be str")


@dataclass(frozen=True)
class QueryRewrite:
    """改写结果。``query`` 交给检索；``rewritten`` 为假时 ``query`` 与 ``original`` 逐字相同。"""

    query: str = field(repr=False)
    original: str = field(repr=False)
    rewritten: bool
    reason: RewriteReason | None
    #: 是否经调用策略发起了改写调用（含被预算或预写拒绝、未真正发出的情形）。
    model_called: bool
    #: 送入模型（或本应送入）的历史回合数，清洗与裁剪之后。
    history_turns: int

    def __post_init__(self) -> None:
        if self.rewritten != (self.reason is None):
            raise ValueError("QueryRewrite: rewritten must be True exactly when reason is None")
        if not self.rewritten and self.query != self.original:
            raise ValueError("QueryRewrite: a fallback must return the original question")

    @property
    def used_original(self) -> bool:
        return not self.rewritten


# ---------------------------------------------------------------- 历史清洗与裁剪


def strip_citation_markers(text: str) -> str:
    """剔除类标记（总长 ≤ 32）与哨兵，反复进行直到不再变化；其余字符（含空白）不动。"""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    while True:
        cleaned = _CLASS_MARKER.sub(
            lambda match: "" if len(match.group()) <= _MARKER_MAX_CHARS else match.group(), text
        ).replace(INSUFFICIENT_EVIDENCE_SENTINEL, "")
        if cleaned == text:
            return cleaned
        text = cleaned


def _one_line(text: str) -> str:
    """去掉控制字符，所有空白（含换行）压成单个空格，去首尾空白。"""
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in text)
    return " ".join(text.split())


def _clean_assistant(text: str) -> str:
    # 压空白可能让超长的类标记变短而成立，因此与剔除交替进行直到稳定。
    while True:
        cleaned = _one_line(strip_citation_markers(text))
        if cleaned == text:
            return cleaned
        text = cleaned


def _coerce(turn: object) -> HistoryTurn:
    if isinstance(turn, HistoryTurn):
        return turn
    if isinstance(turn, Mapping):
        if "role" not in turn or "content" not in turn:
            raise ValueError("history turn needs role and content")
        role, content = turn["role"], turn["content"]
    elif not isinstance(turn, str | bytes) and hasattr(turn, "role") and hasattr(turn, "content"):
        role, content = turn.role, turn.content  # 例如生成的契约模型 ChatTurn（role 为 Enum）
    else:
        raise TypeError("history turn must be a mapping or an object with role and content")
    if isinstance(role, Enum):
        role = role.value
    return HistoryTurn(role, content)


def prepare_history(history: Iterable[object] | None) -> tuple[HistoryTurn, ...]:
    """校验、清洗并裁剪历史，返回按时间先后排列的回合（可能为空）。"""
    if history is None:
        return ()
    if isinstance(history, str | bytes | Mapping) or not isinstance(history, Iterable):
        raise TypeError("history must be a sequence of turns")
    turns = [_coerce(turn) for turn in history]  # 先整体校验：任何一个回合不合规都拒绝
    cleaned: list[HistoryTurn] = []
    for turn in turns:
        content = _clean_assistant(turn.content) if turn.role == "assistant" else _one_line(turn.content)
        if not content:
            continue
        if len(content) > MAX_TURN_CHARS:
            content = content[: MAX_TURN_CHARS - len(_TRUNCATION_MARK)].rstrip() + _TRUNCATION_MARK
        cleaned.append(HistoryTurn(turn.role, content))
    kept: list[HistoryTurn] = []
    total = 0
    for turn in reversed(cleaned[-MAX_HISTORY_TURNS:]):
        if total + len(turn.content) > MAX_HISTORY_CHARS:
            break
        kept.append(turn)
        total += len(turn.content)
    kept.reverse()
    return tuple(kept)


def _render_history(turns: tuple[HistoryTurn, ...]) -> str:
    return "\n".join(f"{_ROLE_LABELS[turn.role]}：{turn.content}" for turn in turns)


# ---------------------------------------------------------------- 输出检查


def _unquote(text: str) -> str:
    for left, right in _QUOTE_PAIRS:
        if len(text) >= 2 and text.startswith(left) and text.endswith(right):
            return text[len(left) : -len(right)].strip()
    return text


def _markers(text: str) -> set[str]:
    return {marker for marker in _CLASS_MARKER.findall(text) if len(marker) <= _MARKER_MAX_CHARS}


def _check_output(result: ModelResult, question: str) -> tuple[str, RewriteReason | None]:
    if result.finish_reason == "length":
        return "", RewriteReason.OUTPUT_TOO_LONG
    text = _unquote(result.text.strip())
    if not text:
        return "", RewriteReason.EMPTY_OUTPUT
    if len(text.splitlines()) > 1:
        return "", RewriteReason.MULTILINE_OUTPUT
    if len(text) > REWRITE_MAX_CHARS:
        return "", RewriteReason.OUTPUT_TOO_LONG
    if (
        INSUFFICIENT_EVIDENCE_SENTINEL in text
        or any(unicodedata.category(ch) == "Cc" and ch != "\t" for ch in text)
        or not _markers(text) <= _markers(question)
    ):
        return "", RewriteReason.INVALID_OUTPUT
    if _one_line(text) == question:
        return "", RewriteReason.UNCHANGED
    return text, None


# ---------------------------------------------------------------- 服务


def _is_seconds(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value)


class QueryRewriter:
    """多轮问题改写服务。每个进程一个实例，与 J05 共用同一个 ``ModelCallPolicy``。

    ``deadline`` 与 ``clock`` 同一时间轴（默认 ``time.monotonic``），取「收到请求时刻 +
    ``LLM_CHAT_TIMEOUT_SECONDS``」，即整条问答链路的截止时刻。``model`` 取 ``LLM_CHAT_MODEL``。
    """

    def __init__(
        self,
        policy: ModelCallPolicy,
        *,
        model: str,
        prompts: PromptLibrary | None = None,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = REWRITE_TIMEOUT_SECONDS,
        reserve_seconds: float = REWRITE_RESERVE_SECONDS,
        min_seconds: float = REWRITE_MIN_SECONDS,
    ) -> None:
        if not isinstance(policy, ModelCallPolicy):
            raise TypeError("policy must be a ModelCallPolicy")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not _is_seconds(min_seconds) or min_seconds <= 0:
            raise ValueError("min_seconds must be a finite number > 0")
        if not _is_seconds(timeout_seconds) or timeout_seconds < min_seconds:
            raise ValueError("timeout_seconds must be a finite number >= min_seconds")
        if not _is_seconds(reserve_seconds) or reserve_seconds < 0:
            raise ValueError("reserve_seconds must be a finite number >= 0")
        self._policy = policy
        self._model = model
        self._clock = clock
        self._timeout_seconds = float(timeout_seconds)
        self._reserve_seconds = float(reserve_seconds)
        self._min_seconds = float(min_seconds)
        # 装配时就取模板：缺文件或版本不符应在启动时暴露，而不是每个请求静默降级。
        self._template = (prompts if prompts is not None else PromptLibrary()).get(
            REWRITE_PROMPT_PURPOSE, REWRITE_PROMPT_VERSION
        )

    def rewrite(
        self,
        question: str,
        history: Iterable[object] | None,
        *,
        course_id: str,
        request_id: str,
        deadline: float,
    ) -> QueryRewrite:
        if not isinstance(question, str):
            raise TypeError("question must be str")
        for name, value in (("course_id", course_id), ("request_id", request_id)):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not _is_seconds(deadline):
            raise ValueError("deadline must be a finite number")
        turns = prepare_history(history)

        def fallback(reason: RewriteReason, called: bool) -> QueryRewrite:
            return QueryRewrite(query=question, original=question, rewritten=False, reason=reason,
                                model_called=called, history_turns=len(turns))

        flat_question = _one_line(question)
        if not flat_question:
            return fallback(RewriteReason.BLANK_QUESTION, False)
        if not turns:
            return fallback(RewriteReason.NO_HISTORY, False)
        if len(flat_question) > MAX_QUESTION_CHARS:
            return fallback(RewriteReason.QUESTION_TOO_LONG, False)
        seconds = min(self._timeout_seconds, deadline - self._clock() - self._reserve_seconds)
        if seconds < self._min_seconds:
            return fallback(RewriteReason.NO_TIME, False)

        rendered = self._template.render({"history": _render_history(turns), "question": flat_question})
        request = ModelRequest(
            purpose=REWRITE_CALL_PURPOSE,
            model=self._model,
            messages=(Message("user", rendered.text),),
            max_output_tokens=REWRITE_MAX_OUTPUT_TOKENS,
            response_format="text",
            timeout_seconds=seconds,
        )
        client = self._policy.bind(CallAttribution(course_id=course_id, request_id=request_id),
                                   deadline=deadline - self._reserve_seconds)
        try:
            result = client.complete(request)
        except CallDeadlineExceededError:
            return fallback(RewriteReason.TIMEOUT, True)
        except BudgetExceededError:
            return fallback(RewriteReason.BUDGET_EXCEEDED, True)
        except CallRecordError:
            return fallback(RewriteReason.CALL_RECORD_FAILED, True)
        except ModelUnavailableError:
            return fallback(RewriteReason.MODEL_ERROR, True)
        except ModelCallError as error:
            timed_out = error.error_class is ErrorClass.TIMEOUT
            return fallback(RewriteReason.TIMEOUT if timed_out else RewriteReason.MODEL_ERROR, True)
        except Exception as error:  # P3 不失败：任何意外都退回原问题
            logger.warning("query rewrite failed unexpectedly (%s); using the original question",
                           type(error).__name__)
            return fallback(RewriteReason.UNEXPECTED_ERROR, True)

        text, reason = _check_output(result, flat_question)
        if reason is not None:
            return fallback(reason, True)
        return QueryRewrite(query=text, original=question, rewritten=True, reason=None,
                            model_called=True, history_turns=len(turns))
