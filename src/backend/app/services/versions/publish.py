"""G04：原子发布与发布指针切换（specs/teacher-review-publish.md V3～V5、V11 PUB-1/2/4/5/6/12/21/22/23/35；
ADR-012、ADR-034）。

``publish`` 按 V5 的 P2～P12 执行，唯一提交点是 P11 的 SQLite 事务：

- P2 插入 ``preparing`` 尝试行（同课程已有尝试 → ``PublishInProgress``，409），并开始按租约 1/3 心跳。
- P3 有界等待课程写锁（超时 → ``CourseBusy``，409，``holder`` 为当前持有方）。
- P4 持锁读取：SQLite 的草稿修订号 r、发布指针、任务水位 w、有效任务集合 V 与 V 的资料修订；Neo4j 的
  可见草稿（F07 ``GraphReader``，按 V 过滤节点、关系、章节与来源关联）；来源块的修订取自 SQLite。
- P5 释放写锁。之后的草稿编辑不进入本次快照。
- P6/P7 G01 组装快照并校验（``SnapshotBlocked``，409 ``PUBLISH_BLOCKED``；环路先核对首尾同 ID）。
  摘要等于当前版本且向量空间相同 → 幂等路径：一个事务内删尝试行、T7、写 ``published_from_revision``，
  返回 ``unchanged = True``，不写 Neo4j；摘要相同而空间不同 → 不变式被破坏，5xx 并告警。
  否则写入快照（``record_snapshot``）。
- P8/P9 G03 物化并核对；P10 ``materialized``；P11 一个事务内 ``commit_attempt``（取号、指针 CAS）与 T7。

P2 之后任何失败都走 C1：尝试行条件更新为 ``failed``（0 行说明已提交或已被清扫，**不碰 Neo4j**）；
若已开始物化，再删除本尝试的 Neo4j 副本，删不掉置 ``cleanup_pending`` 交给清扫（G05）。发布指针在 C1
中从不改变，任务状态也不变。

本模块不做鉴权（P1，由路由按 A05 完成），也不定义 HTTP 形状；异常各带 ``code`` 供路由映射。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from app.repositories import course_locks, versions
from app.repositories.chunks import get_chunks
from app.repositories.graph_read import GraphReader
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.repositories.versions import CommitRejected, PublishInProgress
from app.services.graph.read import _relation_chunk_ids
from app.services.versions.materialize import Embedder, embed_snapshot_nodes, materialize, verify
from app.services.versions.reconcile import compensate
from app.services.versions.snapshot import (
    DraftChapter,
    DraftEdge,
    DraftGraph,
    DraftNode,
    Revision,
    Snapshot,
    SnapshotBlocked,
    build_snapshot,
)

__all__ = [
    "CourseBusy",
    "PublishContext",
    "PublishFailed",
    "PublishInProgress",
    "PublishOutcome",
    "SnapshotBlocked",
    "load_draft",
    "publish",
]

logger = logging.getLogger(__name__)

DRAFT: Final = "draft"
LOCK_HOLDER: Final = "publish"


class CourseBusy(Exception):
    """P3 等课程写锁超时（409 ``COURSE_BUSY``）；``holder`` 为当时的持有方，可能已在此间释放。"""

    code = "COURSE_BUSY"

    def __init__(self, holder: str | None) -> None:
        super().__init__(self.code)
        self.holder = holder

    def details(self) -> dict[str, Any]:
        return {} if self.holder is None else {"holder": self.holder}


class PublishFailed(RuntimeError):
    """P4 之后的存储、物化、核对或提交失败（5xx）；已执行 C1，发布指针不变，教师可重试。"""

    code = "INTERNAL_ERROR"

    def __init__(self, step: str, reason: str, version_id: str) -> None:
        super().__init__(f"publish failed at {step}: {reason}")
        self.step = step
        self.reason = reason
        self.version_id = version_id


@dataclass(frozen=True)
class PublishContext:
    """发布依赖：SQLite、Neo4j、E07 向量适配器、当前向量空间读取器与 A07 配置值。"""

    sqlite_url: str
    repo: Neo4jRepository
    embedder: Embedder
    current_space: Callable[[], str]
    lease_seconds: int = 60
    lock_wait_seconds: float = 5


@dataclass(frozen=True)
class PublishOutcome:
    """``PublishResult`` 的内容；``version_id`` 供日志与审计，不上线。"""

    version: int
    version_id: str
    published_at: str
    unchanged: bool
    node_count: int
    edge_count: int
    excluded: Mapping[str, int]


# ---------------------------------------------------------------- P4 草稿读取


def load_draft(sqlite_url: str, reader: GraphReader, state: versions.DraftState) -> DraftGraph:
    """按 V 读出可见草稿，组成 G01 的 ``DraftGraph``（调用方持课程写锁）。"""
    course_id = state.course_id
    scope = GraphScope(course_id, DRAFT, effective_task_ids=list(state.effective_task_ids))
    raw_nodes = reader.nodes(scope, "teacher")
    kp_ids = [str(p["kp_id"]) for p in raw_nodes]
    node_refs: dict[str, list[str]] = {k: [] for k in kp_ids}
    for evidence in reader.evidence(scope, "teacher", kp_ids):
        node_refs[evidence.kp_id].append(evidence.chunk_id)
    raw_edges = reader.edges(scope, "teacher")
    edge_refs = [_relation_chunk_ids(e, scope) for e in raw_edges]

    chunk_ids = {c for refs in node_refs.values() for c in refs} | {c for refs in edge_refs for c in refs}
    # 只认本课程 SQLite 中的块：他课或不存在的块不在映射里，由 G01 判为 invalid_source_ref。
    chunk_revisions = {c.chunk_id: c.revision_id for c in get_chunks(sqlite_url, course_id=course_id,
                                                                      chunk_ids=sorted(chunk_ids))}
    nodes = [
        DraftNode(
            kp_id=str(p["kp_id"]), name=p.get("name"), type=p.get("type"), definition=p.get("definition"),
            status=p.get("status"), aliases=tuple(p.get("aliases") or ()), chapter_id=p.get("chapter_id"),
            difficulty=p.get("difficulty"), importance=p.get("importance"),
            source_refs=tuple(node_refs[str(p["kp_id"])]), merged_from=tuple(p.get("merged_from") or ()),
        )
        for p in raw_nodes
    ]
    edges = [
        DraftEdge(rel_id=e["p"].get("rel_id"), type=e["type"], from_id=e["from_id"], to_id=e["to_id"],
                  status=e["p"].get("status"), source_refs=tuple(refs))
        for e, refs in zip(raw_edges, edge_refs, strict=True)
    ]
    chapters = [DraftChapter(p.get("chapter_id"), p.get("title"), p.get("order"), p.get("parent_id"))
                for p in reader.chapters(scope, "teacher")]
    revisions = [Revision(*row) for row in state.revisions]
    return DraftGraph(course_id, revisions, chapters, nodes, edges, chunk_revisions)


def _require_closed_cycles(blocked: SnapshotBlocked) -> None:
    """契约 ``x-closed-cycle``：``cycle`` 必须首尾同 ID，组装 409 前核对（V3）。"""
    for reason in blocked.reasons:
        if reason.kind == "cycle" and (not reason.cycle or len(reason.cycle) < 2
                                       or reason.cycle[0] != reason.cycle[-1]):
            raise RuntimeError("cycle reason is not a closed chain")


# ---------------------------------------------------------------- 心跳与 C1


@contextmanager
def _heartbeat(ctx: PublishContext, version_id: str) -> Iterator[None]:
    """每 ``PUBLISH_LEASE_SECONDS / 3`` 续约尝试行；续约失败即停（提交条件会拒绝过期尝试）。"""
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(ctx.lease_seconds / 3):
            try:
                if not versions.heartbeat(ctx.sqlite_url, version_id, lease_seconds=ctx.lease_seconds):
                    return
            except Exception:  # SQLite 暂时不可用：下个周期再试
                continue

    thread = threading.Thread(target=beat, name=f"publish-{version_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def _compensate(ctx: PublishContext, course_id: str, version_id: str, reason: str, *, touched_graph: bool) -> None:
    """C1（G05 ``reconcile.compensate``）；自身失败只记日志，留给清扫，不掩盖原错误。"""
    try:
        compensate(ctx.sqlite_url, ctx.repo, course_id, version_id, reason, touched_graph=touched_graph)
    except Exception:
        logger.exception("publish C1 failed for attempt %s; the sweeper will finish it after the lease expires",
                         version_id)


# ---------------------------------------------------------------- 发布


def publish(ctx: PublishContext, course_id: str, *, created_by: str | None) -> PublishOutcome:
    """V5 P2～P12。调用方已完成 P1 鉴权。"""
    url = ctx.sqlite_url
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=created_by,
                                     lease_seconds=ctx.lease_seconds)  # P2；冲突抛 PublishInProgress
    version_id = attempt.version_id
    step = "P3"
    touched_graph = False
    try:
        with _heartbeat(ctx, version_id):
            lock = course_locks.acquire(url, course_id, holder=LOCK_HOLDER, lease_seconds=ctx.lease_seconds,
                                        wait_seconds=ctx.lock_wait_seconds)
            if lock is None:
                raise CourseBusy(course_locks.current_holder(url, course_id))
            step = "P4"
            with course_locks.held(url, lock, lease_seconds=ctx.lease_seconds):
                state = versions.read_draft_state(url, course_id)
                draft = load_draft(url, GraphReader(ctx.repo), state)
            # P5：锁已释放。
            step = "P6"
            try:
                build = build_snapshot(draft)
            except SnapshotBlocked as blocked:
                _require_closed_cycles(blocked)
                raise
            snapshot = build.snapshot
            step = "P7"
            space = ctx.current_space()
            current = None if state.published_version_id is None else versions.get_version(
                url, state.published_version_id)
            counts = _counts(snapshot)
            if current is not None and current.digest == snapshot.digest:
                if current.embedding_space != space:
                    logger.error("course %s: current version %s has digest-equal content in space %s, "
                                 "current space is %s (V12 invariant broken)",
                                 course_id, current.version_id, current.embedding_space, space)
                    raise PublishFailed(step, "embedding space of the current version differs", version_id)
                with versions.immediate(url) as database:
                    versions.discard_attempt(database, version_id, expected_pointer=state.published_version_id,
                                             published_from_revision=state.draft_revision)
                    versions.complete_published_tasks(database, course_id, state.task_watermark)
                assert current.version is not None and current.committed_at is not None
                return PublishOutcome(current.version, current.version_id, current.committed_at, True,
                                      *counts, build.excluded.to_dict())
            if not versions.record_snapshot(
                url, version_id, snapshot=snapshot.canonical, digest=snapshot.digest, node_count=counts[0],
                edge_count=counts[1], excluded=build.excluded.to_dict(), draft_revision=state.draft_revision,
                task_watermark=state.task_watermark, embedding_space=space,
            ):
                raise PublishFailed(step, "attempt is no longer preparing", version_id)
            step = "P8"
            vectors = embed_snapshot_nodes(ctx.embedder, snapshot)
            touched_graph = True
            materialize(ctx.repo, snapshot, version_id, vectors, lambda: space)
            step = "P9"
            verify(ctx.repo, snapshot, version_id, space)
            step = "P10"
            if not versions.mark_materialized(url, version_id):
                raise PublishFailed(step, "attempt is no longer preparing", version_id)
            step = "P11"
            with versions.immediate(url) as database:
                record = versions.commit_attempt(database, version_id, expected_pointer=state.published_version_id,
                                                 published_from_revision=state.draft_revision)
                versions.complete_published_tasks(database, course_id, state.task_watermark)
    except CourseBusy:
        _compensate(ctx, course_id, version_id, "COURSE_BUSY", touched_graph=False)
        raise
    except SnapshotBlocked:
        _compensate(ctx, course_id, version_id, "PUBLISH_BLOCKED", touched_graph=False)
        raise
    except PublishFailed as error:
        _compensate(ctx, course_id, version_id, f"{error.step}: {error.reason}", touched_graph=touched_graph)
        raise
    except CommitRejected as error:
        _compensate(ctx, course_id, version_id, f"{step}: {error}", touched_graph=touched_graph)
        raise PublishFailed(step, str(error), version_id) from error
    except Exception as error:
        _compensate(ctx, course_id, version_id, f"{step}: {type(error).__name__}", touched_graph=touched_graph)
        raise PublishFailed(step, type(error).__name__, version_id) from error
    # P12
    assert record.version is not None and record.committed_at is not None
    return PublishOutcome(record.version, version_id, record.committed_at, False, *counts,
                          build.excluded.to_dict())


def _counts(snapshot: Snapshot) -> tuple[int, int]:
    data: Mapping[str, Sequence[Any]] = snapshot.data
    return len(data["nodes"]), len(data["edges"])
