"""E12：``extracting`` 阶段编排与块检查点（specs/task-processing.md §4、§5、§6、§8.2～§8.4；ADR-011；
E04/E05/E06/E11 交接的调用约定）。

输入是 D11 推进到 ``extracting``、仍由本 worker 持有的租约（或接管后重新领到的同阶段任务）。
``run_extract_stage``：

1. **阶段开头**：按令牌读任务行；令牌失效 → ``lost``（不写）。课程/资料与租约不符或不在 ``extracting`` →
   ``ValueError``（调用方缺陷）。取消标志已为真 → T8。块取自本任务关联的资料修订（D10）。
2. **块派发**：跳过已有检查点的块（接管续跑，LEASE-2）；实体块优先按文档顺序进入共享线程池。
   块与小节合计同时在途数不超过 ``LLM_MAX_CONCURRENCY``（每单元同一时刻最多一次模型调用）。每块最多
   ``TASK_CHUNK_MAX_ATTEMPTS`` 次尝试（L2），每次尝试用 E04 ``bind`` 一个带归属的客户端，调用 E05
   实体抽取，E06 补漏（装配时启用）在同一次尝试内。尝试失败只重试这一块。
   - 输出不合规（E05/E06 修复一次后仍坏）→ 该次尝试失败，耗尽后块失败码 ``EXTRACTION_INCOMPLETE``；
   - 其余模型调用错误（L1 已在 E04 内做完）→ 同上，失败码 ``LLM_UNAVAILABLE``；
   - ``BudgetExceededError`` → 块立即失败 ``BUDGET_EXCEEDED``，不再重试（预算不会自己恢复）；
   - ``ModelUnavailableError``（熔断打开）→ 当前块**不记失败**，停止派发，阶段级临时故障主动释放（LEASE-6）；
   - ``CallRecordError`` → 存储不可用，同样主动释放；
   - ``ModelAuthError``（供应商 401/403）→ 不重试，停止派发，任务 ``LLM_UNAVAILABLE`` + ``reason = auth``
     终止（块与小节阶段相同，ADR-082 决定 4）。
3. **检查点**：每块结束在一个 C09 ``leased_transaction`` 内先读取消标志——为真则不写该块结果（在途调用的
   结果被丢弃，§4「生效时延」），随后 T8；否则写 ``task_chunk_checkpoints`` 并上报阶段内进度。
   失败块一旦使 ``失败块数 / 总块数`` 超过阈值（精确十进制比较）即提前判定 T9，不再为剩余块花钱，
   结论与跑完全部块时相同（§5）；超阈值时若失败块全是 ``LLM_UNAVAILABLE`` 用该码，否则
   ``EXTRACTION_INCOMPLETE``，``details`` 含 ``chunks_failed``、``chunks_total``、``threshold`` 与 ``by_code``。
4. **小节关系**：实体派发队列为空，且剩余块全部失败仍不超阈值时，用已就绪小节填补共享池空位。
   小节的全部块结束后只保留成功块，按「资料修订 + 章节标题路径」分组；每个小节的实体表取该小节
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
# Keep legacy module attributes available alongside the explicit re-exports below.
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
from app.services.ai.client import ModelAuthError, ModelClient, ModelError, ModelRequest, ModelResult, StreamEvent
from app.services.ai.entities import REPAIR_PURPOSE, EntityCandidate, EntityExtractor, EntitySource
from app.services.ai.gleaning import EntityGleaner, entity_name_key
from app.services.ai.policy import (
    BudgetExceededError,
    CallAttribution,
    CallRecordError,
    ModelCallPolicy,
    ModelUnavailableError,
)
from app.services.credentials import CredentialUnavailable
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
from app.workers.extraction.candidates import (
    _chunk_order,
    _decode_entity,
    _decode_relation,
    _encode_entity,
    _encode_relation,
    _group_entities,
    _identity,
    _section_path,
    _sections,
    _source_fields,
    _source_json,
    _task_chunks,
    load_candidates,
    task_entity_id,
)
from app.workers.extraction.dispatch import (
    _Dispatcher,
    _U,
    _halted,
    _run,
    _threshold_failure,
)
from app.workers.extraction.state import (
    _boundary,
    _fail,
    _lost,
    _release,
    _state_in,
    _write_progress,
    _write_unit,
)
from app.workers.extraction.types import (
    AUTH_MESSAGE,
    BUDGET_CODE,
    CHUNK_PROGRESS_SHARE,
    CREDENTIAL_MESSAGE,
    ExtractLimits,
    ExtractOutcome,
    ExtractStatus,
    ExtractionCandidates,
    ExtractionToolkit,
    FailedChunk,
    FailedSection,
    MODEL_ERROR_CODE,
    NEXT_STAGE,
    OUTPUT_INVALID_CODE,
    RunOnceResult,
    STAGE,
    TaskEntity,
    _Halt,
    _MESSAGES,
    _NOW_TEXT,
    _Progress,
    _Section,
    _UnitResult,
    _is_int,
    exceeds_threshold,
    logger,
)
from app.workers.extraction.units import (
    _AttemptClient,
    _attempts,
    _extract_chunk,
    _extract_section,
)

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


def fail_for_credential(sqlite_url: str, lease: Lease, reason: str) -> ExtractOutcome:
    """ADR-080 决定 3：快照缺失、已撤销或不可解时终止任务，不重试、不换 key。"""
    return _fail(sqlite_url, lease, MODEL_ERROR_CODE, {"reason": reason}, {}, message=CREDENTIAL_MESSAGE)


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
    except CredentialUnavailable as exc:
        logger.warning("extracting task %s: credential unavailable (%s)", lease.task_id, exc.reason)
        return fail_for_credential(sqlite_url, lease, exc.reason)
    except sqlite3.OperationalError as exc:
        logger.warning("extracting task %s: storage unavailable (%s)", lease.task_id, type(exc).__name__)
        return _release(sqlite_url, lease, "STORAGE_UNAVAILABLE", limits.max_attempts, {})
    except Exception as exc:  # noqa: BLE001 - 未预期错误一律 INTERNAL_ERROR，只记类型名
        logger.error("extracting task %s: unexpected %s", lease.task_id, type(exc).__name__)
        return _fail(sqlite_url, lease, "INTERNAL_ERROR", None, {})


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
