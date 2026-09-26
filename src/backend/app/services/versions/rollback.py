"""G06：回滚——以历史版本 k 的内容前滚为新版本（specs/teacher-review-publish.md V6；PUB-3/7/15/16/25/26；ADR-041）。

- R2 按 ``(course_id, version, committed)`` 查 k，找不到（含他课版本号、失败尝试）→ ``VersionNotFound``（404），无写入。
- R3 k 的摘要等于当前发布版摘要 → ``unchanged = True``，不产生版本号。
- R4 插入 ``kind = rollback`` 尝试行（快照、摘要、统计、向量空间自 k 复制；冲突 → ``PublishInProgress``）并心跳。
- R5 核对 k 自己记录的 ``embedding_space`` 等于当前空间，再在一个 Neo4j 写事务里把 k 的副本连同向量复制到
  本尝试（``copy_version``，不调用向量模型），按 P9 核对后置 ``materialized``。源副本缺失或空间不符 → C1 + 告警，5xx。
- R6 有界等待课程写锁，读草稿修订号 r 并按 V3 复算草稿摘要 d；等锁超时、读失败或草稿不可发布都按「d 未知」处理，
  回滚照常进行。
- R7 提交（取号、指针 CAS），``published_from_revision = r``（d 等于 k 的摘要）否则 ``-1``；**不执行 T7**。

回滚从不修改草稿。任何 R4 之后的失败都走 G05 ``compensate``，发布指针不变。
"""

from __future__ import annotations

import logging
from typing import Final

from app.repositories import course_locks, versions
from app.repositories.graph_read import GraphReader
from app.repositories.versions import CommitRejected, VersionNotFound
from app.services.versions.materialize import copy_version, verify
from app.services.versions.publish import PublishContext, PublishFailed, PublishOutcome, _heartbeat, load_draft
from app.services.versions.reconcile import compensate, reclaim_expired
from app.services.versions.snapshot import SnapshotBlocked, build_snapshot, load_snapshot

__all__ = ["VersionNotFound", "rollback"]

logger = logging.getLogger(__name__)

LOCK_HOLDER: Final = "rollback"
UNKNOWN_REVISION: Final = -1


def _draft_digest(ctx: PublishContext, course_id: str) -> tuple[int, str] | None:
    """R6：``(r, d)``；拿不到锁、读失败或草稿不可发布时为 ``None``（d 未知）。"""
    url = ctx.sqlite_url
    try:
        lock = course_locks.acquire(url, course_id, holder=LOCK_HOLDER, lease_seconds=ctx.lease_seconds,
                                    wait_seconds=ctx.lock_wait_seconds)
    except Exception:
        logger.warning("rollback R6: course lock unavailable for %s; treating the draft digest as unknown", course_id)
        return None
    if lock is None:
        return None
    try:
        with course_locks.held(url, lock, lease_seconds=ctx.lease_seconds):
            state = versions.read_draft_state(url, course_id)
            draft = load_draft(url, GraphReader(ctx.repo), state)
        return state.draft_revision, build_snapshot(draft).snapshot.digest
    except SnapshotBlocked:
        return None
    except Exception:
        logger.warning("rollback R6: could not read the draft of %s; treating its digest as unknown", course_id)
        return None


def _outcome(record: versions.VersionRecord, unchanged: bool) -> PublishOutcome:
    assert record.version is not None and record.committed_at is not None
    excluded = dict(record.excluded or {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0})
    return PublishOutcome(record.version, record.version_id, record.committed_at, unchanged,
                          record.node_count or 0, record.edge_count or 0, excluded)


def rollback(ctx: PublishContext, course_id: str, version: int, *, created_by: str | None) -> PublishOutcome:
    """V6 R2～R7。调用方已完成 R1 鉴权。"""
    url = ctx.sqlite_url
    if type(version) is not int or version < 1:
        raise VersionNotFound("version must be a positive integer")
    source = versions.get_committed(url, course_id, version)  # R2
    if source is None:
        raise VersionNotFound(f"version {version} is not a committed version of this course")
    current = versions.current_version(url, course_id)
    if current is not None and current.digest == source.digest:  # R3
        return _outcome(current, True)
    try:
        reclaim_expired(url, ctx.repo, course_id)
    except Exception:
        logger.exception("could not reclaim expired attempts for course %s before rolling back", course_id)
    attempt = versions.begin_attempt(url, course_id, kind="rollback", created_by=created_by,
                                     lease_seconds=ctx.lease_seconds, source_version=version)  # R4
    version_id = attempt.version_id
    expected_pointer = None if current is None else current.version_id
    step = "R5"
    touched_graph = False
    try:
        with _heartbeat(ctx, version_id):
            space = ctx.current_space()
            if source.embedding_space != space:
                logger.error("course %s: rollback source v%s is in space %s, current space is %s "
                             "(V12 invariant broken); not re-embedding", course_id, version,
                             source.embedding_space, space)
                raise PublishFailed(step, "embedding space of the source version differs", version_id)
            raw = versions.read_snapshot(url, version_id)
            if raw is None:
                raise PublishFailed(step, "attempt has no copied snapshot", version_id)
            snapshot = load_snapshot(raw)
            touched_graph = True
            copy_version(ctx.repo, snapshot, source.version_id, version_id)
            verify(ctx.repo, snapshot, version_id, space)
            if not versions.mark_materialized(url, version_id):
                raise PublishFailed(step, "attempt is no longer preparing", version_id)
            step = "R6"
            draft = _draft_digest(ctx, course_id)
            revision = draft[0] if draft is not None and draft[1] == snapshot.digest else UNKNOWN_REVISION
            step = "R7"
            with versions.immediate(url) as database:
                record = versions.commit_attempt(database, version_id, expected_pointer=expected_pointer,
                                                 published_from_revision=revision)
    except PublishFailed as error:
        _compensate(ctx, course_id, version_id, f"{error.step}: {error.reason}", touched_graph)
        raise
    except CommitRejected as error:
        _compensate(ctx, course_id, version_id, f"{step}: {error}", touched_graph)
        raise PublishFailed(step, str(error), version_id) from error
    except Exception as error:
        if step == "R5":
            logger.error("course %s: rollback to v%s failed while copying the source copy (%s)",
                         course_id, version, type(error).__name__)
        _compensate(ctx, course_id, version_id, f"{step}: {type(error).__name__}", touched_graph)
        raise PublishFailed(step, type(error).__name__, version_id) from error
    return _outcome(record, False)


def _compensate(ctx: PublishContext, course_id: str, version_id: str, reason: str, touched_graph: bool) -> None:
    try:
        compensate(ctx.sqlite_url, ctx.repo, course_id, version_id, reason, touched_graph=touched_graph)
    except Exception:
        logger.exception("rollback C1 failed for attempt %s; the sweeper will finish it", version_id)
