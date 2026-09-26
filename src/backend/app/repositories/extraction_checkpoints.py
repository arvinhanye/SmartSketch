"""E12：抽取阶段检查点（``task_chunk_checkpoints``，迁移 008；specs/task-processing.md §8.4 ``extracting``）。

一行表示任务的一个抽取单元已经结束：``chunk``（块级实体抽取）或 ``section``（小节级关系抽取）。
行一经写入不再改变（库层触发器）；写入必须在调用方已开启、已做令牌 fence 的事务里执行，
与任务行更新同事务提交（§8.2 防旧写）。所有读取按 ``course_id`` 隔离。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from app.repositories.sqlite import connect

__all__ = ["Checkpoint", "UnitKind", "list_checkpoints", "read_checkpoints", "write_checkpoint"]

UnitKind = Literal["chunk", "section"]
_KINDS = frozenset({"chunk", "section"})


@dataclass(frozen=True)
class Checkpoint:
    unit_kind: str
    unit_id: str
    status: str
    attempts: int
    error_code: str | None
    result: Mapping[str, object] | None = field(repr=False)


def _check(course_id: str, task_id: str, unit_kind: str | None) -> None:
    for name, value in (("course_id", course_id), ("task_id", task_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if unit_kind is not None and unit_kind not in _KINDS:
        raise ValueError(f"unit_kind must be one of {sorted(_KINDS)}")


def write_checkpoint(
    database: sqlite3.Connection,
    *,
    task_id: str,
    course_id: str,
    unit_kind: UnitKind,
    unit_id: str,
    status: Literal["done", "failed"],
    attempts: int,
    error_code: str | None = None,
    result: Mapping[str, object] | None = None,
) -> bool:
    """插入一个检查点；同一单元已有检查点时不写（重放幂等），返回是否新写入。"""
    _check(course_id, task_id, unit_kind)
    if not database.in_transaction:
        raise RuntimeError("write_checkpoint must run inside the caller's leased transaction")
    encoded = None if result is None else json.dumps(dict(result), ensure_ascii=False, sort_keys=True)
    return database.execute(
        """INSERT INTO task_chunk_checkpoints
               (task_id, course_id, unit_kind, unit_id, status, attempts, error_code, result)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (task_id, unit_kind, unit_id) DO NOTHING""",
        (task_id, course_id, unit_kind, unit_id, status, attempts, error_code, encoded),
    ).rowcount == 1


def read_checkpoints(
    database: sqlite3.Connection, *, course_id: str, task_id: str, unit_kind: UnitKind | None = None
) -> tuple[Checkpoint, ...]:
    _check(course_id, task_id, unit_kind)
    clauses, params = ["course_id = ?", "task_id = ?"], [course_id, task_id]
    if unit_kind is not None:
        clauses.append("unit_kind = ?")
        params.append(unit_kind)
    rows = database.execute(
        f"""SELECT unit_kind, unit_id, status, attempts, error_code, result FROM task_chunk_checkpoints
            WHERE {' AND '.join(clauses)} ORDER BY unit_kind, unit_id""",
        params,
    ).fetchall()
    return tuple(
        Checkpoint(kind, unit, status, attempts, code, None if raw is None else json.loads(raw))
        for kind, unit, status, attempts, code, raw in rows
    )


def list_checkpoints(
    sqlite_url: str, *, course_id: str, task_id: str, unit_kind: UnitKind | None = None
) -> tuple[Checkpoint, ...]:
    with connect(sqlite_url) as database:
        return read_checkpoints(database, course_id=course_id, task_id=task_id, unit_kind=unit_kind)
