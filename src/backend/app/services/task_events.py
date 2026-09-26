"""Task snapshot and task SSE stream (``specs/task-processing.md`` §7; ``events.v1.md`` §2).

The API and the worker are different processes sharing one SQLite file (§8.1), so there is no
in-process event source: every stream polls its task row and pushes only real changes.

* On connect the current snapshot goes out first: ``stage`` for a non-terminal task, otherwise
  ``done`` / ``error`` / ``cancelled``.
* Afterwards a ``stage`` event is pushed when the task enters a later stage, its progress rises
  within the stage, or ``cancel_requested`` turns true. A stage or progress regression (which
  I1/I2 forbid) is never pushed; emitted progress is monotonic per connection.
* ``awaiting_review`` (and every terminal event) ends the connection: exactly one end event is
  sent and the stream stops. If polling misses ``awaiting_review`` because the task was already
  published, the processing connection still ends with an ``awaiting_review`` event, never
  ``done`` (§7: ``done`` only answers a connection opened after publication).
* A ``:ping`` comment is sent every ``heartbeat_seconds`` (15 by default).

Ticket authorization (``specs/identity-access.md`` §5.2) is ``authorize_ticket``: redeem the
one-time ticket (C16), re-check the ticket owner's account, then re-run the §4.1 task checks.
The event source is the ``processing_tasks`` row itself, read through ``repositories/tasks.py``
(``get_task_snapshot``, TD-02) and mapped by C10's ``snapshot_from_row``, the single row →
``TaskSnapshot`` mapping.
"""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import anyio

from app.repositories.accounts import find_by_id
from app.repositories.event_tickets import redeem_ticket
from app.repositories.tasks import get_task_snapshot
from app.services.access import AccessService, CourseAccess, unauthenticated
from app.services.task_cancel import TaskSnapshot, snapshot_from_row
from app.services.task_state import TaskError

DEFAULT_HEARTBEAT_SECONDS = 15.0
DEFAULT_POLL_SECONDS = 1.0
PING_FRAME = b":ping\n\n"

# Main line of the processing phase; terminal stages are handled separately.
_PROCESSING_ORDER = ("queued", "parsing", "extracting", "merging", "persisting", "awaiting_review")
_RANK = {stage: rank for rank, stage in enumerate(_PROCESSING_ORDER)}
_TERMINAL_EVENT = {"completed": "done", "failed": "error", "cancelled": "cancelled"}
_AWAITING_REVIEW_PROGRESS = 0.95


# --- snapshot -----------------------------------------------------------------------------------


def load_task(sqlite_url: str, task_id: str, *, course_id: str) -> TaskSnapshot | None:
    """The task row constrained to its course (I7), or ``None``."""
    row = get_task_snapshot(sqlite_url, task_id, course_id=course_id)
    return snapshot_from_row(row) if row else None


def _error_body(error: TaskError) -> dict[str, Any]:
    body: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.details is not None:
        body["details"] = json.loads(json.dumps(error.details))  # plain dict/list copies
    return body


def task_body(snapshot: TaskSnapshot) -> dict[str, Any]:
    """Contract ``Task`` JSON for ``GET /tasks/{tid}``; ``error`` only for ``failed`` (I4)."""
    body: dict[str, Any] = {
        "id": snapshot.id,
        "course_id": snapshot.course_id,
        "document_id": snapshot.document_id,
        "stage": snapshot.stage,
        "progress": 1 if snapshot.stage == "completed" else snapshot.progress,
        "cancel_requested": snapshot.cancel_requested,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
    }
    if snapshot.stage == "failed" and snapshot.error is not None:
        body["error"] = _error_body(snapshot.error)
    return body


# --- events -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskStreamEvent:
    """One SSE event: ``name`` is the ``event:`` line, ``data`` the contract ``TaskEvent``."""

    name: str
    data: dict[str, Any]
    final: bool

    def encode(self) -> bytes:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"event: {self.name}\ndata: {payload}\n\n".encode("utf-8")


def _stage_event(task_id: str, stage: str, progress: float, cancel_requested: bool) -> TaskStreamEvent:
    return TaskStreamEvent(
        name="stage",
        data={
            "task_id": task_id,
            "stage": stage,
            "progress": progress,
            "cancel_requested": cancel_requested,
        },
        final=stage == "awaiting_review",
    )


def _terminal_event(snapshot: TaskSnapshot, progress: float) -> TaskStreamEvent:
    name = _TERMINAL_EVENT[snapshot.stage]
    data: dict[str, Any] = {"task_id": snapshot.id, "stage": snapshot.stage}
    if name == "done":
        data["progress"] = 1
    elif name == "error":
        data["progress"] = progress
        data["error"] = _error_body(snapshot.error) if snapshot.error else {
            "code": "INTERNAL_ERROR", "message": "任务失败"
        }
        data["cancel_requested"] = snapshot.cancel_requested
    else:
        data["progress"] = progress
        data["cancel_requested"] = True  # I5: cancelled ⇒ cancel_requested
    return TaskStreamEvent(name=name, data=data, final=True)


def snapshot_event(snapshot: TaskSnapshot) -> TaskStreamEvent:
    """The first event of every connection: the current snapshot."""
    if snapshot.stage in _TERMINAL_EVENT:
        return _terminal_event(snapshot, snapshot.progress)
    return _stage_event(snapshot.id, snapshot.stage, snapshot.progress, snapshot.cancel_requested)


class EventDiffer:
    """What one connection pushes next, given the last snapshot it pushed."""

    def __init__(self, first: TaskSnapshot) -> None:
        self._stage = first.stage
        self._progress = first.progress
        self._cancel = first.cancel_requested

    def next(self, current: TaskSnapshot) -> TaskStreamEvent | None:
        progress = max(self._progress, current.progress)
        if current.stage == "completed":
            # Published between two polls: the processing connection still ends here (§7).
            return _stage_event(current.id, "awaiting_review", _AWAITING_REVIEW_PROGRESS, False)
        if current.stage in _TERMINAL_EVENT:
            return _terminal_event(current, progress)
        if current.stage not in _RANK or _RANK[current.stage] < _RANK[self._stage]:
            return None  # I1: never push a stage regression
        advanced = _RANK[current.stage] > _RANK[self._stage]
        rose = current.progress > self._progress
        flagged = current.cancel_requested and not self._cancel
        if not (advanced or rose or flagged):
            return None  # no change, or a progress regression (I2)
        self._stage = current.stage
        self._progress = progress
        self._cancel = self._cancel or current.cancel_requested
        if current.stage == "awaiting_review":
            progress = _AWAITING_REVIEW_PROGRESS
        return _stage_event(current.id, current.stage, progress, self._cancel)


# --- streams ------------------------------------------------------------------------------------


class TaskEventStreams:
    """Stream settings plus the live-subscriber registry (released when a client leaves)."""

    def __init__(
        self,
        *,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if poll_seconds <= 0 or heartbeat_seconds <= 0:
            raise ValueError("poll and heartbeat intervals must be positive")
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._subscribers: Counter[str] = Counter()

    def subscribers(self, task_id: str) -> int:
        with self._lock:
            return self._subscribers[task_id]

    def total(self) -> int:
        with self._lock:
            return sum(self._subscribers.values())

    @contextmanager
    def _subscribed(self, task_id: str) -> Iterator[None]:
        with self._lock:
            self._subscribers[task_id] += 1
        try:
            yield
        finally:
            with self._lock:
                self._subscribers[task_id] -= 1
                if self._subscribers[task_id] <= 0:
                    del self._subscribers[task_id]

    async def stream(
        self, load: Callable[[], TaskSnapshot | None], task_id: str
    ) -> AsyncIterator[bytes]:
        """Encoded SSE frames for one connection; ends after its single end event.

        ``load`` reads the task row (blocking; run in a worker thread). Cancellation or
        ``aclose()`` on client disconnect runs the ``finally`` that releases the subscription.
        """
        with self._subscribed(task_id):
            snapshot = await anyio.to_thread.run_sync(load)
            if snapshot is None:
                return
            first = snapshot_event(snapshot)
            yield first.encode()
            if first.final:
                return
            differ = EventDiffer(snapshot)
            now = self._clock()
            next_poll = now + self.poll_seconds
            next_ping = now + self.heartbeat_seconds
            while True:
                await anyio.sleep(max(0.0, min(next_poll, next_ping) - self._clock()))
                now = self._clock()
                if now >= next_ping:
                    yield PING_FRAME
                    next_ping = now + self.heartbeat_seconds
                if now < next_poll:
                    continue
                next_poll = now + self.poll_seconds
                current = await anyio.to_thread.run_sync(load)
                if current is None:
                    return
                event = differ.next(current)
                if event is None:
                    continue
                yield event.encode()
                if event.final:
                    return


# --- ticket authorization -------------------------------------------------------------------------


def authorize_ticket(
    sqlite_url: str,
    access: AccessService,
    *,
    ticket: str | None,
    task_id: str,
    now: float,
) -> CourseAccess:
    """§5.2: redeem the one-time ticket, re-check its owner, then the §4.1 steps 2–4.

    401 for a missing/invalid/expired/used/foreign ticket or a disabled owner; afterwards the
    ``streamTaskEvents`` matrix row (404 non-member or missing task, 403 ``ROLE_FORBIDDEN``).
    """
    if not ticket:
        raise unauthenticated()
    user_id = redeem_ticket(sqlite_url, ticket=ticket, task_id=task_id, now=now)
    if user_id is None:
        raise unauthenticated()
    account = find_by_id(sqlite_url, user_id)
    if account is None or account.disabled_at is not None:
        raise unauthenticated()
    return access.require_task(account, task_id)
