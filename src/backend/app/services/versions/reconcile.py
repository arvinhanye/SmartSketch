"""G05：发布/回滚失败的补偿与清扫（specs/teacher-review-publish.md V5 C1、V9；PUB-18/19/20；ADR-035）。

- ``compensate``（C1，发布与回滚共用，可重复执行）：先把尝试行条件更新为 ``failed``——影响 0 行说明它已
  提交或已被清扫处理，**到此为止，不碰 Neo4j**；否则删除该尝试的 Neo4j 副本，删不掉置 ``cleanup_pending``。
- ``sweep_course``（V9，按课程逐个处理，不跨课程批量删除）：
  1. 租约已过期的进行中尝试执行 C1（原因 ``LEASE_EXPIRED``）；
  2. ``cleanup_pending`` 的 ``failed`` 行重试删除，成功后清除标记；
  3. Neo4j 中存有副本、SQLite 对应行为 ``failed`` 的 ``version_id`` 删除副本；
  4. Neo4j 中找不到任何 SQLite 行的 ``version_id`` **只告警，不删除**（K10 人工核对恢复时间点）；
  5. ``committed`` 行在 Neo4j 缺副本：告警（重建归 K10）。
  ``committed`` 版本与租约未过期的尝试从不被删除，因此学生正在读的旧版本与进行中的发布都不受影响。
- ``sweep``：遍历全部课程；一个课程失败只记日志，不影响其他课程。

调度（并入 worker 周期回收步骤，A06 §8.6）不在本模块：调用方按自己的周期调用 ``sweep``。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Final

from app.repositories import versions
from app.repositories.graph_read import stored_version_ids
from app.repositories.neo4j import Neo4jRepository
from app.services.versions.materialize import drop_version

__all__ = ["LEASE_EXPIRED", "SweepReport", "compensate", "sweep", "sweep_course"]

logger = logging.getLogger(__name__)

LEASE_EXPIRED: Final = "LEASE_EXPIRED"


def compensate(sqlite_url: str, repo: Neo4jRepository, course_id: str, version_id: str, reason: str, *,
               touched_graph: bool = True) -> bool:
    """C1。返回 ``True`` 表示本次把尝试判为失败（Neo4j 副本已删或已置 ``cleanup_pending``）。

    SQLite 写失败时原样抛出：尝试行保持进行中，租约到期后由清扫再执行 C1。
    """
    if not versions.fail_attempt(sqlite_url, version_id, reason):
        return False  # 已提交或已被处理：不得删除 Neo4j 数据
    if touched_graph:
        _drop_or_mark(sqlite_url, repo, course_id, version_id)
    return True


def _drop_or_mark(sqlite_url: str, repo: Neo4jRepository, course_id: str, version_id: str) -> bool:
    """C1 第 2、3 步；返回副本是否已删除。"""
    try:
        drop_version(repo, course_id, version_id)
    except Exception:
        logger.warning("could not drop Neo4j copy of failed attempt %s; marking cleanup_pending", version_id)
        versions.set_cleanup_pending(sqlite_url, version_id, True)
        return False
    return True


@dataclass
class SweepReport:
    course_id: str
    expired: list[str] = field(default_factory=list)  # 本次判失败的过期尝试
    dropped: list[str] = field(default_factory=list)  # 本次删除副本的 failed 尝试
    pending: list[str] = field(default_factory=list)  # 仍待清理（Neo4j 删除失败）
    orphans: list[str] = field(default_factory=list)  # Neo4j 有副本、SQLite 无行：只告警
    missing_copies: list[str] = field(default_factory=list)  # committed 行缺 Neo4j 副本：只告警

    @property
    def changed(self) -> bool:
        return bool(self.expired or self.dropped)


def sweep_course(sqlite_url: str, repo: Neo4jRepository, course_id: str) -> SweepReport:
    """V9 第 1～5 步，只处理 ``course_id``。可重复执行：没有新变化时第二次什么也不写。"""
    report = SweepReport(course_id)

    # 1. 过期尝试 → C1（不知道它是否已写 Neo4j，一律尝试删除，删除可重复执行）。
    for attempt in versions.list_expired_attempts(sqlite_url, course_id):
        if compensate(sqlite_url, repo, course_id, attempt.version_id, LEASE_EXPIRED):
            report.expired.append(attempt.version_id)

    rows = {r.version_id: r for r in versions.list_attempts(sqlite_url, course_id)}
    stored = stored_version_ids(repo, course_id)

    # 2、3. 失败行：待清理的，或 Neo4j 里仍有副本的，删除后清标记。
    for version_id, row in rows.items():
        if row.state != "failed" or version_id in report.expired:
            continue
        if not (row.cleanup_pending or version_id in stored):
            continue
        if _drop_or_mark(sqlite_url, repo, course_id, version_id):
            if row.cleanup_pending:
                versions.set_cleanup_pending(sqlite_url, version_id, False)
            report.dropped.append(version_id)
    rows = {r.version_id: r for r in versions.list_attempts(sqlite_url, course_id)}
    report.pending = [v for v, r in rows.items() if r.state == "failed" and r.cleanup_pending]

    # 4. 孤儿副本：只告警。
    report.orphans = sorted(stored - rows.keys())
    for version_id in report.orphans:
        logger.warning("course %s: Neo4j holds version %s with no SQLite row; not deleting (K10)",
                       course_id, version_id)

    # 5. 已提交版本缺副本：告警。
    report.missing_copies = sorted(v for v, r in rows.items() if r.state == "committed" and v not in stored)
    for version_id in report.missing_copies:
        logger.error("course %s: committed version %s has no Neo4j copy (K10 rebuild needed)",
                     course_id, version_id)
    return report


def sweep(sqlite_url: str, repo: Neo4jRepository) -> list[SweepReport]:
    """逐课程清扫；单个课程失败记日志后继续。"""
    reports = []
    for course_id in versions.list_course_ids(sqlite_url):
        try:
            reports.append(sweep_course(sqlite_url, repo, course_id))
        except Exception:
            logger.exception("publish sweep failed for course %s; will retry next cycle", course_id)
    return reports
