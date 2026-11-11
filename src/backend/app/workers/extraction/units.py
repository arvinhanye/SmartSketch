"""Internal extraction.units responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
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
)

# ---------------------------------------------------------------- 模型调用


class _AttemptClient:
    """一次块/小节尝试的客户端：修复调用走 ``is_repair=True`` 的绑定，各自独立记录（E04 交接）。"""

    def __init__(self, policy: ModelCallPolicy, attribution: CallAttribution) -> None:
        self._main = policy.bind(attribution)
        self._repair = policy.bind(replace(attribution, is_repair=True))

    def _pick(self, request: ModelRequest) -> ModelClient:
        return self._repair if request.purpose == REPAIR_PURPOSE else self._main

    def complete(self, request: ModelRequest) -> ModelResult:
        return self._pick(request).complete(request)

    def stream(self, request: ModelRequest) -> Iterable[StreamEvent]:
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
        )
        try:
            outcome = body(client)
        except BudgetExceededError:
            return _UnitResult("failed", attempt, BUDGET_CODE)
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

    def body(client: ModelClient) -> Mapping[str, object] | str:
        extraction = toolkit.entities(client).extract(identity, chunk.text)
        if not extraction.ok:
            return OUTPUT_INVALID_CODE
        candidates = extraction.candidates
        if toolkit.gleaner is not None:
            gleaned = toolkit.gleaner(client).glean(identity, chunk.text, candidates)
            if gleaned.error_code is not None:
                return gleaned.error_code
            if not gleaned.ok:
                return OUTPUT_INVALID_CODE
            candidates = candidates + gleaned.added
        return {"entities": [_encode_entity(candidate) for candidate in candidates]}

    return _attempts(limits, lease, chunk.chunk_id, toolkit, body)


def _extract_section(
    toolkit: ExtractionToolkit,
    lease: Lease,
    limits: ExtractLimits,
    section: _Section,
    entities: Sequence[SectionEntity],
) -> _UnitResult:
    chunks = tuple(SourceChunk(_identity(chunk), chunk.text) for chunk in section.chunks)

    def body(client: ModelClient) -> Mapping[str, object] | str:
        extraction = toolkit.relations(client).extract(lease.course_id, entities, chunks)
        if not extraction.ok:
            return OUTPUT_INVALID_CODE
        return {
            "chunk_ids": [chunk.chunk_id for chunk in section.chunks],
            "relations": [_encode_relation(candidate) for candidate in extraction.candidates],
        }

    return _attempts(limits, lease, None, toolkit, body)
