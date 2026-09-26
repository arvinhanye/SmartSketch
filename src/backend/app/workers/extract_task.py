"""E12：``extracting`` 阶段编排与块检查点（specs/task-processing.md §4、§5、§6、§8.2～§8.4；ADR-011；
E04/E05/E06/E11 交接的调用约定）。

输入是 D11 推进到 ``extracting``、仍由本 worker 持有的租约（或接管后重新领到的同阶段任务）。
``run_extract_stage``：

1. **阶段开头**：按令牌读任务行；令牌失效 → ``lost``（不写）。课程/资料与租约不符或不在 ``extracting`` →
   ``ValueError``（调用方缺陷）。取消标志已为真 → T8。块取自本任务关联的资料修订（D10）。
2. **块阶段**：跳过已有检查点的块（接管续跑，LEASE-2）；其余块在线程池中并发处理，同时在途的块数不超过
   ``LLM_MAX_CONCURRENCY``（每块同一时刻最多一次模型调用，因此也是调用并发上限）。每块最多
   ``TASK_CHUNK_MAX_ATTEMPTS`` 次尝试（L2），每次尝试用 E04 ``bind`` 一个带归属的客户端，调用 E05
   实体抽取，E06 补漏（装配时启用）在同一次尝试内。尝试失败只重试这一块。
   - 输出不合规（E05/E06 修复一次后仍坏）→ 该次尝试失败，耗尽后块失败码 ``EXTRACTION_INCOMPLETE``；
   - 其余模型调用错误（L1 已在 E04 内做完）→ 同上，失败码 ``LLM_UNAVAILABLE``；
   - ``BudgetExceededError`` → 块立即失败 ``BUDGET_EXCEEDED``，不再重试（预算不会自己恢复）；
   - ``ModelUnavailableError``（熔断打开）→ 当前块**不记失败**，停止派发，阶段级临时故障主动释放（LEASE-6）；
   - ``CallRecordError`` → 存储不可用，同样主动释放。
3. **检查点**：每块结束在一个 C09 ``leased_transaction`` 内先读取消标志——为真则不写该块结果（在途调用的
   结果被丢弃，§4「生效时延」），随后 T8；否则写 ``task_chunk_checkpoints`` 并上报阶段内进度。
   失败块一旦使 ``失败块数 / 总块数`` 超过阈值（精确十进制比较）即提前判定 T9，不再为剩余块花钱，
   结论与跑完全部块时相同（§5）；超阈值时若失败块全是 ``LLM_UNAVAILABLE`` 用该码，否则
   ``EXTRACTION_INCOMPLETE``，``details`` 含 ``chunks_failed``、``chunks_total``、``threshold`` 与 ``by_code``。
4. **小节关系**（E11 第二阶段）：成功块按「资料修订 + 章节标题路径」分组为小节；每个小节的实体表取该小节
   成功块的候选，按 ``task_entity_id``（任务 + 规范化名称）去重，作为任务内临时实体 ID。每个小节一个
   检查点，重试与错误映射同块阶段。小节关系失败只记检查点，**不计入**失败块阈值（ArvinHan 2026-09-26）。
5. **阶段边界**：C08 ``stage_done``——取消 → T8，否则带令牌与 ``cancel_requested = 0`` 条件 T4
   ``extracting → merging``，租约继续持有。

跨任务/草稿融合（E08～E10、D-08 阈值）属于 ``merging``，不在本阶段；``load_candidates`` 读出的
「待持久化候选」只含本任务内去重后的实体、关系和失败清单。失败与释放的写入同 D11：带令牌条件并清空
租约；错误消息固定，日志只记异常类型名，不含原文。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeVar

from app.config import Settings
from app.repositories.chunks import (
    StoredChunk,
    _sources_from_json,
    _sources_json,
    get_chunks,
    list_chunks,
    list_task_revisions,
)
from app.repositories.extraction_checkpoints import Checkpoint, read_checkpoints, write_checkpoint
from app.repositories.sqlite import connect
from app.repositories.task_leases import (
    Lease,
    LeaseLost,
    ReclaimResult,
    claim_next,
    leased_transaction,
    reclaim_expired,
    release_after_transient_failure,
    release_on_shutdown,
)
from app.repositories.tasks import read_leased_task
from app.services.ai.client import ModelClient, ModelError, ModelRequest, ModelResult, StreamEvent
from app.services.ai.entities import REPAIR_PURPOSE, EntityCandidate, EntityExtractor, EntitySource
from app.services.ai.gleaning import EntityGleaner, entity_name_key
from app.services.ai.policy import (
    BudgetExceededError,
    CallAttribution,
    CallRecordError,
    ModelCallPolicy,
    ModelUnavailableError,
)
from app.services.ai.relations import (
    RelationCandidate,
    RelationExtractor,
    RelationSource,
    SectionEntity,
    SourceChunk,
)
from app.services.chunk_identity import ChunkIdentity, split_chunk_id, text_sha256
from app.services.file_storage import FileStorage
from app.services.task_state import (
    Applied,
    TaskError,
    TaskState,
    TransitionEvent,
    apply_event,
    stage_progress_range,
)
from app.workers.parse_task import LeaseHeartbeat, ParseOutcome, ParseStatus, default_owner, run_parse_stage

__all__ = [
    "ExtractLimits",
    "ExtractOutcome",
    "ExtractStatus",
    "ExtractionCandidates",
    "ExtractionToolkit",
    "FailedChunk",
    "FailedSection",
    "RunOnceResult",
    "TaskEntity",
    "exceeds_threshold",
    "load_candidates",
    "run_extract_stage",
    "run_once",
    "task_entity_id",
]

logger = logging.getLogger(__name__)

STAGE = "extracting"
NEXT_STAGE = "merging"
#: 块阶段占本阶段进度区间的份额，其余留给小节关系。
CHUNK_PROGRESS_SHARE = 0.8

OUTPUT_INVALID_CODE = "EXTRACTION_INCOMPLETE"
MODEL_ERROR_CODE = "LLM_UNAVAILABLE"
BUDGET_CODE = "BUDGET_EXCEEDED"

_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_MESSAGES = {
    "EXTRACTION_INCOMPLETE": "抽取失败的块超过允许比例",
    "LLM_UNAVAILABLE": "模型服务不可用，抽取失败的块超过允许比例",
    "INTERNAL_ERROR": "抽取阶段发生未预期的错误",
}


# ---------------------------------------------------------------- 公开数据结构


class ExtractStatus(StrEnum):
    ADVANCED = "advanced"  # T4：到 merging，仍持有租约
    CANCELLED = "cancelled"  # T8
    FAILED = "failed"  # T9：EXTRACTION_INCOMPLETE / LLM_UNAVAILABLE / 耗尽码 / INTERNAL_ERROR
    RELEASED = "released"  # 阶段级临时故障：已主动释放并退避，stage 不变
    LOST = "lost"  # 令牌已失效：此后未做任何写入


@dataclass(frozen=True)
class ExtractOutcome:
    status: ExtractStatus
    task_id: str
    stage: str | None
    sse_event: str | None
    chunks_total: int = 0
    chunks_done: int = 0
    chunks_failed: int = 0
    sections_total: int = 0
    sections_failed: int = 0
    error_code: str | None = None
    not_before: int | None = None


def _is_int(value: object) -> bool:
    return type(value) is int


@dataclass(frozen=True)
class ExtractLimits:
    """§5、§8.3 的阈值与并发上限；``from_settings`` 取 A07 登记的环境变量。"""

    max_attempts: int
    chunk_max_attempts: int = 2
    max_failed_ratio: float = 0.2
    max_concurrency: int = 4

    def __post_init__(self) -> None:
        for name in ("max_attempts", "chunk_max_attempts", "max_concurrency"):
            value = getattr(self, name)
            if not _is_int(value) or value < 1:
                raise ValueError(f"{name} must be an int >= 1")
        ratio = self.max_failed_ratio
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio < 1:
            raise ValueError("max_failed_ratio must be in [0, 1)")

    @classmethod
    def from_settings(cls, settings: Settings) -> ExtractLimits:
        return cls(
            max_attempts=settings.TASK_MAX_ATTEMPTS,
            chunk_max_attempts=settings.TASK_CHUNK_MAX_ATTEMPTS,
            max_failed_ratio=settings.TASK_MAX_FAILED_CHUNK_RATIO,
            max_concurrency=settings.LLM_MAX_CONCURRENCY,
        )


@dataclass(frozen=True)
class ExtractionToolkit:
    """每进程一份：共享熔断状态的 E04 策略，以及把一个已绑定客户端变成抽取服务的工厂。"""

    policy: ModelCallPolicy
    entities: Callable[[ModelClient], EntityExtractor]
    relations: Callable[[ModelClient], RelationExtractor]
    gleaner: Callable[[ModelClient], EntityGleaner] | None = None


@dataclass(frozen=True)
class TaskEntity:
    """任务内去重后的实体：同一规范化名称的全部候选（各自带出处）。名称与类型取首次出现者。"""

    entity_id: str
    name: str = field(repr=False)
    type: str
    candidates: tuple[EntityCandidate, ...] = field(repr=False)


@dataclass(frozen=True)
class FailedChunk:
    """契约 ``FailedChunk`` 的来源：块 ID、最终错误码与原文定位。"""

    chunk_id: str
    code: str
    page: int | None
    section_path: str | None


@dataclass(frozen=True)
class FailedSection:
    section_id: str
    code: str
    section_path: str | None
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionCandidates:
    """待持久化候选（交 ``merging``/F04/F13）。按块、小节的文档顺序排列。"""

    entities: tuple[TaskEntity, ...]
    relations: tuple[RelationCandidate, ...]
    failed_chunks: tuple[FailedChunk, ...]
    failed_sections: tuple[FailedSection, ...]


def task_entity_id(task_id: str, name: str) -> str:
    """任务内临时实体 ID：任务 + E06 规范化名称键（NFKC、casefold、去空白）的摘要。"""
    digest = hashlib.sha256(json.dumps([task_id, entity_name_key(name)], ensure_ascii=False).encode("utf-8"))
    return "tent_" + digest.hexdigest()[:32]


def exceeds_threshold(failed: int, total: int, ratio: float) -> bool:
    """§5：``failed / total > ratio``。阈值按其十进制写法精确比较（0.29 即 29/100）。"""
    if total <= 0:
        raise ValueError("total must be positive")
    return Decimal(failed) > Decimal(repr(ratio)) * total


# ---------------------------------------------------------------- 候选编解码


def _source_json(source: EntitySource | RelationSource) -> dict[str, object]:
    return {
        "document_id": source.document_id,
        "revision_id": source.revision_id,
        "chunk_id": source.chunk_id,
        "evidence_start": source.evidence_start,
        "evidence_end": source.evidence_end,
        "sources": json.loads(_sources_json(source.sources)),
    }


def _source_fields(course_id: str, raw: Mapping[str, object]) -> dict[str, object]:
    return {
        "course_id": course_id,
        "document_id": raw["document_id"],
        "revision_id": raw["revision_id"],
        "chunk_id": raw["chunk_id"],
        "evidence_start": raw["evidence_start"],
        "evidence_end": raw["evidence_end"],
        "sources": _sources_from_json(json.dumps(raw["sources"])),
    }


def _encode_entity(candidate: EntityCandidate) -> dict[str, object]:
    return {
        "name": candidate.name,
        "type": candidate.type,
        "definition": candidate.definition,
        "evidence": candidate.evidence,
        "confidence": candidate.confidence,
        "source": _source_json(candidate.source),
    }


def _decode_entity(course_id: str, raw: Mapping[str, object]) -> EntityCandidate:
    return EntityCandidate(
        name=raw["name"],  # type: ignore[arg-type]
        type=raw["type"],  # type: ignore[arg-type]
        definition=raw["definition"],  # type: ignore[arg-type]
        evidence=raw["evidence"],  # type: ignore[arg-type]
        confidence=raw["confidence"],  # type: ignore[arg-type]
        source=EntitySource(**_source_fields(course_id, raw["source"])),  # type: ignore[arg-type]
    )


def _encode_relation(candidate: RelationCandidate) -> dict[str, object]:
    return {
        "from_id": candidate.from_id,
        "to_id": candidate.to_id,
        "type": candidate.type,
        "evidence": candidate.evidence,
        "confidence": candidate.confidence,
        "source": _source_json(candidate.source),
    }


def _decode_relation(course_id: str, raw: Mapping[str, object]) -> RelationCandidate:
    return RelationCandidate(
        from_id=raw["from_id"],  # type: ignore[arg-type]
        to_id=raw["to_id"],  # type: ignore[arg-type]
        type=raw["type"],  # type: ignore[arg-type]
        evidence=raw["evidence"],  # type: ignore[arg-type]
        confidence=raw["confidence"],  # type: ignore[arg-type]
        source=RelationSource(**_source_fields(course_id, raw["source"])),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- 块与小节


@dataclass(frozen=True)
class _Section:
    section_id: str
    order: tuple[str, int]
    path: str | None
    chunks: tuple[StoredChunk, ...]


def _chunk_order(chunk_id: str) -> tuple[str, int]:
    return split_chunk_id(chunk_id)


def _identity(chunk: StoredChunk) -> ChunkIdentity:
    return ChunkIdentity(
        course_id=chunk.course_id,
        document_id=chunk.material_id,
        revision_id=chunk.revision_id,
        chunk_id=chunk.chunk_id,
        ordinal=chunk.ordinal,
        text_sha256=text_sha256(chunk.text),
        sources=chunk.sources,
    )


def _task_chunks(sqlite_url: str, course_id: str, task_id: str) -> tuple[StoredChunk, ...]:
    chunks: list[StoredChunk] = []
    for revision in list_task_revisions(sqlite_url, course_id=course_id, task_id=task_id):
        chunks.extend(list_chunks(sqlite_url, course_id=course_id, revision_id=revision.revision_id))
    return tuple(sorted(chunks, key=lambda chunk: (chunk.revision_id, chunk.ordinal)))


def _section_path(titles: Sequence[str]) -> str | None:
    return " > ".join(titles) if titles else None


def _sections(chunks: Iterable[StoredChunk]) -> tuple[_Section, ...]:
    grouped: dict[tuple[str, tuple[str, ...]], list[StoredChunk]] = {}
    for chunk in chunks:
        grouped.setdefault((chunk.revision_id, tuple(chunk.section_titles)), []).append(chunk)
    sections = []
    for (revision_id, titles), members in grouped.items():
        digest = hashlib.sha256(json.dumps([revision_id, list(titles)], ensure_ascii=False).encode("utf-8"))
        members.sort(key=lambda chunk: chunk.ordinal)
        sections.append(
            _Section("sec_" + digest.hexdigest(), (revision_id, members[0].ordinal), _section_path(titles),
                     tuple(members))
        )
    return tuple(sorted(sections, key=lambda section: section.order))


def _group_entities(
    task_id: str, course_id: str, checkpoints: Iterable[Checkpoint]
) -> tuple[TaskEntity, ...]:
    ordered = sorted((c for c in checkpoints if c.status == "done"), key=lambda c: _chunk_order(c.unit_id))
    names: dict[str, tuple[str, str]] = {}
    grouped: dict[str, list[EntityCandidate]] = {}
    for checkpoint in ordered:
        assert checkpoint.result is not None
        for raw in checkpoint.result["entities"]:  # type: ignore[union-attr]
            candidate = _decode_entity(course_id, raw)
            entity_id = task_entity_id(task_id, candidate.name)
            names.setdefault(entity_id, (candidate.name, candidate.type))
            grouped.setdefault(entity_id, []).append(candidate)
    return tuple(
        TaskEntity(entity_id, names[entity_id][0], names[entity_id][1], tuple(candidates))
        for entity_id, candidates in grouped.items()
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


class _Halt(Exception):
    """阶段级临时故障：``circuit``（熔断打开）或 ``storage``（调用记录写不进）。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class _UnitResult:
    status: str
    attempts: int
    error_code: str | None
    result: Mapping[str, object] | None = field(default=None, repr=False)


def _attempts(
    limits: ExtractLimits, lease: Lease, chunk_id: str | None, toolkit: ExtractionToolkit,
    body: Callable[[ModelClient], Mapping[str, object] | str],
) -> _UnitResult:
    """L2：最多 ``chunk_max_attempts`` 次；``body`` 返回结果或输出不合规的失败码。"""
    last = OUTPUT_INVALID_CODE
    for attempt in range(1, limits.chunk_max_attempts + 1):
        client = _AttemptClient(
            toolkit.policy,
            CallAttribution(
                course_id=lease.course_id,
                task_id=lease.task_id,
                chunk_id=chunk_id,
                task_attempt=lease.attempt,
                chunk_attempt=attempt,
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


# ---------------------------------------------------------------- 带令牌的读写


def _state_in(database: sqlite3.Connection, lease: Lease) -> TaskState:
    row = read_leased_task(database, lease.task_id, lease.token)
    if row is None:
        raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    return TaskState(row.stage, row.progress, row.cancel_requested)


def _write_progress(database: sqlite3.Connection, lease: Lease, state: TaskState, progress: float) -> None:
    decision = apply_event(state, TransitionEvent("progress", progress=progress))
    if not isinstance(decision, Applied) or not decision.changed:
        return  # 低于当前值（接管后）或超出区间：不写（I2）
    database.execute(
        f"""UPDATE processing_tasks SET progress = ?, updated_at = {_NOW_TEXT}
            WHERE id = ? AND lease_token = ? AND stage = ? AND progress <= ?""",
        (decision.state.progress, lease.task_id, lease.token, STAGE, decision.state.progress),
    )


def _write_unit(
    sqlite_url: str, lease: Lease, kind: str, unit_id: str, result: _UnitResult, progress: float
) -> bool:
    """块/小节边界：取消标志为真 → 不写并返回 ``False``；否则写检查点与进度。"""
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        state = _state_in(database, lease)
        if state.stage != STAGE:
            raise RuntimeError(f"task {lease.task_id} left the {STAGE} stage under this lease")
        if state.cancel_requested:
            return False
        write_checkpoint(
            database,
            task_id=lease.task_id,
            course_id=lease.course_id,
            unit_kind=kind,  # type: ignore[arg-type]
            unit_id=unit_id,
            status=result.status,  # type: ignore[arg-type]
            attempts=result.attempts,
            error_code=result.error_code,
            result=result.result,
        )
        _write_progress(database, lease, state, progress)
    return True


def _boundary(sqlite_url: str, lease: Lease, event: str) -> TaskState:
    """C08 ``checkpoint``/``stage_done``：取消 → T8（清空租约）；``stage_done`` 否则 T4。"""
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        decision = apply_event(_state_in(database, lease), TransitionEvent(event))
        if not isinstance(decision, Applied):
            raise RuntimeError(f"{event} rejected for task {lease.task_id}: {decision.reason}")
        state = decision.state
        if state.stage == "cancelled":
            changed = database.execute(
                f"""UPDATE processing_tasks
                    SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 1""",
                (lease.task_id, lease.token, STAGE),
            ).rowcount
        elif state.stage == NEXT_STAGE:
            changed = database.execute(
                f"""UPDATE processing_tasks SET stage = ?, progress = ?, updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 0""",
                (NEXT_STAGE, state.progress, lease.task_id, lease.token, STAGE),
            ).rowcount
        else:
            return state
        if changed != 1:
            raise RuntimeError(f"{event} compare-and-swap on task {lease.task_id} matched no row")
    return state


def _fail(
    sqlite_url: str, lease: Lease, code: str, details: Mapping[str, object] | None, counts: Mapping[str, int]
) -> ExtractOutcome:
    message = _MESSAGES[code]
    error = TaskError(code, message, details)
    encoded = None if details is None else json.dumps(dict(details), ensure_ascii=False, sort_keys=True)
    try:
        with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
            decision = apply_event(_state_in(database, lease), TransitionEvent("fail", error=error))
            if not isinstance(decision, Applied):
                raise RuntimeError(f"fail rejected for task {lease.task_id}: {decision.reason}")
            changed = database.execute(
                f"""UPDATE processing_tasks
                    SET stage = 'failed', error_code = ?, error_message = ?, error_details = ?,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                        updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ?""",
                (code, message, encoded, lease.task_id, lease.token, STAGE),
            ).rowcount
            if changed != 1:
                raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    except LeaseLost:
        return _lost(lease)
    return ExtractOutcome(ExtractStatus.FAILED, lease.task_id, "failed", "error", error_code=code, **counts)


def _release(sqlite_url: str, lease: Lease, code: str, max_attempts: int, counts: Mapping[str, int]) -> ExtractOutcome:
    released = release_after_transient_failure(
        sqlite_url, lease.task_id, lease.token, code=code, max_attempts=max_attempts
    )
    if released.status == "released":
        return ExtractOutcome(ExtractStatus.RELEASED, lease.task_id, STAGE, None, not_before=released.not_before,
                              **counts)
    if released.status == "failed":
        return ExtractOutcome(ExtractStatus.FAILED, lease.task_id, "failed", "error", error_code=code, **counts)
    return _lost(lease)


def _lost(lease: Lease) -> ExtractOutcome:
    return ExtractOutcome(ExtractStatus.LOST, lease.task_id, None, None)


# ---------------------------------------------------------------- 并发派发

_U = TypeVar("_U")


class _Dispatcher(Generic[_U]):
    """在线程池里处理单元，主线程按完成顺序在块边界写检查点；在途上限 ``limit``。

    ``halt`` 取值：``cancel``（边界读到取消标志）、``lost``、``threshold``（``after_write`` 判定）、
    ``circuit``/``storage``（阶段级临时故障）。出现后不再派发；``cancel``/``lost``/``threshold`` 之后
    完成的单元不写检查点，``circuit``/``storage`` 之后正常完成的单元照常写入（结果有效）。
    """

    def __init__(
        self,
        units: Sequence[_U],
        *,
        limit: int,
        work: Callable[[_U], _UnitResult],
        write: Callable[[_U, _UnitResult], bool],
        after_write: Callable[[_U, _UnitResult], bool],
        order: Callable[[_U], object],
    ) -> None:
        self._units = iter(units)
        self._limit = limit
        self._work = work
        self._write = write
        self._after_write = after_write
        self._order = order
        self.halt: str | None = None

    def run(self) -> str | None:
        inflight: dict[Future[_UnitResult], _U] = {}
        with ThreadPoolExecutor(max_workers=self._limit, thread_name_prefix="extract") as pool:
            self._fill(pool, inflight)
            while inflight:
                finished, _ = wait(tuple(inflight), return_when=FIRST_COMPLETED)
                for future in sorted(finished, key=lambda f: self._order(inflight[f])):  # type: ignore[arg-type]
                    unit = inflight.pop(future)
                    self._settle(unit, future)
                self._fill(pool, inflight)
        return self.halt

    def _fill(self, pool: ThreadPoolExecutor, inflight: dict[Future[_UnitResult], _U]) -> None:
        while self.halt is None and len(inflight) < self._limit:
            unit = next(self._units, None)
            if unit is None:
                return
            inflight[pool.submit(self._work, unit)] = unit

    def _settle(self, unit: _U, future: Future[_UnitResult]) -> None:
        try:
            result = future.result()
        except _Halt as halt:
            self.halt = self.halt or halt.reason
            return
        if self.halt in ("cancel", "lost", "threshold"):
            return
        try:
            if not self._write(unit, result):
                self.halt = "cancel"
                return
        except LeaseLost:
            self.halt = "lost"
            return
        except sqlite3.OperationalError:
            self.halt = self.halt or "storage"
            return
        if self.halt is None and self._after_write(unit, result):
            self.halt = "threshold"


# ---------------------------------------------------------------- 阶段编排


@dataclass
class _Progress:
    chunks_total: int
    chunks_done: int = 0
    chunks_failed: int = 0
    sections_total: int = 0
    sections_failed: int = 0
    by_code: Counter[str] = field(default_factory=Counter)

    def counts(self) -> dict[str, int]:
        return {
            "chunks_total": self.chunks_total,
            "chunks_done": self.chunks_done,
            "chunks_failed": self.chunks_failed,
            "sections_total": self.sections_total,
            "sections_failed": self.sections_failed,
        }


def _threshold_failure(
    sqlite_url: str, lease: Lease, limits: ExtractLimits, progress: _Progress
) -> ExtractOutcome:
    codes = dict(sorted(progress.by_code.items()))
    code = MODEL_ERROR_CODE if set(codes) == {MODEL_ERROR_CODE} else OUTPUT_INVALID_CODE
    details: dict[str, object] = {
        "chunks_failed": progress.chunks_failed,
        "chunks_total": progress.chunks_total,
        "threshold": limits.max_failed_ratio,
    }
    if code == OUTPUT_INVALID_CODE:
        details["by_code"] = codes
    return _fail(sqlite_url, lease, code, details, progress.counts())


def _halted(
    sqlite_url: str, lease: Lease, limits: ExtractLimits, progress: _Progress, halt: str
) -> ExtractOutcome:
    counts = progress.counts()
    if halt == "lost":
        return _lost(lease)
    if halt == "cancel":
        _boundary(sqlite_url, lease, "checkpoint")
        return ExtractOutcome(ExtractStatus.CANCELLED, lease.task_id, "cancelled", "cancelled", **counts)
    if halt == "threshold":
        return _threshold_failure(sqlite_url, lease, limits, progress)
    code = MODEL_ERROR_CODE if halt == "circuit" else "STORAGE_UNAVAILABLE"
    logger.warning("extracting task %s: stage-level fault (%s), releasing", lease.task_id, halt)
    return _release(sqlite_url, lease, code, limits.max_attempts, counts)


def _run(sqlite_url: str, lease: Lease, toolkit: ExtractionToolkit, limits: ExtractLimits) -> ExtractOutcome:
    chunks = _task_chunks(sqlite_url, lease.course_id, lease.task_id)
    if not chunks:
        raise RuntimeError(f"task {lease.task_id} reached {STAGE} without source chunks")
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    with connect(sqlite_url) as database:
        existing = read_checkpoints(database, course_id=lease.course_id, task_id=lease.task_id)
    done_chunks = {c.unit_id: c for c in existing if c.unit_kind == "chunk" and c.unit_id in by_id}
    done_sections = {c.unit_id for c in existing if c.unit_kind == "section"}

    progress = _Progress(len(chunks))
    lower, upper = stage_progress_range(STAGE)
    width = upper - lower

    def count(result: _UnitResult) -> None:
        progress.chunks_done += 1
        if result.status == "failed":
            progress.chunks_failed += 1
            progress.by_code[result.error_code or OUTPUT_INVALID_CODE] += 1

    for checkpoint in done_chunks.values():
        count(_UnitResult(checkpoint.status, checkpoint.attempts, checkpoint.error_code))
    ratio = limits.max_failed_ratio

    # -- 块阶段
    if progress.chunks_failed == 0 or not exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio):

        def write_chunk(chunk: StoredChunk, result: _UnitResult) -> bool:
            share = (progress.chunks_done + 1) / progress.chunks_total
            written = _write_unit(sqlite_url, lease, "chunk", chunk.chunk_id, result,
                                  lower + width * CHUNK_PROGRESS_SHARE * share)
            if written:
                count(result)
            return written

        halt = _Dispatcher(
            [chunk for chunk in chunks if chunk.chunk_id not in done_chunks],
            limit=limits.max_concurrency,
            work=lambda chunk: _extract_chunk(toolkit, lease, limits, chunk),
            write=write_chunk,
            after_write=lambda _chunk, _result: exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio),
            order=lambda chunk: (chunk.revision_id, chunk.ordinal),
        ).run()
        if halt is not None:
            return _halted(sqlite_url, lease, limits, progress, halt)
    if exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio):
        return _threshold_failure(sqlite_url, lease, limits, progress)

    # -- 小节关系
    with connect(sqlite_url) as database:
        chunk_checkpoints = read_checkpoints(database, course_id=lease.course_id, task_id=lease.task_id,
                                             unit_kind="chunk")
    succeeded = {c.unit_id: c for c in chunk_checkpoints if c.status == "done"}
    sections = _sections(by_id[chunk_id] for chunk_id in succeeded if chunk_id in by_id)
    progress.sections_total = len(sections)
    with connect(sqlite_url) as database:
        for checkpoint in read_checkpoints(database, course_id=lease.course_id, task_id=lease.task_id,
                                           unit_kind="section"):
            if checkpoint.status == "failed":
                progress.sections_failed += 1
    finished = [0 + len(done_sections)]

    def section_entities(section: _Section) -> tuple[SectionEntity, ...]:
        members = [succeeded[chunk.chunk_id] for chunk in section.chunks]
        return tuple(
            SectionEntity(entity.entity_id, lease.course_id, entity.name, entity.type)
            for entity in _group_entities(lease.task_id, lease.course_id, members)
        )

    def write_section(section: _Section, result: _UnitResult) -> bool:
        share = (finished[0] + 1) / max(progress.sections_total, 1)
        written = _write_unit(
            sqlite_url, lease, "section", section.section_id, result,
            lower + width * (CHUNK_PROGRESS_SHARE + (1 - CHUNK_PROGRESS_SHARE) * share),
        )
        if written:
            finished[0] += 1
            if result.status == "failed":
                progress.sections_failed += 1
        return written

    halt = _Dispatcher(
        [section for section in sections if section.section_id not in done_sections],
        limit=limits.max_concurrency,
        work=lambda section: _extract_section(toolkit, lease, limits, section, section_entities(section)),
        write=write_section,
        after_write=lambda _section, _result: False,  # 小节关系失败不计入阈值（ArvinHan 2026-09-26）
        order=lambda section: section.order,
    ).run()
    if halt is not None:
        return _halted(sqlite_url, lease, limits, progress, halt)

    state = _boundary(sqlite_url, lease, "stage_done")
    if state.stage == "cancelled":
        return ExtractOutcome(ExtractStatus.CANCELLED, lease.task_id, "cancelled", "cancelled", **progress.counts())
    return ExtractOutcome(ExtractStatus.ADVANCED, lease.task_id, NEXT_STAGE, "stage", **progress.counts())


def run_extract_stage(
    sqlite_url: str, lease: Lease, *, toolkit: ExtractionToolkit, limits: ExtractLimits
) -> ExtractOutcome:
    """把一个已领取的 ``extracting`` 任务推进到阶段检查点（见模块说明）。"""
    with connect(sqlite_url) as database:
        head = read_leased_task(database, lease.task_id, lease.token)
    if head is None:
        return _lost(lease)
    if (head.course_id, head.document_id) != (lease.course_id, lease.document_id):
        raise ValueError(f"lease does not match the course or material of task {lease.task_id}")
    if head.stage != STAGE:
        raise ValueError(f"task {lease.task_id} is not in the {STAGE} stage")

    try:
        if head.cancel_requested:
            _boundary(sqlite_url, lease, "checkpoint")
            return ExtractOutcome(ExtractStatus.CANCELLED, lease.task_id, "cancelled", "cancelled")
        return _run(sqlite_url, lease, toolkit, limits)
    except LeaseLost:
        return _lost(lease)
    except sqlite3.OperationalError as exc:
        logger.warning("extracting task %s: storage unavailable (%s)", lease.task_id, type(exc).__name__)
        return _release(sqlite_url, lease, "STORAGE_UNAVAILABLE", limits.max_attempts, {})
    except Exception as exc:  # noqa: BLE001 - 未预期错误一律 INTERNAL_ERROR，只记类型名
        logger.error("extracting task %s: unexpected %s", lease.task_id, type(exc).__name__)
        return _fail(sqlite_url, lease, "INTERNAL_ERROR", None, {})


# ---------------------------------------------------------------- 读取待持久化候选


def load_candidates(sqlite_url: str, *, course_id: str, task_id: str) -> ExtractionCandidates:
    """按课程隔离读出一个任务已结束单元的候选；他课任务得到空结果。"""
    with connect(sqlite_url) as database:
        checkpoints = read_checkpoints(database, course_id=course_id, task_id=task_id)
    chunk_rows = [c for c in checkpoints if c.unit_kind == "chunk"]
    section_rows = [c for c in checkpoints if c.unit_kind == "section"]
    entities = _group_entities(task_id, course_id, chunk_rows)

    failed_ids = sorted((c for c in chunk_rows if c.status == "failed"), key=lambda c: _chunk_order(c.unit_id))
    chunks: dict[str, StoredChunk] = {}
    if failed_ids:
        chunks = {c.chunk_id: c for c in get_chunks(sqlite_url, course_id=course_id,
                                                     chunk_ids=[c.unit_id for c in failed_ids])}
    failed_chunks = []
    for checkpoint in failed_ids:
        chunk = chunks.get(checkpoint.unit_id)
        locator = chunk.sources[0].locator if chunk is not None and chunk.sources else None
        failed_chunks.append(FailedChunk(
            checkpoint.unit_id,
            checkpoint.error_code or OUTPUT_INVALID_CODE,
            None if locator is None else locator.page,
            None if locator is None else locator.section_path,
        ))

    relations: list[tuple[tuple[str, int], RelationCandidate]] = []
    failed_sections = []
    known: dict[str, _Section] = {}
    if any(c.status == "failed" for c in section_rows):
        done = {c.unit_id for c in chunk_rows if c.status == "done"}
        known = {
            section.section_id: section
            for section in _sections(c for c in _task_chunks(sqlite_url, course_id, task_id) if c.chunk_id in done)
        }
    for checkpoint in section_rows:
        if checkpoint.status == "done":
            assert checkpoint.result is not None
            head = checkpoint.result["chunk_ids"][0]  # type: ignore[index]
            for raw in checkpoint.result["relations"]:  # type: ignore[union-attr]
                relations.append((_chunk_order(head), _decode_relation(course_id, raw)))
        else:
            section = known.get(checkpoint.unit_id)
            failed_sections.append(FailedSection(
                checkpoint.unit_id,
                checkpoint.error_code or OUTPUT_INVALID_CODE,
                None if section is None else section.path,
                () if section is None else tuple(chunk.chunk_id for chunk in section.chunks),
            ))
    relations.sort(key=lambda item: item[0])
    failed_sections.sort(key=lambda item: _chunk_order(item.chunk_ids[0]) if item.chunk_ids else ("", 0))
    return ExtractionCandidates(
        entities=entities,
        relations=tuple(candidate for _, candidate in relations),
        failed_chunks=tuple(failed_chunks),
        failed_sections=tuple(failed_sections),
    )


# ---------------------------------------------------------------- 运行一次


@dataclass(frozen=True)
class RunOnceResult:
    reclaimed: ReclaimResult
    lease: Lease | None
    parse: ParseOutcome | None
    extract: ExtractOutcome | None
    handed_back: bool


def run_once(
    settings: Settings,
    *,
    toolkit: ExtractionToolkit,
    owner: str | None = None,
    storage: FileStorage | None = None,
) -> RunOnceResult:
    """回收 → 领取一个任务 → ``parsing`` 与 ``extracting`` 在同一租约与心跳下连续推进。

    推进到 ``merging``，或领到本入口不处理的阶段时，以 C09 ``release_on_shutdown`` 交还（不计尝试次数），
    留给 ``merging``/``persisting`` 的 worker。
    """
    url = settings.SQLITE_URL
    store = storage or FileStorage(settings.STORAGE_DIR, settings.UPLOAD_MAX_BYTES)
    limits = ExtractLimits.from_settings(settings)
    reclaimed = reclaim_expired(url, max_attempts=settings.TASK_MAX_ATTEMPTS)
    lease = claim_next(
        url,
        owner=owner or default_owner(),
        lease_seconds=settings.TASK_LEASE_SECONDS,
        max_attempts=settings.TASK_MAX_ATTEMPTS,
    )
    if lease is None:
        return RunOnceResult(reclaimed, None, None, None, False)
    if lease.stage not in ("parsing", STAGE):
        return RunOnceResult(reclaimed, lease, None, None, release_on_shutdown(url, lease.task_id, lease.token))
    parsed: ParseOutcome | None = None
    extracted: ExtractOutcome | None = None
    with LeaseHeartbeat(url, lease, lease_seconds=settings.TASK_LEASE_SECONDS):
        current = lease
        if lease.stage == "parsing":
            parsed = run_parse_stage(url, lease, storage=store, max_attempts=settings.TASK_MAX_ATTEMPTS)
            current = replace(lease, stage=STAGE) if parsed.status is ParseStatus.ADVANCED else lease
        if current.stage == STAGE:
            extracted = run_extract_stage(url, current, toolkit=toolkit, limits=limits)
    handed_back = False
    if extracted is not None and extracted.status is ExtractStatus.ADVANCED:
        handed_back = release_on_shutdown(url, lease.task_id, lease.token)
    return RunOnceResult(reclaimed, lease, parsed, extracted, handed_back)
