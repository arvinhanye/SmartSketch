"""Internal extraction.units responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, replace
from app.repositories.chunks import StoredChunk
from app.repositories.task_leases import Lease
from app.services.ai.client import ModelAuthError, ModelClient, ModelError, ModelRequest, ModelResult, StreamEvent
from app.services.ai.entities import REPAIR_PURPOSE
from app.services.ai.policy import (
    BudgetExceededError,
    CallAttribution,
    CallRecordError,
    ModelCallPolicy,
    ModelUnavailableError,
)
from app.services.ai.relations import SectionEntity, SourceChunk
from app.workers.extraction.candidates import (
    _encode_entity,
    _encode_relation,
    _identity,
)
from app.workers.extraction.types import (
    BUDGET_CODE,
    ExtractLimits,
    ExtractionToolkit,
    MODEL_ERROR_CODE,
    OUTPUT_INVALID_CODE,
    _Halt,
    _Section,
    _UnitResult,
    TaskEntity,
)
from app.workers.extraction.analysis import analyze_section
from app.workers.extraction import windowed
from app.services.ai.request_budget import WindowBudgetError, check_request_budget

# ---------------------------------------------------------------- 模型调用


class _AttemptClient:
    """一次块/小节尝试的客户端：修复调用走 ``is_repair=True`` 的绑定，各自独立记录（E04 交接）。"""

    def __init__(self, policy: ModelCallPolicy, attribution: CallAttribution, *,
                 guard: Callable[[], None] | None = None, max_input_bytes: int | None = None) -> None:
        options = {} if guard is None else {"before_attempt": guard}
        self._main = policy.bind(attribution, **options)
        self._repair = policy.bind(replace(attribution, is_repair=True), **options)
        self._max_input_bytes = max_input_bytes

    def _pick(self, request: ModelRequest) -> ModelClient:
        return self._repair if request.purpose == REPAIR_PURPOSE else self._main

    def complete(self, request: ModelRequest) -> ModelResult:
        if self._max_input_bytes is not None:
            check_request_budget(request, self._max_input_bytes)
        return self._pick(request).complete(request)

    def stream(self, request: ModelRequest) -> Iterable[StreamEvent]:
        if self._max_input_bytes is not None:
            check_request_budget(request, self._max_input_bytes)
        return self._pick(request).stream(request)


def _attempts(
    limits: ExtractLimits, lease: Lease, chunk_id: str | None, toolkit: ExtractionToolkit,
    body: Callable[[ModelClient], Mapping[str, object] | str],
) -> _UnitResult:
    """L2：最多 ``chunk_max_attempts`` 次；``body`` 返回结果或输出不合规的失败码。"""
    last = OUTPUT_INVALID_CODE
    for attempt in range(1, limits.chunk_max_attempts + 1):
        if toolkit.guard is not None:
            toolkit.guard()
        client = _AttemptClient(
            toolkit.policy,
            CallAttribution(
                course_id=lease.course_id,
                task_id=lease.task_id,
                chunk_id=chunk_id,
                task_attempt=lease.attempt,
                chunk_attempt=attempt,
                user_id=toolkit.user_id,
            ),
            guard=toolkit.guard if toolkit.preserve_mentions else None,
            max_input_bytes=None if toolkit.window_policy is None else toolkit.window_policy.max_input_bytes,
        )
        try:
            outcome = body(client)
        except BudgetExceededError:
            return _UnitResult("failed", attempt, BUDGET_CODE)
        except WindowBudgetError:
            return _UnitResult("failed", attempt, OUTPUT_INVALID_CODE)
        except ModelUnavailableError as exc:
            raise _Halt("circuit") from exc
        except CallRecordError as exc:
            raise _Halt("storage") from exc
        except ModelAuthError as exc:
            raise _Halt("auth") from exc
        except ModelError:
            last = MODEL_ERROR_CODE
            continue
        if isinstance(outcome, str):
            if outcome == BUDGET_CODE:
                return _UnitResult("failed", attempt, BUDGET_CODE)
            last = outcome
            continue
        return _UnitResult("done", attempt, None, outcome)
    return _UnitResult("failed", limits.chunk_max_attempts, last)


def _extract_chunk(
    toolkit: ExtractionToolkit, lease: Lease, limits: ExtractLimits, chunk: StoredChunk
) -> _UnitResult:
    identity = _identity(chunk)
    coverage = None

    def report(value):
        nonlocal coverage
        coverage = value

    def body(client: ModelClient) -> Mapping[str, object] | str:
        if toolkit.window_policy is not None:
            candidates, error = windowed.extract_entities(toolkit.entities(client), SourceChunk(identity,chunk.text),
                toolkit.window_policy, report, gleaner=None if toolkit.gleaner is None else toolkit.gleaner(client))
            if error is not None:
                return error
        else:
            extraction = toolkit.entities(client).extract(identity, chunk.text)
            if not extraction.ok:
                return OUTPUT_INVALID_CODE
            candidates = extraction.candidates
        if toolkit.gleaner is not None and toolkit.window_policy is None:
            gleaned = toolkit.gleaner(client).glean(identity, chunk.text, candidates,
                                                   preserve_mentions=toolkit.preserve_mentions)
            if gleaned.error_code is not None:
                return gleaned.error_code
            if not gleaned.ok:
                return OUTPUT_INVALID_CODE
            candidates = candidates + gleaned.added
        if toolkit.preserve_mentions:
            # An ordinal distinguishes unresolved outputs; it is not a guessed text position.
            candidates = tuple(replace(c, occurrence_index=i) if c.source.evidence_ambiguous else c
                               for i, c in enumerate(candidates))
        result: dict[str, object] = {"entities": [_encode_entity(candidate) for candidate in candidates]}
        if toolkit.preserve_mentions:
            result["entity_identity_version"] = 2
        return result

    result = _attempts(limits, lease, chunk.chunk_id, toolkit, body)
    return _with_coverage(result, toolkit, coverage)


def _with_coverage(result, toolkit, coverage):
    if toolkit.window_policy is None:
        return result
    if coverage is None:
        coverage = dict(version=1,status='partial',reason='request_not_completed',
                        planned_windows=None,completed_windows=0,input_digest=None)
    return replace(result,metadata={'window_policy':asdict(toolkit.window_policy), 'window_coverage':coverage})


def _extract_section(
    toolkit: ExtractionToolkit,
    lease: Lease,
    limits: ExtractLimits,
    section: _Section,
    entities: Sequence[SectionEntity],
    *, task_entities: Sequence[TaskEntity] = (),
) -> _UnitResult:
    chunks = tuple(SourceChunk(_identity(chunk), chunk.text) for chunk in section.chunks)
    analysis = None
    coverage = None

    def report(value):
        nonlocal coverage
        coverage = value
    prepared = None
    if toolkit.window_policy is not None:
        probe = _AttemptClient(toolkit.policy,CallAttribution(course_id=lease.course_id,task_id=lease.task_id),
            guard=toolkit.guard,max_input_bytes=toolkit.window_policy.max_input_bytes)
        try:
            prepared = windowed.plan_relations(toolkit.relations(probe),entities,chunks,toolkit.window_policy,report)
        except WindowBudgetError:
            return _with_coverage(_UnitResult('failed',1,OUTPUT_INVALID_CODE),toolkit,coverage)
    if toolkit.preserve_mentions:
        client = _AttemptClient(toolkit.policy, CallAttribution(course_id=lease.course_id,
            task_id=lease.task_id, task_attempt=lease.attempt, chunk_attempt=1, user_id=toolkit.user_id),
            guard=toolkit.guard)
        try:
            resolver = None if toolkit.resolver is None else toolkit.resolver(client)
            analysis = analyze_section(task_entities, {c.chunk_id: c for c in section.chunks},
                                       resolver=resolver, max_pairs=toolkit.analysis_max_pairs)
        except ModelUnavailableError as exc:
            raise _Halt("circuit") from exc
        except CallRecordError as exc:
            raise _Halt("storage") from exc
        except ModelAuthError as exc:
            raise _Halt("auth") from exc

    def body(client: ModelClient) -> Mapping[str, object] | str:
        if toolkit.window_policy is not None:
            candidates, error = windowed.extract_relations(toolkit.relations(client),lease.course_id,entities,chunks,
                                                           toolkit.window_policy,report,prepared=prepared)
            if error is not None:
                return error
        else:
            extraction = toolkit.relations(client).extract(lease.course_id, entities, chunks)
            if not extraction.ok:
                return OUTPUT_INVALID_CODE
            candidates = extraction.candidates
        return {
            "chunk_ids": [chunk.chunk_id for chunk in section.chunks],
            "relations": [_encode_relation(candidate) for candidate in candidates],
        }

    result = _attempts(limits, lease, None, toolkit, body)
    if result.result is not None and analysis is not None:
        result = replace(result, result={**result.result, "analysis": analysis})
    return _with_coverage(result, toolkit, coverage)
