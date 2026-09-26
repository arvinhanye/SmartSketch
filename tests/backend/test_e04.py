"""E04: model call policy — bounded backoff, switching matrix, circuit breaker, budgets and
``model_calls`` bookkeeping around an E02 ``ModelClient``.

Rules come from docs/integrations.md「模型接入规则（A07）」(主备切换矩阵、预算、调用记录),
ADR-011 修订 2/3 and specs/task-processing.md LEASE-17/24～30, specs/grounded-qa.md
QA-28/29 (O12). No test sleeps for real: clock, sleep and jitter are injected.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from app.repositories import model_calls as repo
from app.repositories.model_calls import (
    BudgetRejected,
    CallOutcome,
    CallRecord,
    SqliteCallStore,
    billed_for_day,
    billed_for_task,
    get_call,
)
from app.repositories.sqlite import migrate
from app.services.ai import policy as policy_module
from app.services.ai.client import (
    Message,
    ModelAuthError,
    ModelClient,
    ModelConnectionError,
    ModelInvalidRequestError,
    ModelMalformedResponseError,
    ModelRateLimitedError,
    ModelRequest,
    ModelServerError,
    ModelStreamInterruptedError,
    ModelTimeoutError,
    StreamDelta,
    StreamDone,
    Usage,
)
from app.services.ai.compatible import CompatibleModelClient, estimate_input_tokens
from app.services.ai.fake import FakeModelClient, FakeReply
from app.services.ai.policy import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_BACKOFF_MAX_SECONDS,
    HARD_MAX_BACKOFF_SECONDS,
    BackoffPolicy,
    BudgetExceededError,
    CallAttribution,
    CallDeadlineExceededError,
    CallRecordError,
    CircuitBreaker,
    CircuitState,
    ModelCallPolicy,
    ModelUnavailableError,
    new_call_id,
)

PROMPT = "PROMPT-SECRET-栈与队列的区别"
OUTPUT = "OUTPUT-SECRET-答案正文"
API_KEY = "sk-E04-TEST-KEY-DO-NOT-LOG"
PRIMARY_MODEL = "primary-model"
FALLBACK_MODEL = "fallback-model"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Env:
    def __init__(self, tmp_path, **policy_kwargs: Any) -> None:
        self.url = f"sqlite:///{tmp_path / 'e04.sqlite3'}"
        migrate(self.url)
        self.clock = Clock()
        self.sleeps: list[float] = []
        self.primary = FakeModelClient()
        self.fallback = FakeModelClient() if policy_kwargs.pop("with_fallback", False) else None
        self.store = policy_kwargs.pop("store", None) or SqliteCallStore(self.url)
        defaults: dict[str, Any] = {
            "max_retries": 2,
            "failure_threshold": 5,
            "open_seconds": 30,
            "task_token_budget": 1_000_000,
            "daily_token_budget": 10_000_000,
        }
        defaults.update(policy_kwargs)
        self.policy = ModelCallPolicy(
            primary=self.primary,
            fallback=self.fallback,
            fallback_models={PRIMARY_MODEL: FALLBACK_MODEL} if self.fallback is not None else None,
            store=self.store,
            clock=self.clock,
            sleep=self._sleep,
            random=lambda: 1.0,
            **defaults,
        )

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock.now += seconds

    def client(self, **attribution: Any) -> Any:
        values = {"course_id": "course-1", "task_id": "task-1", "chunk_id": "chunk-1",
                  "task_attempt": 1, "chunk_attempt": 1}
        values.update(attribution)
        return self.policy.bind(CallAttribution(**values))

    def rows(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.url.removeprefix("sqlite:///")) as database:
            database.row_factory = sqlite3.Row
            return [dict(row) for row in database.execute("SELECT * FROM model_calls ORDER BY created_at, call_seq")]


def request(max_output_tokens: int = 100, purpose: str = "extract_entities") -> ModelRequest:
    return ModelRequest(purpose=purpose, model=PRIMARY_MODEL,
                        messages=(Message("user", PROMPT),), max_output_tokens=max_output_tokens)


def estimate(req: ModelRequest) -> int:
    return estimate_input_tokens(req) + req.max_output_tokens


# ---------------------------------------------------------------- backoff (有界)


def test_backoff_defaults_are_bounded_and_documented() -> None:
    assert DEFAULT_BACKOFF_BASE_SECONDS == 1.0
    assert DEFAULT_BACKOFF_MAX_SECONDS == 8.0
    assert HARD_MAX_BACKOFF_SECONDS == 30.0
    backoff = BackoffPolicy()
    delays = [backoff.delay(n, None, 1.0) for n in range(10)]
    assert delays[:4] == [1.0, 2.0, 4.0, 8.0]
    assert max(delays) == 8.0
    assert all(d <= HARD_MAX_BACKOFF_SECONDS for d in delays)
    # Huge retry indices do not overflow.
    assert backoff.delay(10_000, None, 1.0) == 8.0


def test_backoff_jitter_keeps_at_least_half() -> None:
    backoff = BackoffPolicy(base_seconds=2.0, max_seconds=16.0)
    assert backoff.delay(0, None, 0.0) == 1.0
    assert backoff.delay(1, None, 0.5) == 3.0
    assert backoff.delay(3, None, 0.0) == 8.0


def test_retry_after_is_honoured_but_capped() -> None:
    backoff = BackoffPolicy(base_seconds=1.0, max_seconds=8.0)
    assert backoff.delay(0, 5.0, 0.0) == 5.0
    assert backoff.delay(0, 0.0, 0.0) == 0.0
    assert backoff.delay(0, 3600.0, 1.0) == 8.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_seconds": 0},
        {"base_seconds": -1},
        {"base_seconds": math.nan},
        {"max_seconds": math.inf},
        {"max_seconds": HARD_MAX_BACKOFF_SECONDS + 0.001},
        {"base_seconds": 4.0, "max_seconds": 2.0},
        {"base_seconds": True},
    ],
)
def test_backoff_rejects_unbounded_or_invalid_parameters(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        BackoffPolicy(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_retries": -1},
        {"failure_threshold": 0},
        {"open_seconds": 0},
        {"task_token_budget": -1},
        {"daily_token_budget": -1},
        {"max_retries": True},
    ],
)
def test_policy_rejects_invalid_parameters(tmp_path, kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        Env(tmp_path, **kwargs)


def test_fallback_needs_model_mapping(tmp_path) -> None:
    with pytest.raises(ValueError):
        ModelCallPolicy(primary=FakeModelClient(), fallback=FakeModelClient(), fallback_models=None,
                        store=SqliteCallStore(f"sqlite:///{tmp_path / 'x.sqlite3'}"),
                        max_retries=1, failure_threshold=1, open_seconds=1,
                        task_token_budget=1, daily_token_budget=1)


# ---------------------------------------------------------------- L1 retry and switching matrix


@pytest.mark.parametrize(
    "error",
    [
        ModelRateLimitedError(PRIMARY_MODEL),
        ModelServerError(PRIMARY_MODEL, status_code=503),
        ModelTimeoutError(PRIMARY_MODEL),
        ModelConnectionError(PRIMARY_MODEL),
    ],
)
def test_transient_errors_retry_with_exponential_backoff(tmp_path, error) -> None:
    env = Env(tmp_path)
    env.primary.script(error, error, OUTPUT)
    result = env.client().complete(request())
    assert result.text == OUTPUT
    assert len(env.primary.calls) == 3
    assert env.sleeps == [1.0, 2.0]
    rows = env.rows()
    assert [row["status"] for row in rows] == ["error", "error", "ok"]
    assert [row["call_seq"] for row in rows] == [1, 2, 3]
    assert len({row["call_id"] for row in rows}) == 3


def test_retries_are_bounded_by_max_retries_and_backoff_sum(tmp_path) -> None:
    env = Env(tmp_path, max_retries=3)
    env.primary.script(*[ModelServerError(PRIMARY_MODEL)] * 10)
    with pytest.raises(ModelServerError):
        env.client().complete(request())
    assert len(env.primary.calls) == 4  # first try + LLM_MAX_RETRIES
    assert len(env.sleeps) == 3
    assert sum(env.sleeps) <= 3 * DEFAULT_BACKOFF_MAX_SECONDS
    assert env.primary.pending == 6


def test_rate_limit_retry_after_is_used_and_capped(tmp_path) -> None:
    env = Env(tmp_path)
    env.primary.script(ModelRateLimitedError(PRIMARY_MODEL, retry_after_seconds=3.0),
                       ModelRateLimitedError(PRIMARY_MODEL, retry_after_seconds=3600.0), OUTPUT)
    env.client().complete(request())
    assert env.sleeps == [3.0, DEFAULT_BACKOFF_MAX_SECONDS]


@pytest.mark.parametrize(
    "error",
    [
        ModelAuthError(PRIMARY_MODEL, status_code=401),
        ModelAuthError(PRIMARY_MODEL, status_code=403),
        ModelInvalidRequestError(PRIMARY_MODEL, status_code=400),
        ModelInvalidRequestError(PRIMARY_MODEL, status_code=404),
        ModelInvalidRequestError(PRIMARY_MODEL, status_code=422),
    ],
)
def test_auth_and_parameter_errors_neither_retry_nor_switch(tmp_path, error) -> None:
    env = Env(tmp_path, with_fallback=True, failure_threshold=1)
    env.primary.script(error, OUTPUT)
    with pytest.raises(type(error)):
        env.client().complete(request())
    assert len(env.primary.calls) == 1
    assert env.fallback is not None and env.fallback.calls == ()
    assert env.sleeps == []
    assert env.policy.circuit_state("primary") is CircuitState.CLOSED
    (row,) = env.rows()
    assert row["status"] == "error"


def test_primary_exhausted_switches_to_fallback_model(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True)
    env.primary.script(*[ModelServerError(PRIMARY_MODEL)] * 3)
    assert env.fallback is not None
    env.fallback.script(FakeReply(OUTPUT, usage=Usage(7, 3)))
    result = env.client().complete(request())
    assert result.text == OUTPUT
    assert result.model_requested == FALLBACK_MODEL
    assert env.fallback.calls[0].request.model == FALLBACK_MODEL
    rows = env.rows()
    assert [(r["provider_role"], r["model_requested"], r["status"]) for r in rows] == [
        ("primary", PRIMARY_MODEL, "error")] * 3 + [("fallback", FALLBACK_MODEL, "ok")]
    assert rows[-1]["model_responded"] == FALLBACK_MODEL


def test_both_providers_exhausted_raise_last_error(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True, max_retries=1)
    env.primary.script(ModelServerError(PRIMARY_MODEL), ModelServerError(PRIMARY_MODEL))
    assert env.fallback is not None
    env.fallback.script(ModelTimeoutError(FALLBACK_MODEL), ModelTimeoutError(FALLBACK_MODEL))
    with pytest.raises(ModelTimeoutError):
        env.client().complete(request())
    assert len(env.primary.calls) == 2 and len(env.fallback.calls) == 2
    assert len(env.rows()) == 4


def test_unmapped_model_does_not_switch(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True, max_retries=0)
    env.primary.script(ModelServerError("other-model"))
    req = ModelRequest(purpose="answer_with_context", model="other-model",
                       messages=(Message("user", PROMPT),), max_output_tokens=10)
    with pytest.raises(ModelServerError):
        env.client().complete(req)
    assert env.fallback is not None and env.fallback.calls == ()


def test_malformed_response_is_not_retried(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True)
    env.primary.script(ModelMalformedResponseError(PRIMARY_MODEL, status_code=200), OUTPUT)
    with pytest.raises(ModelMalformedResponseError):
        env.client().complete(request())
    assert len(env.primary.calls) == 1
    assert env.fallback is not None and env.fallback.calls == ()


def test_bound_client_is_a_model_client(tmp_path) -> None:
    env = Env(tmp_path)
    assert isinstance(env.client(), ModelClient)


# ---------------------------------------------------------------- circuit breaker


def test_breaker_opens_after_threshold_and_sticks_to_fallback(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True, failure_threshold=2, max_retries=5)
    assert env.fallback is not None
    env.primary.script(*[ModelServerError(PRIMARY_MODEL)] * 2)
    env.fallback.script(OUTPUT, OUTPUT)
    env.client().complete(request())
    # Breaker opened on the second failure: no third primary try, straight to fallback.
    assert len(env.primary.calls) == 2
    assert env.policy.circuit_state("primary") is CircuitState.OPEN
    env.client().complete(request())
    assert len(env.primary.calls) == 2  # open primary is not tried
    assert len(env.fallback.calls) == 2


def test_all_circuits_open_is_model_unavailable_without_calls(tmp_path) -> None:
    env = Env(tmp_path, failure_threshold=1, max_retries=0)
    env.primary.script(ModelServerError(PRIMARY_MODEL))
    with pytest.raises(ModelUnavailableError) as info:
        env.client().complete(request())
    assert info.value.code == "LLM_UNAVAILABLE"
    assert isinstance(info.value.__cause__, ModelServerError)
    assert not env.policy.model_available()
    calls_before, rows_before = len(env.primary.calls), len(env.rows())
    with pytest.raises(ModelUnavailableError):
        env.client().complete(request())
    assert len(env.primary.calls) == calls_before
    assert len(env.rows()) == rows_before


def test_breaker_half_open_probe_success_closes(tmp_path) -> None:
    env = Env(tmp_path, failure_threshold=1, max_retries=0, open_seconds=30)
    env.primary.script(ModelServerError(PRIMARY_MODEL), OUTPUT, OUTPUT)
    with pytest.raises(ModelUnavailableError):
        env.client().complete(request())
    env.clock.now += 29
    with pytest.raises(ModelUnavailableError):
        env.client().complete(request())
    env.clock.now += 1
    assert env.policy.circuit_state("primary") is CircuitState.HALF_OPEN
    assert env.client().complete(request()).text == OUTPUT
    assert env.policy.circuit_state("primary") is CircuitState.CLOSED
    assert env.client().complete(request()).text == OUTPUT


def test_breaker_half_open_probe_failure_reopens_full_period(tmp_path) -> None:
    env = Env(tmp_path, failure_threshold=3, max_retries=5, open_seconds=30)
    env.primary.script(*[ModelServerError(PRIMARY_MODEL)] * 4)
    with pytest.raises(ModelUnavailableError):
        env.client().complete(request())
    assert len(env.primary.calls) == 3
    env.clock.now += 30
    with pytest.raises(ModelUnavailableError):
        env.client().complete(request())
    assert len(env.primary.calls) == 4  # exactly one probe
    env.clock.now += 29
    assert env.policy.circuit_state("primary") is CircuitState.OPEN


def test_breaker_half_open_allows_single_probe_and_success_resets_count() -> None:
    clock = Clock()
    breaker = CircuitBreaker(failure_threshold=2, open_seconds=10, clock=clock)
    assert breaker.acquire()
    breaker.record_failure()
    breaker.record_success()  # any success clears the count
    assert breaker.acquire()
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    assert not breaker.acquire()
    clock.now += 10
    assert breaker.acquire()
    assert not breaker.acquire()  # probe in flight
    breaker.release()  # probe ended without a verdict (e.g. budget, auth)
    assert breaker.acquire()


def test_non_counting_errors_do_not_trip_breaker(tmp_path) -> None:
    env = Env(tmp_path, failure_threshold=1)
    env.primary.script(ModelAuthError(PRIMARY_MODEL), ModelInvalidRequestError(PRIMARY_MODEL), OUTPUT)
    for _ in range(2):
        with pytest.raises((ModelAuthError, ModelInvalidRequestError)):
            env.client().complete(request())
    assert env.policy.circuit_state("primary") is CircuitState.CLOSED
    assert env.client().complete(request()).text == OUTPUT


# ---------------------------------------------------------------- budgets


@pytest.mark.parametrize("budget", ["task_token_budget", "daily_token_budget"])
def test_zero_budget_sends_nothing(tmp_path, budget: str) -> None:
    env = Env(tmp_path, **{budget: 0})
    with pytest.raises(BudgetExceededError) as info:
        env.client().complete(request())
    assert info.value.code == "BUDGET_EXCEEDED"
    assert info.value.scope == ("task" if budget == "task_token_budget" else "daily")
    assert env.primary.calls == ()
    assert env.rows() == []


def test_zero_budget_blocks_streams_too(tmp_path) -> None:
    env = Env(tmp_path, daily_token_budget=0)
    with pytest.raises(BudgetExceededError):
        list(env.client(task_id=None, chunk_id=None, request_id="req-1").stream(request()))
    assert env.primary.calls == ()


def test_task_budget_is_soft_limit_on_used_amount(tmp_path) -> None:
    req = request(max_output_tokens=10)
    env = Env(tmp_path, task_token_budget=50)
    env.primary.script(FakeReply(OUTPUT, usage=Usage(30, 19)), FakeReply(OUTPUT, usage=Usage(30, 30)), OUTPUT)
    env.client().complete(req)  # used 0 < 50
    env.client().complete(req)  # used 49 < 50: allowed, ends at 109 (soft limit)
    with pytest.raises(BudgetExceededError):
        env.client().complete(req)  # used 109 >= 50
    assert len(env.primary.calls) == 2
    assert billed_for_task(env.url, "task-1") == 109
    # Another task is not affected; QA calls have no task budget.
    env.client(task_id="task-2").complete(req)
    env.client(task_id=None, chunk_id=None, request_id="req-1").complete(req)
    assert len(env.primary.calls) == 4


def test_budget_rejection_mid_retry_stops_without_switching(tmp_path) -> None:
    req = request(max_output_tokens=10)
    env = Env(tmp_path, with_fallback=True, task_token_budget=1)
    env.primary.script(ModelServerError(PRIMARY_MODEL), OUTPUT)  # 5xx without usage bills the estimate
    with pytest.raises(BudgetExceededError):
        env.client().complete(req)
    assert len(env.primary.calls) == 1
    assert env.fallback is not None and env.fallback.calls == ()


def test_daily_budget_counts_all_llm_calls_including_qa(tmp_path) -> None:
    req = request(max_output_tokens=10)
    env = Env(tmp_path, daily_token_budget=100)
    env.primary.script(FakeReply(OUTPUT, usage=Usage(60, 40)))
    env.client(task_id=None, chunk_id=None, request_id="req-1").complete(req)
    with pytest.raises(BudgetExceededError) as info:
        env.client(task_id="task-9").complete(req)
    assert info.value.scope == "daily"


def test_in_flight_calls_count_as_estimate(tmp_path) -> None:
    req = request(max_output_tokens=10)
    env = Env(tmp_path, task_token_budget=estimate(req) + 1)
    stream = env.client().stream(req)
    next(stream)  # first delta: record is pre-written and in flight
    assert billed_for_task(env.url, "task-1") == estimate(req)
    stream.close()
    env.policy.bind(CallAttribution(course_id="course-1", task_id="task-1")).complete(req)
    with pytest.raises(BudgetExceededError):
        env.client().complete(req)


# ---------------------------------------------------------------- model_calls records


def test_prewrite_happens_before_the_call_with_attribution(tmp_path) -> None:
    env = Env(tmp_path)
    seen: list[dict[str, Any]] = []

    def responder(req: ModelRequest) -> str:
        seen.extend(env.rows())
        return OUTPUT

    env.primary = FakeModelClient(responder=responder)
    env.policy._primary.client = env.primary  # type: ignore[attr-defined]
    req = request(max_output_tokens=77)
    env.client(chunk_attempt=2, task_attempt=3, is_repair=True).complete(req)
    (pre,) = seen
    assert pre["status"] == "sent"
    assert pre["usage_input"] is None and pre["finished_at"] is None
    assert (pre["course_id"], pre["task_id"], pre["chunk_id"], pre["request_id"]) == (
        "course-1", "task-1", "chunk-1", None)
    assert (pre["task_attempt"], pre["chunk_attempt"], pre["call_seq"], pre["is_repair"]) == (3, 2, 1, 1)
    assert pre["purpose"] == "extract_entities"
    assert pre["input_tokens_est"] == estimate_input_tokens(req)
    assert pre["max_output_tokens"] == 77
    assert len(pre["call_id"]) == 26
    (row,) = env.rows()
    assert row["status"] == "ok" and row["finished_at"] is not None
    assert row["latency_ms"] >= 0


def test_prewrite_failure_sends_no_request(tmp_path) -> None:
    class BrokenStore:
        def prewrite(self, record: CallRecord, *, task_budget: int, daily_budget: int) -> None:
            raise sqlite3.OperationalError("disk I/O error")

        def finish(self, outcome: CallOutcome) -> None:  # pragma: no cover - never reached
            raise AssertionError

    env = Env(tmp_path, store=BrokenStore())
    with pytest.raises(CallRecordError) as info:
        env.client().complete(request())
    assert info.value.code == "STORAGE_UNAVAILABLE"
    assert env.primary.calls == ()
    with pytest.raises(CallRecordError):
        list(env.client().stream(request()))
    assert env.primary.calls == ()


def test_prewrite_failure_on_real_sqlite_sends_no_request(tmp_path) -> None:
    env = Env(tmp_path)
    with sqlite3.connect(env.url.removeprefix("sqlite:///")) as database:
        database.execute("DROP TABLE model_calls")
    with pytest.raises(CallRecordError):
        env.client().complete(request())
    assert env.primary.calls == ()


def test_writeback_usage_and_missing_usage_estimate(tmp_path) -> None:
    req = request(max_output_tokens=20)
    env = Env(tmp_path)
    env.primary.script(FakeReply(OUTPUT, usage=Usage(11, 5)), FakeReply(OUTPUT, usage=None))
    env.client().complete(req)
    env.client().complete(req)
    first, second = env.rows()
    assert (first["usage_input"], first["usage_output"]) == (11, 5)
    assert (second["usage_input"], second["usage_output"]) == (None, None)
    assert second["status"] == "ok"
    assert billed_for_task(env.url, "task-1") == 16 + estimate(req)  # LEASE-28


def test_error_billing_rules(tmp_path) -> None:
    req = request(max_output_tokens=20)
    env = Env(tmp_path, max_retries=0)
    cases = [
        (ModelRateLimitedError(PRIMARY_MODEL), 0),                     # 429 no usage: 0
        (ModelAuthError(PRIMARY_MODEL), 0),                             # 401 no usage: 0
        (ModelInvalidRequestError(PRIMARY_MODEL, status_code=413), 0),  # 413: rejected set
        (ModelInvalidRequestError(PRIMARY_MODEL, status_code=409), estimate(req)),  # not in set
        (ModelServerError(PRIMARY_MODEL), estimate(req)),               # 5xx no usage: estimate
        (ModelTimeoutError(PRIMARY_MODEL, status_code=408), estimate(req)),
        (ModelTimeoutError(PRIMARY_MODEL), estimate(req)),
        (ModelAuthError(PRIMARY_MODEL, usage=Usage(3, 0)), 3),          # error with usage: usage
        (ModelServerError(PRIMARY_MODEL, usage=Usage(4, 2)), 6),
    ]
    for index, (error, billed) in enumerate(cases):
        env.primary.script(error)
        with pytest.raises(type(error)):
            env.client(task_id=f"task-{index}").complete(req)
        assert billed_for_task(env.url, f"task-{index}") == billed, error
        # Breaker threshold 5 must not interfere: reset between cases.
        env.policy._primary.breaker.record_success()  # type: ignore[attr-defined]
    rejected = [row for row in env.rows() if row["error_class"].endswith(":rejected_before_generation")]
    assert len(rejected) == 4


def test_retry_after_timeout_keeps_both_records(tmp_path) -> None:
    """LEASE-24: timeout (no response) then success → two rows, estimate + real usage."""
    req = request(max_output_tokens=20)
    env = Env(tmp_path)
    env.primary.script(ModelTimeoutError(PRIMARY_MODEL), FakeReply(OUTPUT, usage=Usage(9, 1)))
    env.client().complete(req)
    assert len(env.rows()) == 2
    assert billed_for_task(env.url, "task-1") == estimate(req) + 10
    assert billed_for_day(env.url) == estimate(req) + 10


def test_call_id_dedup_on_replayed_prewrite_and_writeback(tmp_path) -> None:
    """LEASE-17/25/28: replays neither add rows nor change the billed amount."""
    url = f"sqlite:///{tmp_path / 'd.sqlite3'}"
    migrate(url)
    store = SqliteCallStore(url)
    record = CallRecord(call_id=new_call_id(), course_id="c", task_id="t", chunk_id=None, request_id=None,
                        purpose="extract_entities", task_attempt=1, chunk_attempt=1, call_seq=1,
                        provider_role="primary", is_repair=False, model_requested="m",
                        input_tokens_est=10, max_output_tokens=5)
    store.prewrite(record, task_budget=100, daily_budget=100)
    store.prewrite(record, task_budget=100, daily_budget=100)
    assert billed_for_task(url, "t") == 15
    outcome = CallOutcome(call_id=record.call_id, status="ok", model_responded="m",
                          usage_input=None, usage_output=None, latency_ms=3, error_class=None, rejected_before_generation=False)
    store.finish(outcome)
    store.finish(outcome)
    assert billed_for_task(url, "t") == 15
    store.finish(CallOutcome(call_id=record.call_id, status="ok", model_responded="m",
                             usage_input=2, usage_output=2, latency_ms=3, error_class=None,
                             rejected_before_generation=False))
    assert billed_for_task(url, "t") == 4
    row = get_call(url, record.call_id)
    assert row is not None and row["status"] == "ok"
    with sqlite3.connect(url.removeprefix("sqlite:///")) as database:
        assert database.execute("SELECT COUNT(*) FROM model_calls").fetchone() == (1,)
    # A replayed prewrite of an existing call is not re-checked against the budget.
    store.prewrite(record, task_budget=0, daily_budget=0)


def test_store_budget_rejection_scopes(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'b.sqlite3'}"
    migrate(url)
    store = SqliteCallStore(url)

    def record(task_id: str | None, purpose: str = "extract_entities") -> CallRecord:
        return CallRecord(call_id=new_call_id(), course_id="c", task_id=task_id, chunk_id=None,
                          request_id=None, purpose=purpose, task_attempt=None, chunk_attempt=None,
                          call_seq=None, provider_role="primary", is_repair=False,
                          model_requested="m", input_tokens_est=10, max_output_tokens=0)

    store.prewrite(record("t"), task_budget=10, daily_budget=100)
    with pytest.raises(BudgetRejected) as info:
        store.prewrite(record("t"), task_budget=10, daily_budget=100)
    assert info.value.scope == "task"
    with pytest.raises(BudgetRejected) as info:
        store.prewrite(record(None), task_budget=10, daily_budget=10)
    assert info.value.scope == "daily"
    # Vector calls are recorded but never budgeted nor counted.
    store.prewrite(record(None, purpose=repo.EMBEDDING_PURPOSE), task_budget=0, daily_budget=0)
    assert billed_for_day(url) == 10


def test_daily_budget_uses_beijing_calendar_day(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'day.sqlite3'}"
    migrate(url)
    rows = [
        ("a", "2026-09-24T15:59:59.999Z", "extract_entities"),  # Beijing 09-24 23:59
        ("b", "2026-09-24T16:00:00.000Z", "extract_entities"),  # Beijing 09-25 00:00
        ("c", "2026-09-25T15:59:59.000Z", "answer_with_context"),  # Beijing 09-25 23:59
        ("d", "2026-09-25T10:00:00.000Z", repo.EMBEDDING_PURPOSE),
    ]
    with sqlite3.connect(url.removeprefix("sqlite:///")) as database:
        for call_id, created_at, purpose in rows:
            database.execute(
                "INSERT INTO model_calls (call_id, course_id, purpose, provider_role, is_repair,"
                " model_requested, input_tokens_est, max_output_tokens, created_at)"
                " VALUES (?, 'c', ?, 'primary', 0, 'm', 10, 5, ?)",
                (call_id, purpose, created_at),
            )
    assert billed_for_day(url, "2026-09-24") == 15
    assert billed_for_day(url, "2026-09-25") == 30
    with pytest.raises(ValueError):
        billed_for_day(url, "2026/09/25")


def test_new_call_id_is_ulid() -> None:
    ids = {new_call_id() for _ in range(200)}
    assert len(ids) == 200
    alphabet = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert all(len(i) == 26 and set(i) <= alphabet for i in ids)


# ---------------------------------------------------------------- streams


def test_stream_success_writes_usage(tmp_path) -> None:
    env = Env(tmp_path)
    env.primary.script(FakeReply(chunks=("ab", "cd"), usage=Usage(5, 4)))
    events = list(env.client(task_id=None, chunk_id=None, request_id="req-1").stream(request()))
    assert [e.text for e in events if isinstance(e, StreamDelta)] == ["ab", "cd"]
    assert isinstance(events[-1], StreamDone)
    (row,) = env.rows()
    assert row["status"] == "ok" and row["request_id"] == "req-1" and row["task_id"] is None
    assert (row["usage_input"], row["usage_output"]) == (5, 4)


def test_stream_failure_before_first_token_switches_without_retry(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True)
    env.primary.script(ModelTimeoutError(PRIMARY_MODEL))
    assert env.fallback is not None
    env.fallback.script(FakeReply(chunks=("x",)))
    events = list(env.client().stream(request()))
    assert isinstance(events[-1], StreamDone)
    assert events[-1].result.model_requested == FALLBACK_MODEL
    assert len(env.primary.calls) == 1 and env.sleeps == []
    assert [row["provider_role"] for row in env.rows()] == ["primary", "fallback"]


def test_stream_failure_after_first_token_does_not_switch(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True, failure_threshold=1)
    broken = ModelStreamInterruptedError(PRIMARY_MODEL)
    env.primary.script(FakeReply(chunks=("a", "b"), error_after_chunks=(1, broken)))
    stream = env.client().stream(request())
    assert next(stream) == StreamDelta("a")
    with pytest.raises(ModelStreamInterruptedError):
        next(stream)
    assert env.fallback is not None and env.fallback.calls == ()
    assert env.policy.circuit_state("primary") is CircuitState.OPEN  # counted
    (row,) = env.rows()
    assert row["status"] == "error"


def test_stream_auth_error_does_not_switch(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True)
    env.primary.script(ModelAuthError(PRIMARY_MODEL))
    with pytest.raises(ModelAuthError):
        list(env.client().stream(request()))
    assert env.fallback is not None and env.fallback.calls == ()


def test_stream_closed_early_leaves_record_sent(tmp_path) -> None:
    env = Env(tmp_path, failure_threshold=1)
    env.primary.script(FakeReply(chunks=("a", "b")))
    stream = env.client().stream(request())
    next(stream)
    stream.close()
    assert env.primary.calls[0].closed_early
    (row,) = env.rows()
    assert row["status"] == "sent"
    assert env.policy.circuit_state("primary") is CircuitState.CLOSED


# ---------------------------------------------------------------- no secrets or text


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def header(self, name: str) -> str | None:
        return None

    def read(self, amount: int, timeout: float) -> bytes:
        piece, self._body = self._body[:amount], self._body[amount:]
        return piece

    def close(self) -> None:
        pass


class _Transport:
    def __init__(self, *responses: _Response) -> None:
        self.responses = list(responses)
        self.bodies: list[bytes] = []

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> _Response:
        self.bodies.append(body)
        return self.responses.pop(0)


def test_logs_and_records_hold_no_key_prompt_or_output(tmp_path, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    ok_body = json.dumps({"model": PRIMARY_MODEL, "choices": [
        {"message": {"content": OUTPUT}, "finish_reason": "stop"}]}).encode()
    transport = _Transport(
        _Response(500, json.dumps({"error": {"message": PROMPT}}).encode()),
        _Response(200, ok_body),
        _Response(401, json.dumps({"error": {"message": API_KEY}}).encode()),
    )
    env = Env(tmp_path)
    env.policy._primary.client = CompatibleModelClient(  # type: ignore[attr-defined]
        "https://llm.invalid/v1", API_KEY, transport=transport)
    assert env.client().complete(request()).text == OUTPUT
    with pytest.raises(ModelAuthError):
        env.client().complete(request())
    assert PROMPT.encode() in transport.bodies[0]  # the prompt did reach the provider
    assert caplog.records, "policy should log failures"
    assert any(r.levelno >= logging.ERROR for r in caplog.records)  # auth → error log
    dumped = caplog.text + json.dumps(env.rows(), ensure_ascii=False)
    for secret in (API_KEY, PROMPT, OUTPUT, "栈与队列", "答案正文"):
        assert secret not in dumped


def test_policy_repr_has_no_key(tmp_path) -> None:
    env = Env(tmp_path)
    env.policy._primary.client = CompatibleModelClient(  # type: ignore[attr-defined]
        "https://llm.invalid/v1", API_KEY, transport=_Transport())
    assert API_KEY not in repr(env.policy) and API_KEY not in repr(env.client())


# ---------------------------------------------------------------- settings wiring


def test_from_settings_reads_existing_variables(tmp_path) -> None:
    from app.config import Settings

    settings = Settings(
        LLM_MAX_RETRIES=1, LLM_CIRCUIT_FAILURE_THRESHOLD=4, LLM_CIRCUIT_OPEN_SECONDS=12,
        LLM_TASK_TOKEN_BUDGET=0, LLM_DAILY_TOKEN_BUDGET=7,
        LLM_EXTRACTION_MODEL="p-ext", LLM_CHAT_MODEL="p-chat",
        LLM_FALLBACK_EXTRACTION_MODEL="f-ext", LLM_FALLBACK_CHAT_MODEL="f-chat",
    )
    url = f"sqlite:///{tmp_path / 's.sqlite3'}"
    built = ModelCallPolicy.from_settings(settings, primary=FakeModelClient(), fallback=FakeModelClient(),
                                          store=SqliteCallStore(url))
    assert built.max_retries == 1
    assert built.task_token_budget == 0 and built.daily_token_budget == 7
    assert built.fallback_models == {"p-ext": "f-ext", "p-chat": "f-chat"}
    assert built.failure_threshold == 4 and built.open_seconds == 12
    assert built.backoff == BackoffPolicy()


def test_policy_module_documents_duration_bound() -> None:
    # A07: 单次非流式调用耗时上界 = 2 × [(R + 1) × T + 退避总和]；退避总和 ≤ R × 退避上限。
    assert policy_module.max_backoff_total(2) == 2 * DEFAULT_BACKOFF_MAX_SECONDS
    assert policy_module.max_call_duration_seconds(max_retries=2, request_timeout_seconds=60,
                                                  with_fallback=True) == 2 * (3 * 60 + 16)
    assert policy_module.max_call_duration_seconds(max_retries=2, request_timeout_seconds=60,
                                                  with_fallback=False) == 3 * 60 + 16


def test_no_backoff_when_breaker_opens_before_switching(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True, failure_threshold=2, max_retries=5)
    assert env.fallback is not None
    env.primary.script(*[ModelServerError(PRIMARY_MODEL)] * 2)
    env.fallback.script(OUTPUT)
    env.client().complete(request())
    assert env.sleeps == [1.0]


# ---------------------------------------------------------------- deadline (grounded-qa 链路时限)


def _slow(env: Env, client: FakeModelClient, seconds: float) -> None:
    """Each ``complete`` on ``client`` takes ``seconds`` of the fake clock."""
    inner = client.complete

    def complete(req: ModelRequest) -> Any:
        env.clock.now += seconds
        return inner(req)

    client.complete = complete  # type: ignore[method-assign]


def _qa(env: Env, deadline: float | None) -> Any:
    attribution = CallAttribution(course_id="course-1", request_id="req-1")
    return env.policy.bind(attribution, deadline=deadline)


@pytest.mark.parametrize(("own", "expected"), [(None, 10.0), (3.0, 3.0), (20.0, 10.0)])
def test_deadline_caps_each_request_timeout(tmp_path, own, expected) -> None:
    env = Env(tmp_path)
    env.primary.script(OUTPUT)
    req = request() if own is None else replace(request(), timeout_seconds=own)
    _qa(env, env.clock.now + 10).complete(req)
    assert env.primary.calls[0].request.timeout_seconds == expected


def test_without_deadline_request_timeout_is_untouched(tmp_path) -> None:
    env = Env(tmp_path)
    env.primary.script(OUTPUT)
    env.client().complete(request())
    assert env.primary.calls[0].request.timeout_seconds is None


def test_retries_within_deadline_are_unchanged(tmp_path) -> None:
    env = Env(tmp_path)
    env.primary.script(ModelServerError(PRIMARY_MODEL), ModelServerError(PRIMARY_MODEL), OUTPUT)
    assert _qa(env, env.clock.now + 100).complete(request()).text == OUTPUT
    assert env.sleeps == [1.0, 2.0]


def test_backoff_reaching_deadline_stops_retrying(tmp_path) -> None:
    env = Env(tmp_path, max_retries=2)
    _slow(env, env.primary, 9.5)
    env.primary.script(ModelServerError(PRIMARY_MODEL), OUTPUT)
    with pytest.raises(CallDeadlineExceededError) as caught:
        _qa(env, env.clock.now + 10).complete(request())
    assert caught.value.code == "LLM_UNAVAILABLE" and caught.value.reason == "timeout"
    assert isinstance(caught.value.__cause__, ModelServerError)
    assert env.sleeps == [] and len(env.primary.calls) == 1 and env.primary.pending == 1
    assert [row["status"] for row in env.rows()] == ["error"]


def test_deadline_cut_moves_to_fallback_with_remaining_time(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True, max_retries=2)
    assert env.fallback is not None
    _slow(env, env.primary, 9.5)
    env.primary.script(ModelTimeoutError(PRIMARY_MODEL))
    env.fallback.script(OUTPUT)
    result = _qa(env, env.clock.now + 10).complete(request())
    assert result.model_requested == FALLBACK_MODEL
    assert env.sleeps == []
    assert env.fallback.calls[0].request.timeout_seconds == pytest.approx(0.5)


def test_expired_deadline_sends_nothing(tmp_path) -> None:
    env = Env(tmp_path, with_fallback=True)
    assert env.fallback is not None
    with pytest.raises(CallDeadlineExceededError):
        _qa(env, env.clock.now).complete(request())
    with pytest.raises(CallDeadlineExceededError):
        list(_qa(env, env.clock.now - 1).stream(request()))
    assert env.primary.calls == () and env.fallback.calls == ()
    assert env.rows() == []


def test_deadline_caps_stream_timeout(tmp_path) -> None:
    env = Env(tmp_path)
    env.primary.script(FakeReply(chunks=("a",)))
    events = list(_qa(env, env.clock.now + 7).stream(request()))
    assert isinstance(events[-1], StreamDone)
    assert env.primary.calls[0].request.timeout_seconds == 7.0


@pytest.mark.parametrize("deadline", [math.nan, math.inf, True, "10"])
def test_bind_rejects_invalid_deadline(tmp_path, deadline) -> None:
    env = Env(tmp_path)
    with pytest.raises(ValueError):
        env.policy.bind(CallAttribution(course_id="course-1"), deadline=deadline)
