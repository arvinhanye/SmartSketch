"""Persistence for uploaded course materials in the SQLite ``materials`` table."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.repositories.sqlite import connect

MaterialFormat = Literal["pdf", "docx", "txt", "markdown"]


@dataclass(frozen=True)
class MaterialRecord:
    id: str
    course_id: str
    filename: str
    format: MaterialFormat
    size_bytes: int
    content_hash: str
    storage_name: str
    parse_status: str
    uploaded_at: str
    #: 最新创建任务的 ID（D-16、ADR-021）；只有列表查询填写，无任务时为 None。
    task_id: str | None = None


_COLUMNS = (
    "id, course_id, filename, format, size_bytes, content_hash, storage_name, "
    "parse_status, uploaded_at"
)


def insert_material(
    database: sqlite3.Connection,
    *,
    material_id: str,
    course_id: str,
    filename: str,
    format: MaterialFormat,
    size_bytes: int,
    content_hash: str,
    storage_name: str,
) -> MaterialRecord:
    """Insert a material on the caller's connection and in its transaction."""
    database.execute(
        """INSERT INTO materials
           (id, course_id, filename, format, size_bytes, content_hash, storage_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (material_id, course_id, filename, format, size_bytes, content_hash, storage_name),
    )
    row = database.execute(
        f"SELECT {_COLUMNS} FROM materials WHERE id = ?", (material_id,)
    ).fetchone()
    if row is None:
        raise RuntimeError("material insert did not return a row")
    return MaterialRecord(*row)


def get_material(
    sqlite_url: str, material_id: str, *, course_id: str
) -> MaterialRecord | None:
    """Return a material constrained to its owning course."""
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM materials WHERE id = ? AND course_id = ?",
            (material_id, course_id),
        ).fetchone()
    return MaterialRecord(*row) if row else None


def get_material_in_connection(
    database: sqlite3.Connection, material_id: str, *, course_id: str
) -> MaterialRecord | None:
    """Read a material using an existing transaction/connection."""
    row = database.execute(
        f"SELECT {_COLUMNS} FROM materials WHERE id = ? AND course_id = ?",
        (material_id, course_id),
    ).fetchone()
    return MaterialRecord(*row) if row else None


def list_materials(sqlite_url: str, *, course_id: str) -> list[MaterialRecord]:
    """List one course's materials, ``parse_status`` and ``task_id`` read from the latest created
    task (D-16, ADR-021).

    The latest task is the one with the greatest ``created_at``; ties fall back to insertion
    order (``rowid``). A material without any task keeps its column value (the ``queued``
    default). Rows are ordered by ``uploaded_at`` then ``id`` so the listing is stable.
    """
    with connect(sqlite_url) as database:
        rows = database.execute(
            """SELECT m.id, m.course_id, m.filename, m.format, m.size_bytes, m.content_hash,
                      m.storage_name,
                      COALESCE(latest.stage, m.parse_status) AS parse_status,
                      m.uploaded_at,
                      latest.id AS task_id
               FROM materials AS m
               LEFT JOIN processing_tasks AS latest
                 ON latest.rowid = (
                    SELECT t.rowid FROM processing_tasks AS t
                    WHERE t.course_id = m.course_id AND t.document_id = m.id
                    ORDER BY t.created_at DESC, t.rowid DESC
                    LIMIT 1
                 )
               WHERE m.course_id = ?
               ORDER BY m.uploaded_at, m.id""",
            (course_id,),
        ).fetchall()
    return [MaterialRecord(*row) for row in rows]


#: 删除资料时的任务阶段分组（ADR-021 决定 2）；其余阶段即未结束。
_ENDED_WITHOUT_CONTRIBUTION = frozenset({"failed", "cancelled"})
_CONTRIBUTED = frozenset({"awaiting_review", "completed"})


@dataclass(frozen=True)
class MaterialDeleted:
    storage_name: str


@dataclass(frozen=True)
class MaterialNotDeletable:
    stage: str
    reason: Literal["processing", "contributed", "cleanup_pending"]


def delete_material(
    sqlite_url: str, material_id: str, *, course_id: str
) -> MaterialDeleted | MaterialNotDeletable | None:
    """Delete a material that never contributed to the graph (ADR-021); ``None`` if not found.

    Runs in one ``BEGIN IMMEDIATE`` transaction: the task stages are re-read under the write lock,
    so a task cannot change stage between the check and the delete. The stored file is not
    touched here; the caller removes it after commit.
    """
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            outcome = _delete_material(database, material_id, course_id=course_id)
            database.execute("COMMIT" if isinstance(outcome, MaterialDeleted) else "ROLLBACK")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return outcome


def _delete_material(
    database: sqlite3.Connection, material_id: str, *, course_id: str
) -> MaterialDeleted | MaterialNotDeletable | None:
    material = get_material_in_connection(database, material_id, course_id=course_id)
    if material is None:
        return None
    tasks = database.execute(
        """SELECT stage, cleanup_pending FROM processing_tasks
           WHERE course_id = ? AND document_id = ?
           ORDER BY created_at DESC, rowid DESC""",
        (course_id, material_id),
    ).fetchall()
    for stage, _ in tasks:
        if stage not in _ENDED_WITHOUT_CONTRIBUTION and stage not in _CONTRIBUTED:
            return MaterialNotDeletable(stage, "processing")
    for stage, _ in tasks:
        if stage in _CONTRIBUTED:
            return MaterialNotDeletable(stage, "contributed")
    for stage, cleanup_pending in tasks:
        if cleanup_pending:
            return MaterialNotDeletable(stage, "cleanup_pending")

    scope = (course_id, material_id)
    database.execute("DELETE FROM chunks WHERE course_id = ? AND material_id = ?", scope)
    database.execute("DELETE FROM task_revisions WHERE course_id = ? AND material_id = ?", scope)
    database.execute("DELETE FROM material_revisions WHERE course_id = ? AND material_id = ?", scope)
    # SSE 票据随 processing_tasks 外键级联删除（迁移 006）。
    database.execute("DELETE FROM processing_tasks WHERE course_id = ? AND document_id = ?", scope)
    database.execute("DELETE FROM materials WHERE course_id = ? AND id = ?", scope)
    return MaterialDeleted(material.storage_name)
