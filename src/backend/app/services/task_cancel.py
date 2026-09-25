"""Cooperative task cancellation (``specs/task-processing.md`` §4; ADR-010, ADR-011).

``cancel_task`` decides with the C08 pure transition (``cancel_request``) and commits the
result with a compare-and-swap on the same task row, inside one SQLite ``BEGIN IMMEDIATE``
transaction. C09 claims and every lease-token write (``leased_transaction`` / ``fence``, the
worker's T5 ``stage = merging AND cancel_requested = 0``) take the same write lock, so a cancel
and a worker write on the same row are serialized and the first committed writer wins:

* ``queued`` → ``cancelled`` with ``cancel_requested = true`` (T3); a racing claim then
  matches no row because *C* requires ``stage = queued`` or a lease-free processing stage.
* ``parsing`` / ``extracting`` / ``merging`` → only the durable flag is set. The lease is left
  untouched: the worker is not killed and finishes at its next checkpoint (T8), or the
  reclaimer does it after the lease expires (§8.2).
* the flag already set → idempotent, nothing is written and no event is due.
* ``persisting`` / ``awaiting_review`` / terminal stages → ``TaskNotCancellable`` with the
  closed ``{stage, reason}`` details; nothing is written (I3).

Pushing the SSE event named by ``CancelOutcome.sse_event`` belongs to the task event stream
(C11). The SQL lives here only because ``repositories/`` was outside this task's file lock;
see ``docs/handoffs/claude-c10.md`` (pending item on moving it to ``repositories/tasks.py``).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from app.repositories.sqlite import connect
from app.services.task_state import (
    Applied,
    TaskError,
    TaskState,
    TransitionEvent,
    apply_event,
)

_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_COLUMNS = (
    "id, course_id, document_id, stage, progress, cancel_requested, created_at, updated_at, "
    "error_code, error_message, error_details"
)
# §4: the closed set of rejection reasons, each tied to the stages that produce it.
REJECTION_REASONS = frozenset({"persisting_uninterruptible", "processing_finished", "already_terminal"})
# One retry after a lost compare-and-swap is enough: inside BEGIN IMMEDIATE no other writer can
# move the row, so a second miss means the row is inconsistent and must not be papered over.
_MAX_ROUNDS = 2


@dataclass(frozen=True)
class TaskSnapshot:
    """The persisted task fields the contract ``Task`` snapshot needs."""

    id: str
    course_id: str
    document_id: str
    stage: str
    progress: float
    cancel_requested: bool
    created_at: str
    updated_at: str
    error: TaskError | None = None


@dataclass(frozen=True)
class CancelOutcome:
    """An accepted cancel (HTTP 200).

    ``changed`` is whether this call wrote anything; ``sse_event`` is the task-stream event the
    write calls for (``cancelled`` after T3, ``stage`` after setting the flag) or ``None`` for an
    idempotent repeat, which pushes nothing (§4).
    """

    task: TaskSnapshot
    changed: bool
    sse_event: str | None


class TaskNotFound(LookupError):
    """No task with this id in this course; callers answer 404 without any snapshot field."""


class TaskNotCancellable(Exception):
    """The §4 rejection: 409 ``TASK_NOT_CANCELLABLE`` with ``details = {stage, reason}``."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"task in stage {stage} cannot be cancelled: {reason}")
        self.stage = stage
        self.reason = reason

    @property
    def details(self) -> dict[str, str]:
        return {"stage": self.stage, "reason": self.reason}


def _snapshot_from_row(row: tuple[object, ...]) -> TaskSnapshot:
    error = None
    if row[8] is not None:
        details = json.loads(row[10]) if row[10] is not None else None
        error = TaskError(code=row[8], message=row[9], details=details)
    return TaskSnapshot(
        id=row[0],
        course_id=row[1],
        document_id=row[2],
        stage=row[3],
        progress=float(row[4]),
        cancel_requested=bool(row[5]),
        created_at=row[6],
        updated_at=row[7],
        error=error,
    )


def _read_task(database: sqlite3.Connection, task_id: str, course_id: str) -> TaskSnapshot | None:
    row = database.execute(
        f"SELECT {_COLUMNS} FROM processing_tasks WHERE id = ? AND course_id = ?",
        (task_id, course_id),
    ).fetchone()
    return _snapshot_from_row(row) if row else None


def _write_cancel(database: sqlite3.Connection, snapshot: TaskSnapshot, target: TaskState) -> bool:
    """Compare-and-swap: write ``target`` only if the row still holds what was decided on."""
    return database.execute(
        f"""UPDATE processing_tasks
            SET stage = ?, cancel_requested = 1, updated_at = {_NOW_TEXT}
            WHERE id = ? AND course_id = ? AND stage = ? AND cancel_requested = 0
              AND stage IN ('queued', 'parsing', 'extracting', 'merging')""",
        (target.stage, snapshot.id, snapshot.course_id, snapshot.stage),
    ).rowcount == 1


def _state_of(snapshot: TaskSnapshot) -> TaskState:
    return TaskState(
        stage=snapshot.stage,
        progress=snapshot.progress,
        cancel_requested=snapshot.cancel_requested,
        error=snapshot.error,
    )


def _non_empty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def cancel_task(sqlite_url: str, task_id: str, *, course_id: str) -> CancelOutcome:
    """Apply one cancel request to ``task_id`` in ``course_id`` (§4 matrix).

    Raises ``TaskNotFound`` when the task is not in the course and ``TaskNotCancellable`` for
    ``persisting``, ``awaiting_review`` and terminal stages; neither writes anything.
    """
    _non_empty("task_id", task_id)
    _non_empty("course_id", course_id)
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            outcome = _cancel_in_transaction(database, task_id, course_id)
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return outcome


def _cancel_in_transaction(
    database: sqlite3.Connection, task_id: str, course_id: str
) -> CancelOutcome:
    for _ in range(_MAX_ROUNDS):
        snapshot = _read_task(database, task_id, course_id)
        if snapshot is None:
            raise TaskNotFound(task_id)
        decision = apply_event(_state_of(snapshot), TransitionEvent("cancel_request"))
        if not isinstance(decision, Applied):
            if decision.reason in REJECTION_REASONS:
                raise TaskNotCancellable(snapshot.stage, decision.reason)
            raise RuntimeError(f"task {task_id} has an inconsistent state: {decision.reason}")
        if not decision.changed:
            return CancelOutcome(snapshot, changed=False, sse_event=None)
        if _write_cancel(database, snapshot, decision.state):
            written = _read_task(database, task_id, course_id)
            if written is None:  # pragma: no cover - the row was just updated in this transaction
                raise RuntimeError(f"task {task_id} vanished during cancel")
            event = "cancelled" if written.stage == "cancelled" else "stage"
            return CancelOutcome(written, changed=True, sse_event=event)
    raise RuntimeError(f"task {task_id} kept changing during cancel")
