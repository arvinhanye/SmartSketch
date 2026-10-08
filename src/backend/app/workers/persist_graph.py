"""F13：``merging``（直通）与 ``persisting`` 阶段（specs/task-processing.md §3、§8.4、§8.5；ADR-009、ADR-029）。

``merging``（直通，ArvinHan 2026-09-26 选定）：不做跨任务融合（E08～E10 与 D-08 阈值未接入），
只在阶段边界执行 C08 ``stage_done``：取消标志为真 → T8，否则 T5 进入 ``persisting``（最后一个取消点）。
本任务内的去重已在 E12 按规范化名称完成；跨资料的重复进入审核队列的「疑似重复」（§8.5 已接受）。

``persisting``（§8.4 第 1～4 步）：

1. 从检查点读出候选（``load_candidates``），把任务内实体 ``tent_…`` 映射为草稿节点
   ``kp_id = derive_kp_id(课程, 任务, tent_id)``，关系映射为 ``rel_id = derive_rel_id(课程, 类型, 起点, 终点)``。
   节点与关系状态一律 ``draft``（D-08 签收前，ArvinHan 2026-09-26 选定），置信度原值保存；缺失按 0。
2. 取课程写锁（SQLite ``course_locks``，持锁期间每 ``L/3`` 续约）。等锁上限为一个锁租约 ``L``
   （§8.5：持锁者不续约时锁在 ``L`` 内过期），仍拿不到则释放任务退避；然后读一次 V。
3. **一个 Neo4j 写事务**：锁课程守卫节点 → 撤销本任务此前尝试的全部贡献（删除因此无贡献的元素）→
   写节点（F04）→ 读「可见草稿 + 本任务」的前置边，按 ADR-009 逐环降级（可能降级其他任务的未确认 AI 边）
   → 写关系（F06）。环上无可降级边（DAG-10）→ 回滚，T9 ``CYCLE_DETECTED``。
4. 图构建后进入 SQLite 最终提交围栏，复核任务/课程锁双令牌、阶段、有效期和本地截止；
   围栏内提交显式图事务，再用同一 SQLite 连接执行 T6、分配提交序号并递增
   ``courses.draft_revision``，提交 SQLite 后释放课程写锁（ADR-091）。

失败：Neo4j/SQLite 存储故障或课程写锁等不到 → 主动释放并退避（``STORAGE_UNAVAILABLE``，尝试耗尽则 T9）；
其他错误 → T9 ``INTERNAL_ERROR``。``persisting`` 的每一种失败都置 ``cleanup_pending``，随后尝试清理
（撤销本任务贡献）；清理成功才清除标记，否则由下次回收重试（``cleanup_failed_task``）。
双租约守卫在每条图语句发送前/返回后复核；最终围栏排斥接管。不透明重跑回调。
COMMIT 发出后的故障不作为回滚证明，T6 应答/退出故障先读回确认结果。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Final

from app.config import Settings
from app.repositories import course_locks
from app.repositories.chunks import StoredChunk, get_chunks
from app.repositories.graph_nodes import DraftNode, NodeSource, NodeWriteResult, derive_kp_id, write_draft_nodes_in
from app.repositories.graph_relations import (
    DraftRelation,
    PrerequisiteEdge,
    derive_rel_id,
    downgrade_relation,
    lock_draft,
    read_prerequisite_edges,
    read_relations,
    read_visible_nodes,
    revoke_task,
    task_has_contributions,
)
from app.repositories.neo4j import GraphScope, Neo4jRepository, RepositoryError, ScopedTransaction
from app.repositories.lease_guard import LeaseGuard
from app.repositories.sqlite import connect
from app.repositories.task_leases import (
    Lease,
    LeaseLost,
    ReclaimResult,
    claim_next,
    clear_cleanup_pending,
    leased_transaction,
    persist_transaction,
    reclaim_expired,
    release_after_transient_failure,
    release_on_shutdown,
)
from app.repositories.tasks import read_effective_task_ids, read_leased_task
from app.services.ai.relations import RelationCandidate
from app.services.credentials import CredentialUnavailable
from app.services.file_storage import FileStorage
from app.services.graph.downgrade import Downgrade, UnresolvableCycleError, plan_downgrades
from app.services.graph.relations import RelationWriteError, RelationWriteResult, apply_relations
from app.services.task_state import Applied, TaskError, TaskState, TransitionEvent, apply_event
from app.workers.extract_task import (
    ExtractionCandidates,
    ExtractionToolkit,
    ExtractLimits,
    ExtractStatus,
    TaskEntity,
    fail_for_credential,
    load_candidates,
    run_extract_stage,
)
from app.workers.parse_task import LeaseHeartbeat, ParseStatus, default_owner, run_parse_stage

__all__ = [
    "AUTO_STATUS",
    "DraftPlan",
    "PersistOutcome",
    "PersistStatus",
    "PipelineResult",
    "build_plan",
    "cleanup_failed_task",
    "run_merge_stage",
    "run_persist_stage",
    "run_pipeline_once",
]

logger = logging.getLogger(__name__)

MERGE_STAGE: Final = "merging"
STAGE: Final = "persisting"
DRAFT_VERSION: Final = "draft"
#: D-08 签收前自动写入的节点与关系状态（ArvinHan 2026-09-26）。
AUTO_STATUS: Final = "draft"
STORAGE_CODE: Final = "STORAGE_UNAVAILABLE"
_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_MESSAGES = {
    "CYCLE_DETECTED": "自动候选成环，且环上没有可降级的关系",
    "INTERNAL_ERROR": "持久化阶段发生未预期的错误",
}


class PersistStatus(StrEnum):
    ADVANCED = "advanced"  # merging：T5，仍持有租约；persisting：T6，租约已清空
    CANCELLED = "cancelled"  # merging：T8
    FAILED = "failed"  # T9
    RELEASED = "released"  # 临时故障，已释放并退避
    LOST = "lost"  # 令牌失效，未再写入


@dataclass(frozen=True)
class PersistOutcome:
    status: PersistStatus
    task_id: str
    stage: str | None
    error_code: str | None = None
    not_before: int | None = None
    nodes: NodeWriteResult | None = None
    relations: RelationWriteResult | None = None
    downgraded: tuple[Downgrade, ...] = ()
    cleanup_pending: bool = False


# ---------------------------------------------------------------- 候选 → 草稿


@dataclass(frozen=True)
class DraftPlan:
    nodes: tuple[DraftNode, ...]
    relations: tuple[DraftRelation, ...] = field(default=())
    #: 关系端点实体不存在或自环而丢弃的关系候选数。
    dropped_relations: int = 0


def _confidence(value: float | None) -> float:
    return 0.0 if value is None else float(value)


def _node(course_id: str, task_id: str, entity: TaskEntity) -> DraftNode:
    sources: dict[tuple[str, int, int], NodeSource] = {}
    for candidate in entity.candidates:
        s = candidate.source
        sources.setdefault((s.chunk_id, s.evidence_start, s.evidence_end),
                           NodeSource(s.chunk_id, s.document_id, s.revision_id, s.evidence_start, s.evidence_end))
    definition = next((c.definition.strip() for c in entity.candidates if c.definition.strip()), "")
    aliases = tuple(dict.fromkeys(c.name.strip() for c in entity.candidates if c.name.strip() != entity.name.strip()))
    return DraftNode(
        kp_id=derive_kp_id(course_id, task_id, entity.entity_id),
        name=entity.name,
        type=entity.type,
        definition=definition,
        confidence=max(_confidence(c.confidence) for c in entity.candidates),
        status=AUTO_STATUS,
        aliases=aliases,
        sources=tuple(sources.values()),
    )


def build_plan(course_id: str, task_id: str, candidates: ExtractionCandidates) -> DraftPlan:
    """把 E12 候选映射为草稿节点与关系（确定性，重跑结果相同）。同一 ``rel_id`` 合并来源、取最高置信度。"""
    nodes = tuple(_node(course_id, task_id, entity) for entity in candidates.entities)
    kp_of = {entity.entity_id: node.kp_id for entity, node in zip(candidates.entities, nodes)}
    merged: dict[str, tuple[RelationCandidate, str, str, float, list[str]]] = {}
    dropped = 0
    for candidate in candidates.relations:
        a, b = kp_of.get(candidate.from_id), kp_of.get(candidate.to_id)
        if a is None or b is None or a == b:
            dropped += 1
            continue
        rel_id = derive_rel_id(course_id, candidate.type, a, b)
        confidence = _confidence(candidate.confidence)
        if rel_id in merged:
            first, _, _, best, chunk_ids = merged[rel_id]
            if candidate.source.chunk_id not in chunk_ids:
                chunk_ids.append(candidate.source.chunk_id)
            merged[rel_id] = (first, a, b, max(best, confidence), chunk_ids)
        else:
            merged[rel_id] = (candidate, a, b, confidence, [candidate.source.chunk_id])
    relations = tuple(
        DraftRelation(rel_id=rel_id, type=first.type, from_id=a, to_id=b, confidence=confidence,
                      status=AUTO_STATUS, source="ai", chunk_ids=tuple(chunk_ids))
        for rel_id, (first, a, b, confidence, chunk_ids) in merged.items()
    )
    return DraftPlan(nodes, relations, dropped)


def _source_chunk_ids(plan: DraftPlan) -> list[str]:
    ids = [s.chunk_id for node in plan.nodes for s in node.sources]
    ids.extend(chunk_id for rel in plan.relations for chunk_id in rel.chunk_ids)
    return list(dict.fromkeys(ids))


# ---------------------------------------------------------------- 单个 Neo4j 事务


@dataclass(frozen=True)
class _Written:
    nodes: NodeWriteResult
    relations: RelationWriteResult
    downgraded: tuple[Downgrade, ...]


def _write_draft(tx: ScopedTransaction, task_id: str, plan: DraftPlan, chunks: Sequence[StoredChunk]) -> _Written:
    lock_draft(tx)
    revoke_task(tx, task_id)
    nodes = write_draft_nodes_in(tx, task_id=task_id, nodes=plan.nodes, chunks=chunks)

    usable = set(nodes.written) | set(nodes.skipped_locked)
    relations = [rel for rel in plan.relations if rel.from_id in usable and rel.to_id in usable]
    visible = read_visible_nodes(tx, task_id=task_id)
    relations = [rel for rel in relations if rel.from_id in visible and rel.to_id in visible]

    # ADR-009：参与环检测的边 = 可见草稿（含本任务）的前置边 + 本任务新的前置候选。
    edges = {edge.rel_id: edge for edge in read_prerequisite_edges(tx, task_id=task_id)}
    existing = read_relations(tx, (rel.rel_id for rel in relations))
    ours: set[str] = set()
    for rel in relations:
        old = existing.get(rel.rel_id)
        if rel.type != "PREREQUISITE" or rel.rel_id in edges:
            continue
        if old is not None and (old.type != "PREREQUISITE" or (old.from_id, old.to_id) != (rel.from_id, rel.to_id)
                                or old.status == "rejected"):
            continue  # F06 沿用现有类型或跳过冲突；不参与环检测
        edges[rel.rel_id] = PrerequisiteEdge(rel.rel_id, rel.from_id, rel.to_id, rel.confidence, True)
        ours.add(rel.rel_id)
    downgrades = plan_downgrades(visible, list(edges.values()))  # UnresolvableCycleError → T9

    victims = {d.rel_id: d for d in downgrades}
    for d in downgrades:
        if d.rel_id not in ours or d.rel_id in existing:
            downgrade_relation(tx, rel_id=d.rel_id, from_id=d.from_id, to_id=d.to_id, cycle=d.cycle,
                               task_id=task_id, force=d.rel_id in existing)
    relations = [
        replace(rel, type="RELATED_TO", status="low_confidence", downgrade_cycle=victims[rel.rel_id].cycle)
        if rel.rel_id in victims else rel
        for rel in relations
    ]
    written = apply_relations(tx, relations=relations, task_id=task_id, chunks=chunks)
    return _Written(nodes, written, downgrades)


# ---------------------------------------------------------------- SQLite 边界


def _state_in(database: sqlite3.Connection, lease: Lease) -> TaskState:
    row = read_leased_task(database, lease.task_id, lease.token)
    if row is None:
        raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    return TaskState(row.stage, row.progress, row.cancel_requested)


def _check_lease(sqlite_url: str, lease: Lease) -> None:
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        state = _state_in(database, lease)
        if state.stage != STAGE:
            raise RuntimeError(f"task {lease.task_id} left the {STAGE} stage under this lease")


def _t6_in(database: sqlite3.Connection, lease: Lease) -> int:
    """T6 on the final fence's existing connection; never acquire another writer."""
    decision = apply_event(_state_in(database, lease), TransitionEvent("persisted"))
    if not isinstance(decision, Applied):
        raise RuntimeError(f"persisted rejected for task {lease.task_id}: {decision.reason}")
    row = database.execute(
        f"""UPDATE processing_tasks
            SET stage = 'awaiting_review', progress = ?,
                t6_seq = (SELECT coalesce(max(t6_seq), 0) + 1 FROM processing_tasks WHERE course_id = ?),
                lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL, updated_at = {_NOW_TEXT}
            WHERE id = ? AND lease_token = ? AND stage = ?
            RETURNING t6_seq""",
        (decision.state.progress, lease.course_id, lease.task_id, lease.token, STAGE),
    ).fetchone()
    if row is None:
        raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    # 草稿内容在 T6 变为可见：课程状态据此从 published 变为 revising（V4 draft_revision）。
    database.execute("UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", (lease.course_id,))
    return int(row[0])


def _t6(sqlite_url: str, lease: Lease) -> int:
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        return _t6_in(database, lease)


def _fail(sqlite_url: str, lease: Lease, code: str, details: Mapping[str, object] | None) -> bool:
    """T9，并置 ``cleanup_pending``。返回 ``False`` 表示租约已丢、未写。"""
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
                    SET stage = 'failed', error_code = ?, error_message = ?, error_details = ?, cleanup_pending = 1,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL, updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ?""",
                (code, message, encoded, lease.task_id, lease.token, STAGE),
            ).rowcount
            if changed != 1:
                raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    except LeaseLost:
        return False
    return True


def _effective(sqlite_url: str, course_id: str) -> tuple[str, ...]:
    with connect(sqlite_url) as database:
        return read_effective_task_ids(database, course_id)


def cleanup_failed_task(
    sqlite_url: str, repo: Neo4jRepository, *, course_id: str, task_id: str, holder: str,
    lock_seconds: int, lock_wait_seconds: float,
) -> bool:
    """ADR-092: order even empty cleanup after every prior graph decision.

    A pre-read cannot exclude a cancelled client's late server COMMIT. Clear
    the marker only after the guarded revocation commit and transport exit.
    """
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError('task_id is required')
    try:
        lock = course_locks.acquire(sqlite_url, course_id, holder=holder, lease_seconds=lock_seconds,
                                    wait_seconds=lock_wait_seconds)
        if lock is None:
            return False
        guard = LeaseGuard.from_expiry(lock_seconds, lock.expires_at)
        with course_locks.held(sqlite_url, lock, lease_seconds=lock_seconds, guard=guard):
            guard.check()
            scope = GraphScope(course_id, DRAFT_VERSION,
                               effective_task_ids=_effective(sqlite_url, course_id))
            with repo.persist_write_transaction(scope, check=guard.check, remaining=guard.remaining) as tx:
                lock_draft(tx)
                revoke_task(tx, task_id)
                try:
                    tx.commit(started_at=time.monotonic())
                except BaseException:
                    if tx.commit_started:
                        guard.lose()
                    raise
        return clear_cleanup_pending(sqlite_url, task_id, course_id=course_id)
    except (RepositoryError, sqlite3.Error, LeaseLost, RuntimeError, ValueError) as exc:
        logger.warning('cleanup of task %s failed (%s)', task_id,
                       getattr(exc, 'code', type(exc).__name__))
        return False


# ---------------------------------------------------------------- 阶段入口


def run_merge_stage(sqlite_url: str, lease: Lease) -> PersistOutcome:
    """直通 ``merging``：C08 ``stage_done`` → T5 或 T8（取消时清空租约）。"""
    try:
        with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
            decision = apply_event(_state_in(database, lease), TransitionEvent("stage_done"))
            if not isinstance(decision, Applied):
                raise RuntimeError(f"stage_done rejected for task {lease.task_id}: {decision.reason}")
            state = decision.state
            if state.stage == "cancelled":
                changed = database.execute(
                    f"""UPDATE processing_tasks
                        SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL,
                            lease_expires_at = NULL, updated_at = {_NOW_TEXT}
                        WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 1""",
                    (lease.task_id, lease.token, MERGE_STAGE),
                ).rowcount
                status = PersistStatus.CANCELLED
            else:
                changed = database.execute(
                    f"""UPDATE processing_tasks SET stage = ?, progress = ?, updated_at = {_NOW_TEXT}
                        WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 0""",
                    (STAGE, state.progress, lease.task_id, lease.token, MERGE_STAGE),
                ).rowcount
                status = PersistStatus.ADVANCED
            if changed != 1:
                raise RuntimeError(f"stage_done compare-and-swap on task {lease.task_id} matched no row")
    except LeaseLost:
        return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
    return PersistOutcome(status, lease.task_id, state.stage)


def _after_failure(sqlite_url: str, repo: Neo4jRepository, lease: Lease, *, code: str,
                   details: Mapping[str, object] | None, holder: str, lock_seconds: int,
                   lock_wait_seconds: float, defer_cleanup: bool = False) -> PersistOutcome:
    if not _fail(sqlite_url, lease, code, details):
        return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
    cleaned = False if defer_cleanup else cleanup_failed_task(sqlite_url, repo, course_id=lease.course_id, task_id=lease.task_id,
                                  holder=holder, lock_seconds=lock_seconds, lock_wait_seconds=lock_wait_seconds)
    return PersistOutcome(PersistStatus.FAILED, lease.task_id, "failed", error_code=code, cleanup_pending=not cleaned)


def _release(sqlite_url: str, repo: Neo4jRepository, lease: Lease, *, max_attempts: int, holder: str,
             lock_seconds: int, lock_wait_seconds: float, defer_cleanup: bool = False) -> PersistOutcome:
    released = release_after_transient_failure(sqlite_url, lease.task_id, lease.token, code=STORAGE_CODE,
                                               max_attempts=max_attempts)
    if released.status == "released":
        return PersistOutcome(PersistStatus.RELEASED, lease.task_id, STAGE, not_before=released.not_before)
    if released.status == "failed":  # 已置 cleanup_pending
        cleaned = False if defer_cleanup else cleanup_failed_task(sqlite_url, repo, course_id=lease.course_id, task_id=lease.task_id,
                                      holder=holder, lock_seconds=lock_seconds, lock_wait_seconds=lock_wait_seconds)
        return PersistOutcome(PersistStatus.FAILED, lease.task_id, "failed", error_code=STORAGE_CODE,
                              cleanup_pending=not cleaned)
    return PersistOutcome(PersistStatus.LOST, lease.task_id, None)


class _PersistSteps:
    """C-ACC-B：入库阶段子步骤耗时，结束时写一行 INFO（只有任务编号、结果、毫秒数与次数）。

    每个已开始的步骤都计时（含抛错步骤），未开始的步骤不出现。
    ADR-091 后每次显式事务的 ``neo4j_attempts`` 为 1，不含透明回调重跑。
    ``neo4j_ms`` 覆盖显式事务作用域（含最终围栏和退出），``t6_ms`` 是其中的
    跨库提交子区间；两个重叠字段不相加，``total_ms`` 才是阶段墙钟时间。
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.started = time.monotonic()
        self.done: dict[str, int] = {}
        self.neo4j_attempts = 0
        self._open: dict[str, float] = {}

    def start(self, name: str) -> None:
        self._open[name] = time.monotonic()

    def stop(self, name: str) -> None:
        self.done[name] = max(0, round((time.monotonic() - self._open.pop(name)) * 1000))

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        self.start(name)
        try:
            yield
        finally:
            self.stop(name)

    def log(self, outcome: str) -> None:
        parts = [f"{name}_ms={ms}" for name, ms in self.done.items()]
        if self.neo4j_attempts:
            parts.append(f"neo4j_attempts={self.neo4j_attempts}")
        total = max(0, round((time.monotonic() - self.started) * 1000))
        logger.info("persist steps task_id=%s outcome=%s %s total_ms=%s", self.task_id, outcome, " ".join(parts), total)


def run_persist_stage(
    sqlite_url: str,
    lease: Lease,
    *,
    repo: Neo4jRepository,
    max_attempts: int,
    lock_seconds: int,
    lock_wait_seconds: float,
    holder: str | None = None,
    task_guard: LeaseGuard | None = None,
) -> PersistOutcome:
    """见模块说明。``lease.stage`` 须为 ``persisting``。"""
    if lease.stage != STAGE:
        raise ValueError(f"lease is on stage {lease.stage}, not {STAGE}")
    if task_guard is None:
        # Direct stage callers need the same lease horizon/heartbeat as pipeline
        # callers; seed it from the confirmed claim, never a new object-time TTL.
        with LeaseHeartbeat(sqlite_url, lease, lease_seconds=lock_seconds) as heartbeat:
            return run_persist_stage(sqlite_url, lease, repo=repo, max_attempts=max_attempts,
                                     lock_seconds=lock_seconds, lock_wait_seconds=lock_wait_seconds,
                                     holder=holder, task_guard=heartbeat.guard)
    steps = _PersistSteps(lease.task_id)
    outcome = "error"
    try:
        result = _persist_stage(sqlite_url, lease, repo=repo, max_attempts=max_attempts, lock_seconds=lock_seconds,
                                lock_wait_seconds=lock_wait_seconds, holder=holder, steps=steps, task_guard=task_guard)
        outcome = result.status.value
        return result
    except BaseException as error:
        outcome = type(error).__name__
        raise
    finally:
        steps.log(outcome)


def _persist_stage(
    sqlite_url: str,
    lease: Lease,
    *,
    repo: Neo4jRepository,
    max_attempts: int,
    lock_seconds: int,
    lock_wait_seconds: float,
    holder: str | None,
    steps: _PersistSteps,
    task_guard: LeaseGuard,
) -> PersistOutcome:
    owner = holder or lease.owner
    common = dict(holder=owner, lock_seconds=lock_seconds, lock_wait_seconds=lock_wait_seconds)

    def release(*, defer_cleanup: bool = False) -> PersistOutcome:
        with steps.step("task_release"):
            return _release(sqlite_url, repo, lease, max_attempts=max_attempts,
                            defer_cleanup=defer_cleanup, **common)

    def after_failure(**kwargs: Any) -> PersistOutcome:
        with steps.step("task_release"):
            return _after_failure(sqlite_url, repo, lease, **kwargs, **common)

    try:
        task_guard.check()
        with steps.step("candidates"):
            candidates = load_candidates(sqlite_url, course_id=lease.course_id, task_id=lease.task_id)
        with steps.step("plan"):
            plan = build_plan(lease.course_id, lease.task_id, candidates)
        with steps.step("chunks"):
            chunks = get_chunks(sqlite_url, course_id=lease.course_id, chunk_ids=_source_chunk_ids(plan))
    except LeaseLost:
        return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
    except sqlite3.Error:
        return release()

    with steps.step("lock_wait"):
        lock = course_locks.acquire(sqlite_url, lease.course_id, holder=owner, lease_seconds=lock_seconds,
                                    wait_seconds=lock_wait_seconds)
    if lock is None:  # 发布或教师编辑持锁：退避后重试
        return release()

    course_guard = LeaseGuard.from_expiry(lock_seconds, lock.expires_at)

    def check() -> None:
        task_guard.check()
        course_guard.check()

    def work(tx: ScopedTransaction) -> _Written:
        steps.neo4j_attempts += 1
        return _write_draft(tx, lease.task_id, plan, chunks)

    lock_release_started = False
    t6_seq: int | None = None
    tx = None
    dedicated_started = False

    def completed_after_error() -> bool | None:
        # Only recognize OUR T6 result, not a new owner's completed task. If a
        # SQLite COMMIT ack or resource exit failed, never blindly fail/release a
        # completed task. Failed read-back leaves the outcome uncertain.
        if t6_seq is None:
            return False
        try:
            with connect(sqlite_url) as database:
                row = database.execute(
                    "SELECT stage, t6_seq, lease_token FROM processing_tasks WHERE id=? AND course_id=?",
                    (lease.task_id, lease.course_id),
                ).fetchone()
        except sqlite3.Error:
            return None
        return row is not None and row[0] in ('awaiting_review', 'completed') and row[1] == t6_seq and row[2] is None

    def success() -> PersistOutcome:
        return PersistOutcome(PersistStatus.ADVANCED, lease.task_id, 'awaiting_review', nodes=written.nodes,
                              relations=written.relations, downgraded=written.downgraded)

    try:
        try:
            with course_locks.held(sqlite_url, lock, lease_seconds=lock_seconds, guard=course_guard):
                try:
                    with steps.step("lease_check"):
                        check()
                        _check_lease(sqlite_url, lease)  # 租约已丢则不写 Neo4j
                        scope = GraphScope(lease.course_id, DRAFT_VERSION,
                                           effective_task_ids=_effective(sqlite_url, lease.course_id))
                    with steps.step("neo4j"):
                        dedicated_started = True
                        with repo.persist_write_transaction(scope, check=check,
                                remaining=lambda: min(task_guard.remaining(), course_guard.remaining())) as tx:
                            written = work(tx)  # Graph draft guard is acquired here, before SQLite.
                            with steps.step("t6"):
                                acquired = []
                                with persist_transaction(sqlite_url, lease, lock.token,
                                        deadline=tx.deadline, on_acquired=acquired.append) as database:
                                    check()
                                    try:
                                        tx.commit(started_at=acquired[0])
                                        t6_seq = _t6_in(database, lease)
                                    except BaseException:
                                        if tx.commit_started:
                                            task_guard.lose()
                                            course_guard.lose()
                                        raise  # SQLite unwinds before transport cleanup waits.
                finally:
                    steps.start("lock_release")
                    lock_release_started = True
        finally:
            # 只计持锁上下文的退出；进入失败不虚构释放，退出抛错也完成计时。
            if lock_release_started:
                steps.stop("lock_release")
    except LeaseLost:
        if completed_after_error():
            return success()
        return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
    except UnresolvableCycleError as exc:
        return after_failure(code="CYCLE_DETECTED", details={"cycle": list(exc.cycle)})
    except (RepositoryError, sqlite3.Error):
        completed = completed_after_error()
        if completed:
            return success()
        if completed is None:
            logger.warning('persisting T6 outcome uncertain task_id=%s', lease.task_id)
            return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
        if tx is not None and tx.commit_started:
            task_guard.lose()
            course_guard.lose()
            logger.warning('persisting graph outcome uncertain task_id=%s', lease.task_id)
            return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
        return release(defer_cleanup=dedicated_started)
    except (RelationWriteError, RuntimeError, ValueError) as exc:
        completed = completed_after_error()
        if completed:
            return success()
        if completed is None:
            return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
        if tx is not None and tx.commit_started:
            task_guard.lose()
            course_guard.lose()
            return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
        logger.exception("persisting task %s failed (%s)", lease.task_id, type(exc).__name__)
        return after_failure(code="INTERNAL_ERROR", details=None, defer_cleanup=dedicated_started)
    return success()


# ---------------------------------------------------------------- 运行一次


@dataclass(frozen=True)
class PipelineResult:
    reclaimed: ReclaimResult
    cleaned: tuple[str, ...]
    lease: Lease | None
    stages: tuple[tuple[str, str], ...]


#: 全局模式一份共用工具包；personal 模式按租约取各任务自己的工具包（ADR-080）。
ToolkitSource = ExtractionToolkit | Callable[[Lease], ExtractionToolkit]


class _StageTimer:
    """C03-2 续：每个阶段一行 INFO（任务编号、阶段、结果、毫秒数），用于归因抽取末段的非模型时间。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._started = time.monotonic()

    def start(self) -> None:
        self._started = time.monotonic()

    def done(self, stage: str, status: str) -> tuple[str, str]:
        duration = max(0, round((time.monotonic() - self._started) * 1000))
        logger.info("task stage done task_id=%s stage=%s status=%s duration_ms=%s",
                    self.task_id, stage, status, duration)
        return stage, status


def run_pipeline_once(
    settings: Settings,
    *,
    toolkit: ToolkitSource,
    repo: Neo4jRepository,
    owner: str | None = None,
    storage: FileStorage | None = None,
) -> PipelineResult:
    """回收（含重试待清理的失败任务）→ 领取一个任务 → 在同一租约与心跳下依次推进
    ``parsing`` → ``extracting`` → ``merging`` → ``persisting``，直到 T6、终态或释放。"""
    url = settings.SQLITE_URL
    holder = owner or default_owner()
    store = storage or FileStorage(settings.STORAGE_DIR, settings.UPLOAD_MAX_BYTES)
    # §8.5：worker 等锁不另设超时，上限由持锁者的租约决定（持锁者不续约时其锁在 L 秒内过期）。
    lock = dict(lock_seconds=settings.TASK_LEASE_SECONDS, lock_wait_seconds=settings.TASK_LEASE_SECONDS)
    reclaimed = reclaim_expired(url, max_attempts=settings.TASK_MAX_ATTEMPTS)
    cleaned = tuple(
        task.task_id for task in reclaimed.cleanup_pending
        if cleanup_failed_task(url, repo, course_id=task.course_id, task_id=task.task_id, holder=holder, **lock)
    )
    lease = claim_next(url, owner=holder, lease_seconds=settings.TASK_LEASE_SECONDS,
                       max_attempts=settings.TASK_MAX_ATTEMPTS)
    if lease is None:
        return PipelineResult(reclaimed, cleaned, None, ())
    stages: list[tuple[str, str]] = []
    timer = _StageTimer(lease.task_id)
    with LeaseHeartbeat(url, lease, lease_seconds=settings.TASK_LEASE_SECONDS) as heartbeat:
        stage = lease.stage
        if stage == "parsing":
            timer.start()
            parsed = run_parse_stage(url, lease, storage=store, max_attempts=settings.TASK_MAX_ATTEMPTS)
            stages.append(timer.done("parsing", parsed.status.value))
            stage = "extracting" if parsed.status is ParseStatus.ADVANCED else ""
        if stage == "extracting":
            timer.start()
            leased = replace(lease, stage=stage)
            try:
                resolved = toolkit if isinstance(toolkit, ExtractionToolkit) else toolkit(leased)
            except CredentialUnavailable as exc:
                extracted = fail_for_credential(url, leased, exc.reason)
            else:
                extracted = run_extract_stage(url, leased, toolkit=resolved,
                                              limits=ExtractLimits.from_settings(settings))
            stages.append(timer.done("extracting", extracted.status.value))
            stage = MERGE_STAGE if extracted.status is ExtractStatus.ADVANCED else ""
        if stage == MERGE_STAGE:
            timer.start()
            merged = run_merge_stage(url, replace(lease, stage=stage))
            stages.append(timer.done(MERGE_STAGE, merged.status.value))
            stage = STAGE if merged.status is PersistStatus.ADVANCED else ""
        if stage == STAGE:
            timer.start()
            persisted = run_persist_stage(url, replace(lease, stage=stage), repo=repo,
                                          max_attempts=settings.TASK_MAX_ATTEMPTS, holder=holder,
                                          task_guard=heartbeat.guard, **lock)
            stages.append(timer.done(STAGE, persisted.status.value))
    if not stages:  # 领到了本入口不处理的阶段（不应出现）
        release_on_shutdown(url, lease.task_id, lease.token)
    return PipelineResult(reclaimed, cleaned, lease, tuple(stages))
