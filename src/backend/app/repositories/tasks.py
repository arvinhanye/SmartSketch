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
    sqlite_url: str, task_id: str, *, course_id: str
) -> TaskRecord | None:
    """Return a task constrained to its owning course."""
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_TASK_COLUMNS} FROM processing_tasks "
            "WHERE id = ? AND course_id = ?",
            (task_id, course_id),
        ).fetchone()
    return _task_from_row(row) if row else None


def find_task_course_id(sqlite_url: str, task_id: str) -> str | None:
    """Resolve ownership before C03 checks membership; never expose task details."""
    with connect(sqlite_url) as database:
        row = database.execute(
            "SELECT course_id FROM processing_tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return row[0] if row else None


# --- task read model (TD-02: moved from services/task_cancel.py, services/task_events.py and
# workers/parse_task.py; SQL and column lists unchanged) ------------------------------------------

_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_SNAPSHOT_COLUMNS = (
    "id, course_id, document_id, stage, progress, cancel_requested, created_at, updated_at, "
    "error_code, error_message, error_details"
)


@dataclass(frozen=True)
class TaskSnapshotRow:
    """One ``processing_tasks`` row as the contract ``Task`` snapshot needs it.

    ``error_details_json`` stays the stored JSON text: turning the ``error_*`` columns into a
    ``TaskError`` is the service layer's single mapping (``services.task_cancel.snapshot_from_row``),
    because this layer must not depend on ``app.services``.
    """

    id: str
    course_id: str
    document_id: str
    stage: str
    progress: float
    cancel_requested: bool
    created_at: str
    updated_at: str
    error_code: str | None
    error_message: str | None
    error_details_json: str | None


@dataclass(frozen=True)
class LeasedTaskRow:
    """The fields a worker needs from the row its lease token still owns."""

    course_id: str
    document_id: str
    stage: str
    progress: float
    cancel_requested: bool


def _snapshot_row(row: tuple[object, ...]) -> TaskSnapshotRow:
    return TaskSnapshotRow(
        id=row[0],
        course_id=row[1],
        document_id=row[2],
        stage=row[3],
        progress=float(row[4]),
        cancel_requested=bool(row[5]),
        created_at=row[6],
        updated_at=row[7],
        error_code=row[8],
        error_message=row[9],
        error_details_json=row[10],
    )


def read_task_snapshot(
    database: sqlite3.Connection, task_id: str, *, course_id: str
) -> TaskSnapshotRow | None:
    """Read the task row on the caller's connection (and transaction), constrained to its course."""
    row = database.execute(
        f"SELECT {_SNAPSHOT_COLUMNS} FROM processing_tasks WHERE id = ? AND course_id = ?",
        (task_id, course_id),
    ).fetchone()
    return _snapshot_row(row) if row else None


def get_task_snapshot(
    sqlite_url: str, task_id: str, *, course_id: str
) -> TaskSnapshotRow | None:
    """``read_task_snapshot`` on a fresh connection (C11 snapshot and SSE polling)."""
    with connect(sqlite_url) as database:
        return read_task_snapshot(database, task_id, course_id=course_id)


def mark_cancel_requested(
    database: sqlite3.Connection,
    *,
    task_id: str,
    course_id: str,
    expected_stage: str,
    target_stage: str,
) -> bool:
    """C10 compare-and-swap on the caller's ``BEGIN IMMEDIATE`` transaction.

    Sets ``cancel_requested`` and moves to ``target_stage`` only while the row, in its course,
    still holds ``expected_stage`` with the flag clear and a cancellable stage. ``True`` iff one
    row was written.
    """
    return database.execute(
        f"""UPDATE processing_tasks
            SET stage = ?, cancel_requested = 1, updated_at = {_NOW_TEXT}
            WHERE id = ? AND course_id = ? AND stage = ? AND cancel_requested = 0
              AND stage IN ('queued', 'parsing', 'extracting', 'merging')""",
        (target_stage, task_id, course_id, expected_stage),
    ).rowcount == 1


def read_leased_task(
    database: sqlite3.Connection, task_id: str, lease_token: str
) -> LeasedTaskRow | None:
    """D11: read the row only while ``lease_token`` still owns it; ``None`` means the lease is lost.

    The filter is the lease token (unique per claim), not ``course_id``: the worker compares the
    returned course and material with its lease and treats a mismatch as a caller defect.
    """
    row = database.execute(
        """SELECT course_id, document_id, stage, progress, cancel_requested
           FROM processing_tasks WHERE id = ? AND lease_token = ?""",
        (task_id, lease_token),
    ).fetchone()
    if row is None:
        return None
    return LeasedTaskRow(row[0], row[1], row[2], float(row[3]), bool(row[4]))
