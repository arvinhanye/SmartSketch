"""F12：图编辑审计日志的 SQLite 持久化（迁移 012；ADR-061）。

- ``begin``：**一个** SQLite 写事务里把 ``courses.draft_revision`` 加 1 并插入一条 ``pending`` 审计行，
  返回事件 ID 与新的草稿修订号。它取代教师写入路径上的 ``bump_draft_revision``，因此审计行记下的版本
  与课程草稿修订号严格一致；事务失败时两者都不写。
- ``resolve``：把 ``pending`` 行置为 ``committed`` / ``aborted``；条件更新只命中 ``pending`` 行，重复调用
  与并发调用都只生效一次（可重试）。已结束的行由触发器冻结。
- ``pending`` / ``list_logs``：按课程读取；课程隔离由 ``course_id`` 条件保证。

本模块只做 SQL；摘要的白名单与脱敏在 ``app.services.graph.audit``。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from app.repositories.sqlite import connect

__all__ = ["ACTIONS", "EditLog", "begin", "list_logs", "pending", "resolve"]

ACTIONS: Final = frozenset({"create", "update", "unlock", "delete", "merge"})
_COLUMNS: Final = ("seq, event_id, course_id, actor_id, action, kp_id, draft_revision, kp_revision_before, "
                   "kp_revision_after, state, summary, failure_reason, resolved_by, created_at, resolved_at")


@dataclass(frozen=True)
class EditLog:
    seq: int
    event_id: str
    course_id: str
    actor_id: str
    action: str
    kp_id: str
    draft_revision: int
    kp_revision_before: int | None
    kp_revision_after: int | None
    state: str
    summary: dict[str, Any]
    failure_reason: str | None
    resolved_by: str | None
    created_at: str
    resolved_at: str | None


def _row(row: sqlite3.Row | tuple[Any, ...]) -> EditLog:
    values = list(row)
    values[10] = json.loads(values[10])
    return EditLog(*values)


def _dump(summary: Mapping[str, Any]) -> str:
    return json.dumps(dict(summary), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def begin(sqlite_url: str, *, course_id: str, actor_id: str, action: str, kp_id: str,
          kp_revision_before: int | None, summary: Mapping[str, Any]) -> tuple[str, int]:
    """草稿修订号加 1 并记一条 ``pending`` 审计行（同一事务）；返回 ``(event_id, draft_revision)``。"""
    if action not in ACTIONS:
        raise ValueError(f"unknown edit action {action!r}")
    event_id = uuid.uuid4().hex
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            row = database.execute(
                "UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ? RETURNING draft_revision",
                (course_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"course {course_id} does not exist")
            revision = int(row[0])
            database.execute(
                "INSERT INTO graph_edit_logs (event_id, course_id, actor_id, action, kp_id, draft_revision,"
                " kp_revision_before, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, course_id, actor_id, action, kp_id, revision, kp_revision_before, _dump(summary)),
            )
            database.execute("COMMIT")
        except BaseException:
            database.execute("ROLLBACK")
            raise
    return event_id, revision


def resolve(sqlite_url: str, event_id: str, *, state: str, resolved_by: str,
            kp_revision_after: int | None = None, summary: Mapping[str, Any] | None = None,
            failure_reason: str | None = None) -> bool:
    """``pending`` → ``committed``/``aborted``；返回本次是否命中（已结束的行返回 ``False``，不报错）。"""
    if state not in ("committed", "aborted"):
        raise ValueError(f"cannot resolve an edit log to {state!r}")
    with connect(sqlite_url) as database:
        cursor = database.execute(
            "UPDATE graph_edit_logs SET state = ?, resolved_by = ?, kp_revision_after = coalesce(?, kp_revision_after),"
            " summary = coalesce(?, summary), failure_reason = ?,"
            " resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
            " WHERE event_id = ? AND state = 'pending'",
            (state, resolved_by, kp_revision_after, None if summary is None else _dump(summary),
             failure_reason if state == "aborted" else None, event_id),
        )
        return cursor.rowcount == 1


def pending(sqlite_url: str, course_id: str) -> list[EditLog]:
    """本课程未结束的审计行，按写入顺序。"""
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_COLUMNS} FROM graph_edit_logs WHERE course_id = ? AND state = 'pending' ORDER BY seq",
            (course_id,),
        ).fetchall()
    return [_row(r) for r in rows]


def list_logs(sqlite_url: str, course_id: str, *, after_seq: int = 0, limit: int = 100) -> list[EditLog]:
    """本课程的审计行，按 ``seq`` 升序、从 ``after_seq`` 之后分页（游标稳定，新行只追加在末尾）。"""
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_COLUMNS} FROM graph_edit_logs WHERE course_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (course_id, after_seq, limit),
        ).fetchall()
    return [_row(r) for r in rows]
