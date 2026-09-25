"""Persistence for queued processing tasks and atomic material/task creation."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.repositories.materials import (
    MaterialRecord,
    get_material_in_connection,
    insert_material,
)
from app.repositories.sqlite import connect


class StoredFileMetadata(Protocol):
    """Metadata returned by C05; the repository never reads or stores its path."""

    original_filename: str
    format: str
    size_bytes: int
    content_hash: str
    storage_name: str


@dataclass(frozen=True)
class TaskRecord:
    id: str
    course_id: str
    document_id: str
    stage: str
    progress: float
    cancel_requested: bool
    created_at: str
    updated_at: str
    idempotency_key: str


@dataclass(frozen=True)
class MaterialTaskResult:
    material: MaterialRecord
    task: TaskRecord
    created: bool


_TASK_COLUMNS = (
    "id, course_id, document_id, stage, progress, cancel_requested, created_at, "
    "updated_at, idempotency_key"
)


def _task_from_row(row: tuple[object, ...]) -> TaskRecord:
    return TaskRecord(
        id=row[0],
        course_id=row[1],
        document_id=row[2],
        stage=row[3],
        progress=float(row[4]),
        cancel_requested=bool(row[5]),
        created_at=row[6],
        updated_at=row[7],
        idempotency_key=row[8],
    )


def _insert_task(
    database: sqlite3.Connection,
    *,
    task_id: str,
    course_id: str,
    document_id: str,
    idempotency_key: str,
) -> TaskRecord:
    """Insert the initial queued row on the caller's connection."""
    database.execute(
        """INSERT INTO processing_tasks
           (id, course_id, document_id, idempotency_key)
           VALUES (?, ?, ?, ?)""",
        (task_id, course_id, document_id, idempotency_key),
    )
    row = database.execute(
        f"SELECT {_TASK_COLUMNS} FROM processing_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        raise RuntimeError("task insert did not return a row")
    return _task_from_row(row)


def create_material_task(
    sqlite_url: str,
    *,
    course_id: str,
    stored_file: StoredFileMetadata,
    idempotency_key: str,
) -> MaterialTaskResult:
    """Create a material and its queued task atomically.

    The key is unique within a course. A retry returns the original pair and
    ``created=False`` so an upload caller can clean up a newly stored duplicate.
    ``stored_file`` is the C05 StoredFile value; only its metadata is persisted.
    """
    if not isinstance(course_id, str) or not course_id.strip():
        raise ValueError("course_id must be a non-empty string")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key must be a non-empty string")
    if len(idempotency_key) > 255:
        raise ValueError("idempotency_key must be at most 255 characters")

    material_id = uuid4().hex
    task_id = uuid4().hex
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            existing = database.execute(
                f"SELECT {_TASK_COLUMNS} FROM processing_tasks "
                "WHERE course_id = ? AND idempotency_key = ?",
                (course_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                task = _task_from_row(existing)
                material = get_material_in_connection(
                    database, task.document_id, course_id=course_id
                )
                if material is None:
                    raise RuntimeError("idempotent task references a missing material")
                result = MaterialTaskResult(material=material, task=task, created=False)
            else:
                material = insert_material(
                    database,
                    material_id=material_id,
                    course_id=course_id,
                    filename=stored_file.original_filename,
                    format=stored_file.format,
                    size_bytes=stored_file.size_bytes,
                    content_hash=stored_file.content_hash,
                    storage_name=stored_file.storage_name,
                )
                task = _insert_task(
                    database,
                    task_id=task_id,
                    course_id=course_id,
                    document_id=material.id,
                    idempotency_key=idempotency_key,
                )
                result = MaterialTaskResult(material=material, task=task, created=True)
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return result


def get_task(
    sqlite_url: str, task_id: str, *, course_id: str | None = None
) -> TaskRecord | None:
    """Return a task, optionally constrained to its owning course."""
    where = "id = ?" if course_id is None else "id = ? AND course_id = ?"
    parameters = (task_id,) if course_id is None else (task_id, course_id)
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_TASK_COLUMNS} FROM processing_tasks WHERE {where}", parameters
        ).fetchone()
    return _task_from_row(row) if row else None
