"""C02-2 方案 A（ADR-089）：模型推理用量埋点。

只计量、不保存内容：兼容客户端把流里的 ``reasoning_content`` / ``reasoning`` 只按字数上报，
推理正文不进入回答文本；用量解析 ``completion_tokens_details.reasoning_tokens``。调用策略层记录首次推理与
首次可见内容相对调用开始的毫秒数，并且不把内部推理事件转发给调用方（回答行为与 SSE 契约不变）。
供应商不提供时一律为空，不当作 0。
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from dataclasses import fields
from typing import Any

from app.repositories.model_calls import SqliteCallStore
from app.repositories.sqlite import migrate
from app.services.ai.client import (
    Message,
    ModelRequest,
    ModelCallError,
    ModelMalformedResponseError,
    ModelStreamInterruptedError,
    ModelResult,
    StreamDelta,
    StreamDone,
    StreamReasoning,
    Usage,
)
from app.services.ai.policy import CallAttribution, ModelCallPolicy
from test_e03 import MODEL, SSE_HEADERS, ScriptedResponse, ScriptedTransport, make_client, make_request, sse

REASONING_TEXT = "先回忆栈的定义，再比较队列……"


def _chunk(*, content: str | None = None, reasoning: str | None = None, key: str = "reasoning_content",
           finish_reason: str | None = None) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if reasoning is not None:
        delta[key] = reasoning
    if content is not None:
        delta["content"] = content
    return {"id": "c", "object": "chat.completion.chunk", "model": MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}], "usage": None}


def _usage_chunk(details: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {"prompt_tokens": 30, "completion_tokens": 950, "total_tokens": 980}
    if details is not ...:
        usage["completion_tokens_details"] = details
    return {"id": "c", "object": "chat.completion.chunk", "model": MODEL, "choices": [], "usage": usage}


def _stream(*chunks: Any) -> list[Any]:
    transport = ScriptedTransport(ScriptedResponse(200, sse(*chunks, "[DONE]"), headers=SSE_HEADERS))
    return list(make_client(transport).stream(make_request()))


# ---------------------------------------------------------------- 兼容客户端


def test_stream_reports_reasoning_by_length_only_and_keeps_it_out_of_the_answer():
    events = _stream(_chunk(reasoning=REASONING_TEXT[:6]), _chunk(reasoning=REASONING_TEXT[6:]),
                     _chunk(content="栈后进先出"), _chunk(content="[1]。", finish_reason="stop"),
                     _usage_chunk({"reasoning_tokens": 900}))
    reasoning = [e for e in events if isinstance(e, StreamReasoning)]
    assert [e.chars for e in reasoning] == [6, len(REASONING_TEXT) - 6]
    assert [f.name for f in fields(StreamReasoning)] == ["chars"]          # 事件里没有正文
    assert [e.text for e in events if isinstance(e, StreamDelta)] == ["栈后进先出", "[1]。"]
    done = events[-1]
    assert isinstance(done, StreamDone)
    assert done.result.text == "栈后进先出[1]。"
    assert done.result.reasoning_chars == len(REASONING_TEXT)
    assert done.result.usage == Usage(30, 950, reasoning_tokens=900)
    assert REASONING_TEXT not in repr(events)


def test_stream_accepts_the_reasoning_alias_field():
    events = _stream(_chunk(reasoning="想一想", key="reasoning"), _chunk(content="答[1]。", finish_reason="stop"),
                     _usage_chunk(...))
    assert [e.chars for e in events if isinstance(e, StreamReasoning)] == [3]
    assert events[-1].result.usage == Usage(30, 950)
    assert events[-1].result.usage.reasoning_tokens is None


def test_stream_without_reasoning_leaves_reasoning_unknown_not_zero():
    events = _stream(_chunk(content="答[1]。", finish_reason="stop"), _usage_chunk(...))
    assert not any(isinstance(e, StreamReasoning) for e in events)
    assert events[-1].result.reasoning_chars is None


def test_invalid_reasoning_tokens_are_ignored_without_dropping_usage():
    for bad in ({"reasoning_tokens": -1}, {"reasoning_tokens": True}, {"reasoning_tokens": "9"}, "x", None):
        events = _stream(_chunk(content="答[1]。", finish_reason="stop"), _usage_chunk(bad))
        assert events[-1].result.usage == Usage(30, 950)


def test_complete_counts_reasoning_and_excludes_it_from_text():
    body = {"id": "c", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "{}", "reasoning_content": REASONING_TEXT}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 40,
                      "completion_tokens_details": {"reasoning_tokens": 35}}}
    transport = ScriptedTransport(ScriptedResponse(200, json.dumps(body, ensure_ascii=False).encode()))
    result = make_client(transport).complete(make_request())
    assert result.text == "{}"
    assert result.reasoning_chars == len(REASONING_TEXT)
    assert result.usage == Usage(10, 40, reasoning_tokens=35)


# ---------------------------------------------------------------- 调用策略：计时、回写、不转发


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _ReasoningClient:
    """先推理后作答的替身：每个事件前推进时钟，复现「首个可见 delta 在生成末尾」的形态。"""

    def __init__(self, clock: _Clock, script: list[tuple[float, Any]], result: ModelResult) -> None:
        self.clock, self.script, self.result = clock, script, result

    def complete(self, request: ModelRequest) -> ModelResult:
        self.clock.now += 2.0
        return self.result

    def stream(self, request: ModelRequest):
        for delay, event in self.script:
            self.clock.now += delay
            yield event
        yield StreamDone(self.result)


def _policy(tmp_path, client, clock) -> tuple[ModelCallPolicy, str]:
    url = f"sqlite:///{tmp_path / 'c02.sqlite3'}"
    migrate(url)
    policy = ModelCallPolicy(primary=client, store=SqliteCallStore(url), clock=clock, sleep=lambda s: None,
                             random=lambda: 1.0, max_retries=0, failure_threshold=5, open_seconds=30,
                             task_token_budget=1_000_000, daily_token_budget=10_000_000)
    return policy, url


def _row(url: str) -> dict[str, Any]:
    with sqlite3.connect(url.removeprefix("sqlite:///")) as db:
        db.row_factory = sqlite3.Row
        (row,) = [dict(r) for r in db.execute("SELECT * FROM model_calls")]
    return row


def _request() -> ModelRequest:
    return ModelRequest(purpose="answer_with_context", model=MODEL, messages=(Message("user", "什么是栈"),),
                        max_output_tokens=2048)


def _bound(policy):
    return policy.bind(CallAttribution(course_id="c1", request_id="req-1"))


def test_policy_records_reasoning_timing_and_does_not_forward_reasoning_events(tmp_path):
    clock = _Clock()
    result = ModelResult(text="栈后进先出[1]。", model_requested=MODEL, model_responded=MODEL,
                         usage=Usage(2000, 900, reasoning_tokens=700), finish_reason="stop", reasoning_chars=15)
    client = _ReasoningClient(clock, [(1.0, StreamReasoning(10)), (1.5, StreamReasoning(5)),
                                      (1.0, StreamDelta("栈后进先出")), (0.2, StreamDelta("[1]。"))], result)
    policy, url = _policy(tmp_path, client, clock)
    events = list(_bound(policy).stream(_request()))
    assert not any(isinstance(e, StreamReasoning) for e in events)
    assert [type(e) for e in events] == [StreamDelta, StreamDelta, StreamDone]
    row = _row(url)
    assert (row["usage_input"], row["usage_output"], row["usage_reasoning"]) == (2000, 900, 700)
    assert row["reasoning_chars"] == 15
    assert (row["first_reasoning_ms"], row["first_content_ms"]) == (1000, 3500)


def test_policy_leaves_reasoning_columns_empty_when_the_model_does_not_reason(tmp_path):
    clock = _Clock()
    result = ModelResult(text="答[1]。", model_requested=MODEL, model_responded=MODEL, usage=Usage(10, 4),
                         finish_reason="stop")
    policy, url = _policy(tmp_path, _ReasoningClient(clock, [(0.3, StreamDelta("答[1]。"))], result), clock)
    list(_bound(policy).stream(_request()))
    row = _row(url)
    assert (row["usage_reasoning"], row["reasoning_chars"], row["first_reasoning_ms"]) == (None, None, None)
    assert row["first_content_ms"] == 300


def test_policy_complete_records_reasoning_usage_without_timing(tmp_path):
    clock = _Clock()
    result = ModelResult(text="{}", model_requested=MODEL, model_responded=MODEL,
                         usage=Usage(10, 40, reasoning_tokens=35), finish_reason="stop", reasoning_chars=12)
    policy, url = _policy(tmp_path, _ReasoningClient(clock, [], result), clock)
    _bound(policy).complete(_request())
    row = _row(url)
    assert (row["usage_reasoning"], row["reasoning_chars"]) == (35, 12)
    assert (row["first_reasoning_ms"], row["first_content_ms"]) == (None, None)


def test_billing_formula_is_unchanged_reasoning_is_part_of_output(tmp_path):
    clock = _Clock()
    result = ModelResult(text="答", model_requested=MODEL, model_responded=MODEL,
                         usage=Usage(100, 900, reasoning_tokens=800), finish_reason="length", reasoning_chars=3)
    policy, url = _policy(tmp_path, _ReasoningClient(clock, [(0.1, StreamDelta("答"))], result), clock)
    list(_bound(policy).stream(_request()))
    with sqlite3.connect(url.removeprefix("sqlite:///")) as db:
        from app.repositories.model_calls import BILLED_TOKENS_SQL
        (billed,) = db.execute(f"SELECT {BILLED_TOKENS_SQL} FROM model_calls").fetchone()
    assert billed == 1000


# ---------------------------------------------------------------- 迁移 017


def test_migration_017_adds_nullable_reasoning_columns(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.sqlite3'}"
    migrate(url)
    with sqlite3.connect(url.removeprefix("sqlite:///")) as db:
        columns = {row[1]: row for row in db.execute("PRAGMA table_info(model_calls)")}
        files = [row[0] for row in db.execute("SELECT filename FROM schema_migrations ORDER BY version")]
    for name in ("usage_reasoning", "reasoning_chars", "first_reasoning_ms", "first_content_ms"):
        assert name in columns and columns[name][3] == 0          # 可空
    assert files.count("017_model_call_reasoning.sql") == 1
    assert migrate(url) == []  # 后续迁移不影响 017 的一次性应用与可空语义


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
@pytest.mark.parametrize("usage", [Usage(10, 100, reasoning_tokens=90), Usage(10, 100, reasoning_tokens=0),
                                   Usage(10, 100), None], ids=["known", "zero", "unknown-reasoning", "no-usage"])
def test_failed_calls_preserve_reasoning_usage_without_double_billing(tmp_path, streaming, usage):
    clock = _Clock()
    error_type = ModelStreamInterruptedError if streaming else ModelMalformedResponseError

    class FailingClient:
        def complete(self, request):
            clock.now += 2.0
            raise error_type(MODEL, usage=usage)

        def stream(self, request):
            clock.now += 1.0
            yield StreamReasoning(len(REASONING_TEXT))
            clock.now += 0.5
            yield StreamDelta("答[1]。")
            clock.now += 0.5
            raise error_type(MODEL, usage=usage)

    policy, url = _policy(tmp_path, FailingClient(), clock)
    events = []
    with pytest.raises(ModelCallError):
        if streaming:
            for event in _bound(policy).stream(_request()):
                events.append(event)
        else:
            _bound(policy).complete(_request())
    row = _row(url)  # also asserts exactly one call: no retry introduced
    assert row["status"] == "error"
    assert (row["usage_input"], row["usage_output"]) == ((10, 100) if usage else (None, None))
    assert row["usage_reasoning"] == (usage.reasoning_tokens if usage else None)
    assert not any(isinstance(event, StreamReasoning) for event in events)
    assert REASONING_TEXT not in repr(events)
    if streaming:
        assert row["reasoning_chars"] == len(REASONING_TEXT)
        assert (row["first_reasoning_ms"], row["first_content_ms"]) == (1000, 1500)
    else:
        assert (row["reasoning_chars"], row["first_reasoning_ms"], row["first_content_ms"]) == (None, None, None)
    with sqlite3.connect(url.removeprefix("sqlite:///")) as db:
        from app.repositories.model_calls import BILLED_TOKENS_SQL
        (billed,) = db.execute(f"SELECT {BILLED_TOKENS_SQL} FROM model_calls").fetchone()
    assert billed == (110 if usage else row["input_tokens_est"] + row["max_output_tokens"])
