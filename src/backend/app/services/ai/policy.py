"""Model call policy (E04): bounded retry, primary/fallback switching, circuit breaking,
token budgets and ``model_calls`` bookkeeping around E02 ``ModelClient`` adapters.

Rules: docs/integrations.md「模型接入规则（A07）」(主备切换矩阵、预算、调用记录),
ADR-011 决定 4 and 修订 2/3, specs/task-processing.md §8.3 and LEASE-17/24～30,
specs/grounded-qa.md QA-28/29.

``ModelCallPolicy.bind(attribution)`` returns a ``ModelClient`` for one caller context
(an E12 chunk attempt, a J05 question …). For every *physical* provider request it:

1. picks the role: primary unless its breaker is open, then the fallback (only when one is
   configured, the request's model has a fallback model and its breaker admits the call);
2. pre-writes a ``sent`` row in ``model_calls`` with a fresh ULID ``call_id``, the input
   estimate (E03 ``estimate_input_tokens``) and the declared output ceiling; the store
   rejects the call when ``used >= budget`` for the task or the Beijing day. A budget of 0
   sends nothing. **If the pre-write fails, no request is sent** (``CallRecordError``);
3. sends the request and writes the outcome back by ``call_id`` (usage, responded model,
   latency, error class; replays overwrite). Missing usage is billed by the store's rule.

Switching matrix (non-streaming ``complete``):

- timeout / connection / 429 / 5xx: retried on the same provider up to ``max_retries``
  times with bounded exponential backoff (``BackoffPolicy``; ``Retry-After`` honoured but
  capped), each failure counted by that provider's breaker; when the primary is exhausted
  (or its breaker opens) the call moves to the fallback once.
- 401/403 (auth), other 4xx (parameters), malformed responses: no retry, no switch, not
  counted; raised as is. Auth failures are logged at ERROR.
- Every role unavailable (breakers open) → ``ModelUnavailableError`` (``LLM_UNAVAILABLE``;
  for workers the ADR-011 stage-level temporary failure: the chunk is not a failed chunk).
- Otherwise the last provider error is re-raised (L2 takes over).

Streams: no L1 retry. A transient failure or stream break before the first non-empty delta
switches to the fallback (counted); after text was shown the error is raised without
switching (counted). A stream closed early by the caller leaves its row ``sent`` (billed
as the estimate) and does not touch the breaker.

Duration bound of one non-streaming call (A07): ``max_call_duration_seconds``.

Deadline (grounded-qa「链路时限」: no call or retry may outlast the remaining time):
``bind(attribution, deadline=...)`` takes an absolute time on the policy clock. Every
physical request then gets ``timeout_seconds = min(request timeout, remaining)`` (a request
without its own timeout gets the remaining time, replacing the adapter default); a backoff
that would reach the deadline is skipped and the call moves on (to the fallback, if any);
with no time left no row is written and no request is sent. Any call cut short this way
raises ``CallDeadlineExceededError`` (``LLM_UNAVAILABLE``, ``reason = "timeout"``, O9).
Workers bind without a deadline and keep the plain behaviour above.

Nothing here logs prompt text, model output, keys or response bodies: log lines carry the
``call_id``, role, model ID, error class and HTTP status only.
"""

from __future__ import annotations

import logging
import math
import random as _random
import secrets
import threading
import time
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol

from app.repositories.model_calls import BudgetRejected, CallOutcome, CallRecord

from .client import (
    ErrorClass,
    ModelCallError,
    ModelClient,
    ModelError,
    ModelRateLimitedError,
    ModelRequest,
    ModelResult,
    ModelStreamInterruptedError,
    StreamDelta,
    StreamDone,
    StreamEvent,
)
from .compatible import estimate_input_tokens

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

# Backoff bounds (A07: 退避参数由 E04 定，必须有上限). Not yet environment variables.
DEFAULT_BACKOFF_BASE_SECONDS: Final = 1.0
DEFAULT_BACKOFF_MAX_SECONDS: Final = 8.0
HARD_MAX_BACKOFF_SECONDS: Final = 30.0

# Switching-matrix row 1: retried, switched, counted by the breaker.
TRANSIENT_ERROR_CLASSES: Final = frozenset(
    {ErrorClass.TIMEOUT, ErrorClass.CONNECTION, ErrorClass.RATE_LIMITED, ErrorClass.SERVER}
)
# Stream breaks also count (「流式问答，已出字后中断」计入熔断); before first text they switch.
_STREAM_COUNTED: Final = TRANSIENT_ERROR_CLASSES | {ErrorClass.STREAM_INTERRUPTED}
UNEXPECTED_ERROR_CLASS: Final = "unexpected"

Role = Literal["primary", "fallback"]


def _is_int(value: object) -> bool:
    return type(value) is int


def _is_seconds(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value))


# ---------------------------------------------------------------- call IDs

_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_call_id() -> str:
    """A ULID: 48-bit millisecond timestamp + 80 random bits, Crockford base32 (26 chars)."""
    value = (time.time_ns() // 1_000_000) << 80 | int.from_bytes(secrets.token_bytes(10), "big")
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


# ---------------------------------------------------------------- backoff


@dataclass(frozen=True)
class BackoffPolicy:
    """Exponential backoff with jitter: ``min(max, base·2ⁿ) · (0.5 + 0.5·r)``, r ∈ [0, 1].

    ``Retry-After`` replaces the computed delay but is capped at ``max_seconds``. Every
    delay is ≤ ``max_seconds`` ≤ ``HARD_MAX_BACKOFF_SECONDS``.
    """

    base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    max_seconds: float = DEFAULT_BACKOFF_MAX_SECONDS

    def __post_init__(self) -> None:
        if not _is_seconds(self.base_seconds) or self.base_seconds <= 0:
            raise ValueError("BackoffPolicy: base_seconds must be a finite number > 0")
        if not _is_seconds(self.max_seconds) or not (
            self.base_seconds <= self.max_seconds <= HARD_MAX_BACKOFF_SECONDS
        ):
            raise ValueError(
                f"BackoffPolicy: max_seconds must be between base_seconds and {HARD_MAX_BACKOFF_SECONDS}"
            )

    def delay(self, retry_index: int, retry_after: float | None, rand: float) -> float:
        """Delay before retry ``retry_index + 1`` (0-based count of retries so far)."""
        if retry_after is not None:
            return min(max(float(retry_after), 0.0), self.max_seconds)
        exponent = min(max(retry_index, 0), 62)
        ceiling = min(self.max_seconds, self.base_seconds * (2 ** exponent))
        jitter = 0.5 + 0.5 * min(max(rand, 0.0), 1.0)
        return ceiling * jitter


def max_backoff_total(max_retries: int, backoff: BackoffPolicy | None = None) -> float:
    """Upper bound of the summed backoff on one provider for one call."""
    return max_retries * (backoff or BackoffPolicy()).max_seconds


def max_call_duration_seconds(
    *, max_retries: int, request_timeout_seconds: float, with_fallback: bool,
    backoff: BackoffPolicy | None = None,
) -> float:
    """A07: ``2 × [(R + 1) × T + 退避总和]`` with fallback, without the factor 2 otherwise."""
    one = (max_retries + 1) * request_timeout_seconds + max_backoff_total(max_retries, backoff)
    return 2 * one if with_fallback else one


# ---------------------------------------------------------------- circuit breaker


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-process breaker: ``failure_threshold`` consecutive failures open it for
    ``open_seconds``; then one probe is admitted (half-open). Probe success closes it,
    probe failure re-opens it for the full period. ``release`` ends an admitted call
    without a verdict (budget refusal, auth or parameter error, early close)."""

    def __init__(self, *, failure_threshold: int, open_seconds: float, clock: Callable[[], float]) -> None:
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False

    def __repr__(self) -> str:
        return f"CircuitBreaker(state={self.state.value}, failures={self._failures})"

    def _state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._clock() - self._opened_at >= self._open_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state()

    def available(self) -> bool:
        with self._lock:
            state = self._state()
            return state is CircuitState.CLOSED or (state is CircuitState.HALF_OPEN and not self._probing)

    def acquire(self) -> bool:
        with self._lock:
            state = self._state()
            if state is CircuitState.CLOSED:
                return True
            if state is CircuitState.HALF_OPEN and not self._probing:
                self._probing = True
                return True
            return False

    def release(self) -> None:
        with self._lock:
            self._probing = False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._probing = False

    def record_failure(self) -> None:
        with self._lock:
            if self._opened_at is not None:  # failed probe (or a straggler): re-open fully
                self._opened_at = self._clock()
            else:
                self._failures += 1
                if self._failures >= self._threshold:
                    self._opened_at = self._clock()
            self._probing = False


# ---------------------------------------------------------------- errors


class PolicyError(ModelError):
    """Refusals decided by the policy; ``code`` is the contract error code."""

    code: str = "INTERNAL_ERROR"


class BudgetExceededError(PolicyError):
    """The task or daily token budget is used up; no request was sent (QA-28)."""

    code = "BUDGET_EXCEEDED"

    def __init__(self, scope: Literal["task", "daily"]) -> None:
        self.scope = scope
        super().__init__(f"{scope} token budget exhausted; no model request sent")


class CallRecordError(PolicyError):
    """The ``model_calls`` pre-write failed; no request was sent (O12, QA-29, LEASE-27)."""

    code = "STORAGE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("model_calls pre-write failed; no model request sent")


class CallDeadlineExceededError(PolicyError):
    """The caller's deadline left no time for another attempt (grounded-qa O9).

    Raised before any request that could not start in time, or after a failed attempt whose
    retry the deadline cut short; the last provider error (if any) is the ``__cause__``.
    """

    code = "LLM_UNAVAILABLE"
    reason = "timeout"

    def __init__(self) -> None:
        super().__init__("call deadline reached; no further model request sent")


class ModelUnavailableError(PolicyError):
    """Every provider usable for this request has an open breaker (A07 matrix)."""

    code = "LLM_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("model unavailable: circuit breakers open")


# ---------------------------------------------------------------- store and attribution


class CallStore(Protocol):
    def prewrite(self, record: CallRecord, *, task_budget: int, daily_budget: int) -> None: ...

    def finish(self, outcome: CallOutcome) -> None: ...


@dataclass(frozen=True)
class CallAttribution:
    """Who a call belongs to (「调用记录」归属字段). QA calls: ``request_id`` and no ``task_id``."""

    course_id: str
    task_id: str | None = None
    chunk_id: str | None = None
    request_id: str | None = None
    task_attempt: int | None = None
    chunk_attempt: int | None = None
    is_repair: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.course_id, str) or not self.course_id:
            raise ValueError("CallAttribution: course_id is required")
        for name in ("task_id", "chunk_id", "request_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"CallAttribution: {name} must be a non-empty str or None")
        for name in ("task_attempt", "chunk_attempt"):
            value = getattr(self, name)
            if value is not None and (not _is_int(value) or value < 1):
                raise ValueError(f"CallAttribution: {name} must be an int >= 1 or None")
        if not isinstance(self.is_repair, bool):
            raise ValueError("CallAttribution: is_repair must be bool")


@dataclass(eq=False)
class _Provider:
    role: Role
    client: ModelClient = field(repr=False)
    breaker: CircuitBreaker


# ---------------------------------------------------------------- policy


class ModelCallPolicy:
    """Shared, thread-safe policy state (breakers) for one process; see the module docstring."""

    def __init__(
        self,
        *,
        primary: ModelClient,
        store: CallStore,
        max_retries: int,
        failure_threshold: int,
        open_seconds: float,
        task_token_budget: int,
        daily_token_budget: int,
        fallback: ModelClient | None = None,
        fallback_models: Mapping[str, str] | None = None,
        backoff: BackoffPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        random: Callable[[], float] = _random.random,
        new_id: Callable[[], str] = new_call_id,
        estimate: Callable[[ModelRequest], int] = estimate_input_tokens,
    ) -> None:
        if not _is_int(max_retries) or max_retries < 0:
            raise ValueError("ModelCallPolicy: max_retries must be an int >= 0")
        if not _is_int(failure_threshold) or failure_threshold < 1:
            raise ValueError("ModelCallPolicy: failure_threshold must be an int >= 1")
        if not _is_seconds(open_seconds) or open_seconds <= 0:
            raise ValueError("ModelCallPolicy: open_seconds must be a finite number > 0")
        for name, value in (("task_token_budget", task_token_budget), ("daily_token_budget", daily_token_budget)):
            if not _is_int(value) or value < 0:
                raise ValueError(f"ModelCallPolicy: {name} must be an int >= 0")
        mapping = dict(fallback_models or {})
        if fallback is not None and not mapping:
            raise ValueError("ModelCallPolicy: a fallback client needs fallback_models")
        if not all(isinstance(k, str) and k and isinstance(v, str) and v for k, v in mapping.items()):
            raise ValueError("ModelCallPolicy: fallback_models must map non-empty model IDs")
        self.max_retries = max_retries
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.task_token_budget = task_token_budget
        self.daily_token_budget = daily_token_budget
        self.fallback_models: dict[str, str] = mapping if fallback is not None else {}
        self.backoff = backoff if backoff is not None else BackoffPolicy()
        self._store = store
        self._clock = clock
        self._sleep = sleep
        self._random = random
        self._new_id = new_id
        self._estimate = estimate

        def breaker() -> CircuitBreaker:
            return CircuitBreaker(failure_threshold=failure_threshold, open_seconds=open_seconds, clock=clock)

        self._primary = _Provider("primary", primary, breaker())
        self._fallback = _Provider("fallback", fallback, breaker()) if fallback is not None else None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        primary: ModelClient,
        store: CallStore,
        fallback: ModelClient | None = None,
        **overrides: object,
    ) -> ModelCallPolicy:
        """Retry, breaker and budget values from ``LLM_*`` settings; backoff by argument."""
        mapping: dict[str, str] = {}
        if fallback is not None:
            pairs = (
                (settings.LLM_EXTRACTION_MODEL, settings.LLM_FALLBACK_EXTRACTION_MODEL),
                (settings.LLM_CHAT_MODEL, settings.LLM_FALLBACK_CHAT_MODEL),
            )
            for source, target in pairs:
                if not source.strip() or not target.strip():
                    continue
                if mapping.get(source, target) != target:
                    raise ValueError("ModelCallPolicy: one primary model maps to two fallback models")
                mapping[source] = target
        kwargs: dict[str, object] = {
            "max_retries": settings.LLM_MAX_RETRIES,
            "failure_threshold": settings.LLM_CIRCUIT_FAILURE_THRESHOLD,
            "open_seconds": settings.LLM_CIRCUIT_OPEN_SECONDS,
            "task_token_budget": settings.LLM_TASK_TOKEN_BUDGET,
            "daily_token_budget": settings.LLM_DAILY_TOKEN_BUDGET,
            "fallback_models": mapping,
        }
        kwargs.update(overrides)
        return cls(primary=primary, fallback=fallback, store=store, **kwargs)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        fallback = self._fallback.breaker.state.value if self._fallback else "none"
        return (f"ModelCallPolicy(primary={self._primary.breaker.state.value}, fallback={fallback}, "
                f"max_retries={self.max_retries})")

    # -- state for ADR-011 决定 4 (阶段级临时故障)

    def circuit_state(self, role: Role) -> CircuitState:
        provider = self._primary if role == "primary" else self._fallback
        if provider is None:
            raise ValueError("no fallback provider configured")
        return provider.breaker.state

    def model_available(self, model: str | None = None) -> bool:
        """False when every provider usable for ``model`` (default: any) has an open breaker."""
        return any(provider.breaker.available() for provider, _ in self._candidates(model))

    def bind(self, attribution: CallAttribution, *, deadline: float | None = None) -> BoundModelClient:
        """Client for one caller context; ``deadline`` is an absolute time on the policy clock."""
        if not isinstance(attribution, CallAttribution):
            raise TypeError("attribution must be a CallAttribution")
        if deadline is not None and not _is_seconds(deadline):
            raise ValueError("deadline must be a finite number or None")
        return BoundModelClient(self, attribution, deadline)

    # -- internals

    def _candidates(self, model: str | None) -> list[tuple[_Provider, str | None]]:
        found: list[tuple[_Provider, str | None]] = [(self._primary, model)]
        if self._fallback is not None:
            if model is None:
                found.append((self._fallback, None))
            elif model in self.fallback_models:
                found.append((self._fallback, self.fallback_models[model]))
        return found

    def _prewrite(self, bound: BoundModelClient, provider: _Provider, request: ModelRequest) -> str:
        attribution = bound.attribution
        if self.daily_token_budget == 0:
            raise BudgetExceededError("daily")
        if attribution.task_id is not None and self.task_token_budget == 0:
            raise BudgetExceededError("task")
        call_id = self._new_id()
        record = CallRecord(
            call_id=call_id,
            course_id=attribution.course_id,
            task_id=attribution.task_id,
            chunk_id=attribution.chunk_id,
            request_id=attribution.request_id,
            purpose=request.purpose,
            task_attempt=attribution.task_attempt,
            chunk_attempt=attribution.chunk_attempt,
            call_seq=bound._next_seq(),
            provider_role=provider.role,
            is_repair=attribution.is_repair,
            model_requested=request.model,
            input_tokens_est=self._estimate(request),
            max_output_tokens=request.max_output_tokens,
        )
        try:
            self._store.prewrite(record, task_budget=self.task_token_budget, daily_budget=self.daily_token_budget)
        except BudgetRejected as rejected:
            logger.warning("model call refused by %s budget purpose=%s role=%s model=%s",
                           rejected.scope, request.purpose, provider.role, request.model)
            raise BudgetExceededError(rejected.scope) from None
        except Exception as error:
            logger.error("model_calls pre-write failed (%s); request not sent purpose=%s role=%s",
                         type(error).__name__, request.purpose, provider.role)
            raise CallRecordError() from None
        return call_id

    def _finish(self, call_id: str, outcome: CallOutcome) -> None:
        try:
            self._store.finish(outcome)
        except Exception as error:
            # The row stays ``sent`` and is billed as the estimate (「调用记录」第 3 条).
            logger.error("model_calls write-back failed (%s) call_id=%s", type(error).__name__, call_id)

    def _remaining(self, bound: BoundModelClient) -> float | None:
        return None if bound.deadline is None else bound.deadline - self._clock()

    def _bounded(self, bound: BoundModelClient, request: ModelRequest, last: BaseException | None) -> ModelRequest:
        """``request`` with its timeout capped by the remaining time; raises when none is left."""
        remaining = self._remaining(bound)
        if remaining is None:
            return request
        if remaining <= 0:
            raise CallDeadlineExceededError() from last
        if request.timeout_seconds is not None and request.timeout_seconds <= remaining:
            return request
        return replace(request, timeout_seconds=remaining)

    def _latency_ms(self, started: float) -> int:
        return max(0, round((self._clock() - started) * 1000))

    def _finish_ok(self, call_id: str, result: ModelResult, started: float) -> None:
        usage = result.usage
        self._finish(call_id, CallOutcome(
            call_id=call_id, status="ok", model_responded=result.model_responded,
            usage_input=usage.input_tokens if usage is not None else None,
            usage_output=usage.output_tokens if usage is not None else None,
            latency_ms=self._latency_ms(started), error_class=None, rejected_before_generation=False,
        ))

    def _finish_error(self, call_id: str, error: BaseException, started: float) -> None:
        if isinstance(error, ModelCallError):
            usage = error.usage
            error_class = error.error_class.value
            rejected = error.rejected_before_generation
        else:
            usage, error_class, rejected = None, UNEXPECTED_ERROR_CLASS, False
        self._finish(call_id, CallOutcome(
            call_id=call_id, status="error", model_responded=None,
            usage_input=usage.input_tokens if usage is not None else None,
            usage_output=usage.output_tokens if usage is not None else None,
            latency_ms=self._latency_ms(started), error_class=error_class,
            rejected_before_generation=rejected,
        ))

    def _log_failure(self, call_id: str, provider: _Provider, model: str, error: BaseException) -> None:
        if isinstance(error, ModelCallError):
            level = logging.ERROR if error.error_class is ErrorClass.AUTH else logging.WARNING
            logger.log(level, "model call failed call_id=%s role=%s model=%s error_class=%s status=%s",
                       call_id, provider.role, model, error.error_class.value, error.status_code)
        else:
            logger.error("model call raised %s call_id=%s role=%s model=%s",
                         type(error).__name__, call_id, provider.role, model)

    def _unavailable(self, model: str, last: BaseException | None) -> PolicyError | BaseException:
        if last is None or not self.model_available(model):
            unavailable = ModelUnavailableError()
            unavailable.__cause__ = last
            return unavailable
        return last

    # -- complete

    def _complete(self, bound: BoundModelClient, request: ModelRequest) -> ModelResult:
        last: BaseException | None = None
        cut = False
        for provider, model in self._candidates(request.model):
            assert model is not None
            call_request = request if model == request.model else replace(request, model=model)
            for retry in range(self.max_retries + 1):
                attempt_request = self._bounded(bound, call_request, last)
                if not provider.breaker.acquire():
                    break
                try:
                    call_id = self._prewrite(bound, provider, attempt_request)
                except BaseException:
                    provider.breaker.release()
                    raise
                started = self._clock()
                try:
                    result = provider.client.complete(attempt_request)
                except ModelCallError as error:
                    self._finish_error(call_id, error, started)
                    self._log_failure(call_id, provider, model, error)
                    if error.error_class not in TRANSIENT_ERROR_CLASSES:
                        provider.breaker.release()
                        raise
                    provider.breaker.record_failure()
                    last = error
                    # Back off only when this provider will admit another try; an opened
                    # breaker moves the call to the fallback without waiting.
                    if retry < self.max_retries and provider.breaker.available():
                        retry_after = error.retry_after_seconds if isinstance(error, ModelRateLimitedError) else None
                        delay = self.backoff.delay(retry, retry_after, self._random())
                        remaining = self._remaining(bound)
                        if remaining is not None and delay >= remaining:
                            cut = True  # waiting would reach the deadline: no further try here
                            break
                        self._sleep(delay)
                    continue
                except BaseException as error:
                    self._finish_error(call_id, error, started)
                    self._log_failure(call_id, provider, model, error)
                    provider.breaker.release()
                    raise
                provider.breaker.record_success()
                self._finish_ok(call_id, result, started)
                return result
        if cut:
            raise CallDeadlineExceededError() from last
        raise self._unavailable(request.model, last)

    # -- stream

    def _stream(self, bound: BoundModelClient, request: ModelRequest) -> Generator[StreamEvent, None, None]:
        last: BaseException | None = None
        for provider, model in self._candidates(request.model):
            assert model is not None
            call_request = self._bounded(
                bound, request if model == request.model else replace(request, model=model), last)
            if not provider.breaker.acquire():
                continue
            try:
                call_id = self._prewrite(bound, provider, call_request)
            except BaseException:
                provider.breaker.release()
                raise
            started = self._clock()
            shown = False
            inner = provider.client.stream(call_request)
            try:
                for event in inner:
                    if isinstance(event, StreamDone):
                        provider.breaker.record_success()
                        self._finish_ok(call_id, event.result, started)
                        yield event
                        return
                    if isinstance(event, StreamDelta) and event.text:
                        shown = True
                    yield event
                # A stream that ends without StreamDone broke off (E02: StreamDone is last).
                raise ModelStreamInterruptedError(call_request.model)
            except GeneratorExit:
                # Closed by the caller: no response verdict; the row stays ``sent``.
                provider.breaker.release()
                raise
            except ModelCallError as error:
                self._finish_error(call_id, error, started)
                self._log_failure(call_id, provider, model, error)
                if error.error_class in _STREAM_COUNTED:
                    provider.breaker.record_failure()
                else:
                    provider.breaker.release()
                if shown or error.error_class not in _STREAM_COUNTED:
                    raise
                last = error
            except BaseException as error:
                self._finish_error(call_id, error, started)
                self._log_failure(call_id, provider, model, error)
                provider.breaker.release()
                raise
            finally:
                inner.close()
        raise self._unavailable(request.model, last)


class BoundModelClient:
    """``ModelClient`` for one caller context; numbers its physical calls 1, 2, 3 … (``call_seq``)."""

    def __init__(self, policy: ModelCallPolicy, attribution: CallAttribution, deadline: float | None = None) -> None:
        self._policy = policy
        self.attribution = attribution
        self.deadline = deadline
        self._seq_lock = threading.Lock()
        self._seq = 0

    def __repr__(self) -> str:
        return f"BoundModelClient(course_id={self.attribution.course_id!r}, task_id={self.attribution.task_id!r})"

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def complete(self, request: ModelRequest) -> ModelResult:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        return self._policy._complete(self, request)

    def stream(self, request: ModelRequest) -> Generator[StreamEvent, None, None]:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest")
        return self._policy._stream(self, request)


__all__ = [
    "DEFAULT_BACKOFF_BASE_SECONDS",
    "DEFAULT_BACKOFF_MAX_SECONDS",
    "HARD_MAX_BACKOFF_SECONDS",
    "TRANSIENT_ERROR_CLASSES",
    "BackoffPolicy",
    "BoundModelClient",
    "BudgetExceededError",
    "CallAttribution",
    "CallDeadlineExceededError",
    "CallRecordError",
    "CallStore",
    "CircuitBreaker",
    "CircuitState",
    "ModelCallPolicy",
    "ModelUnavailableError",
    "PolicyError",
    "max_backoff_total",
    "max_call_duration_seconds",
    "new_call_id",
]
