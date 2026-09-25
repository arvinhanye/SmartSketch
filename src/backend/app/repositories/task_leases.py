"""Worker claim, lease, reclaim and release for processing tasks.

Implements ``specs/task-processing.md`` §8.2 and §8.3 (ADR-011 decisions 2-4):

* ``claim_next`` is one conditional ``UPDATE … RETURNING`` guarded by the claimable
  condition *C*; a ``queued`` task is moved to ``parsing`` (T2) by the same statement.
* every later worker write carries ``WHERE id = ? AND lease_token = ?`` in the same SQLite
  transaction (``leased_transaction`` / ``fence``); zero rows raises ``LeaseLost``.
* ``reclaim_expired`` runs the reclaim order: cancel requested → T8, attempts used up → T9
  ``TASK_ATTEMPTS_EXHAUSTED``, otherwise leave for takeover; it also lists pending cleanups.
* ``release_after_transient_failure`` / ``release_on_shutdown`` are the active releases.

All times are evaluated by SQLite (``unixepoch()``), never passed in by the worker. Pushing
SSE events for tasks this module moves to a terminal stage is the caller's job (C11).
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from app.repositories.sqlite import connect
from app.services.task_state import FAILURE_CODE_STAGES

PROCESSING_STAGES = ("parsing", "extracting", "merging", "persisting")
CANCELLABLE_STAGES = ("parsing", "extracting", "merging")
# §8.3: the only stage-level temporary faults that release and back off.
TRANSIENT_FAULT_CODES = frozenset({"STORAGE_UNAVAILABLE", "LLM_UNAVAILABLE"})
BACKOFF_BASE_SECONDS = 30

_FAULT_MESSAGES = {
    "STORAGE_UNAVAILABLE": "存储不可用，任务重试次数已用尽",
    "LLM_UNAVAILABLE": "模型服务不可用，任务重试次数已用尽",
}
_EXHAUSTED_MESSAGE = "任务多次中断，重试次数已用尽"
_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_PROCESSING_SQL = "('parsing', 'extracting', 'merging', 'persisting')"
_CANCELLABLE_SQL = "('parsing', 'extracting', 'merging')"
_LEASE_FREE_SQL = "(lease_expires_at IS NULL OR lease_expires_at < unixepoch())"
# Claimable condition C (§8.2).
_CLAIMABLE_SQL = (
    "attempt < :max_attempts AND not_before <= unixepoch() AND cancel_requested = 0 "
    f"AND (stage = 'queued' OR (stage IN {_PROCESSING_SQL} AND {_LEASE_FREE_SQL}))"
)


class LeaseLost(RuntimeError):
    """The token no longer owns the task; the worker must stop writing for it."""


@dataclass(frozen=True)
class Lease:
    task_id: str
    course_id: str
    document_id: str
    stage: str
    progress: float
    attempt: int
    owner: str
    token: str
    expires_at: int


@dataclass(frozen=True)
class ReclaimedTask:
    task_id: str
    course_id: str
    stage: str


@dataclass(frozen=True)
class ReclaimResult:
    cancelled: tuple[ReclaimedTask, ...]
    failed: tuple[ReclaimedTask, ...]
    cleanup_pending: tuple[ReclaimedTask, ...]


@dataclass(frozen=True)
class ReleaseOutcome:
    """``released`` (backed off), ``failed`` (T9 on the last attempt) or ``lost`` (stale token)."""

    status: str
    not_before: int | None = None


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_empty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@contextmanager
def _immediate(sqlite_url: str) -> Iterator[sqlite3.Connection]:
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            yield database
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise


def claim_next(
    sqlite_url: str, *, owner: str, lease_seconds: int, max_attempts: int
) -> Lease | None:
    """Claim the oldest claimable task, or return ``None`` if none (or another worker won).

    Callers run ``reclaim_expired`` before each claim (§8.2); a zero-row result is final
    for this call and is not retried against the same row.
    """
    _non_empty("owner", owner)
    _positive_int("lease_seconds", lease_seconds)
    _positive_int("max_attempts", max_attempts)
    token = secrets.token_hex(16)
    params = {
        "owner": owner,
        "token": token,
        "lease_seconds": lease_seconds,
        "max_attempts": max_attempts,
    }
    with _immediate(sqlite_url) as database:
        row = database.execute(
            f"""UPDATE processing_tasks
                SET lease_owner = :owner,
                    lease_token = :token,
                    lease_expires_at = unixepoch() + :lease_seconds,
                    attempt = attempt + 1,
                    stage = CASE WHEN stage = 'queued' THEN 'parsing' ELSE stage END,
                    updated_at = {_NOW_TEXT}
                WHERE id = (
                    SELECT id FROM processing_tasks WHERE {_CLAIMABLE_SQL}
                    ORDER BY created_at, id LIMIT 1
                ) AND {_CLAIMABLE_SQL}
                RETURNING id, course_id, document_id, stage, progress, attempt,
                          lease_owner, lease_token, lease_expires_at""",
            params,
        ).fetchone()
    if row is None:
        return None
    return Lease(
        task_id=row[0],
        course_id=row[1],
        document_id=row[2],
        stage=row[3],
        progress=float(row[4]),
        attempt=row[5],
        owner=row[6],
        token=row[7],
        expires_at=row[8],
    )


def renew_lease(sqlite_url: str, task_id: str, token: str, *, lease_seconds: int) -> int | None:
    """Heartbeat: extend the lease to now + ``lease_seconds``; ``None`` means the lease is lost."""
    _non_empty("token", token)
    _positive_int("lease_seconds", lease_seconds)
    with connect(sqlite_url) as database:
        row = database.execute(
            """UPDATE processing_tasks SET lease_expires_at = unixepoch() + ?
               WHERE id = ? AND lease_token = ?
               RETURNING lease_expires_at""",
            (lease_seconds, task_id, token),
        ).fetchone()
    return row[0] if row else None


def fence(database: sqlite3.Connection, task_id: str, token: str) -> None:
    """Token-conditioned task-row update inside the caller's open transaction.

    Raises ``LeaseLost`` when it matches no row; the caller must roll back the whole
    transaction and stop all writes (including Neo4j) for this task.
    """
    _non_empty("token", token)
    if not database.in_transaction:
        raise RuntimeError("fence must run inside the caller's write transaction")
    changed = database.execute(
        "UPDATE processing_tasks SET lease_token = lease_token WHERE id = ? AND lease_token = ?",
        (task_id, token),
    ).rowcount
    if changed != 1:
        raise LeaseLost(f"lease on task {task_id} is no longer held by this token")


@contextmanager
def leased_transaction(sqlite_url: str, task_id: str, token: str) -> Iterator[sqlite3.Connection]:
    """Open ``BEGIN IMMEDIATE``, fence the lease, yield, then commit; roll back on any error."""
    with _immediate(sqlite_url) as database:
        fence(database, task_id, token)
        yield database


def _error_details(attempts: int, stage: str) -> str:
    return json.dumps({"attempts": attempts, "stage": stage}, ensure_ascii=False, sort_keys=True)


def reclaim_expired(sqlite_url: str, *, max_attempts: int) -> ReclaimResult:
    """Reclaim processing tasks whose lease expired or was released (§8.2 回收).

    Order: cancel requested → ``cancelled`` (T8, the reclaimer acts as the checkpoint);
    else ``attempt ≥ max_attempts`` → ``failed`` with ``TASK_ATTEMPTS_EXHAUSTED``;
    else untouched, waiting for takeover. Also lists ``failed`` tasks with
    ``cleanup_pending`` for the §8.4 cleanup retry. Returned terminal tasks need an SSE push.
    """
    _positive_int("max_attempts", max_attempts)
    with _immediate(sqlite_url) as database:
        cancelled = database.execute(
            f"""UPDATE processing_tasks
                SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = {_NOW_TEXT}
                WHERE stage IN {_CANCELLABLE_SQL} AND cancel_requested = 1 AND {_LEASE_FREE_SQL}
                RETURNING id, course_id, stage"""
        ).fetchall()
        failed = database.execute(
            f"""UPDATE processing_tasks
                SET error_code = 'TASK_ATTEMPTS_EXHAUSTED',
                    error_message = :message,
                    error_details = json_object('attempts', attempt, 'stage', stage),
                    stage = 'failed', lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = {_NOW_TEXT}
                WHERE stage IN {_PROCESSING_SQL} AND attempt >= :max_attempts
                    AND {_LEASE_FREE_SQL}
                RETURNING id, course_id, stage""",
            {"message": _EXHAUSTED_MESSAGE, "max_attempts": max_attempts},
        ).fetchall()
        cleanup = database.execute(
            """SELECT id, course_id, stage FROM processing_tasks
               WHERE stage = 'failed' AND cleanup_pending = 1 ORDER BY created_at, id"""
        ).fetchall()
    return ReclaimResult(
        cancelled=tuple(ReclaimedTask(*row) for row in sorted(cancelled, key=lambda r: r[0])),
        failed=tuple(ReclaimedTask(*row) for row in sorted(failed, key=lambda r: r[0])),
        cleanup_pending=tuple(ReclaimedTask(*row) for row in cleanup),
    )


def clear_cleanup_pending(sqlite_url: str, task_id: str, *, course_id: str) -> bool:
    """Clear the §8.4 cleanup marker after a successful cleanup, scoped to the course."""
    _non_empty("course_id", course_id)
    with connect(sqlite_url) as database:
        changed = database.execute(
            """UPDATE processing_tasks SET cleanup_pending = 0
               WHERE id = ? AND course_id = ? AND stage = 'failed' AND cleanup_pending = 1""",
            (task_id, course_id),
        ).rowcount
    return changed == 1


def release_after_transient_failure(
    sqlite_url: str, task_id: str, token: str, *, code: str, max_attempts: int
) -> ReleaseOutcome:
    """Active release after a stage-level temporary fault (§8.3 主动释放).

    Clears the lease and sets ``not_before = now + 30 s × 2^(attempt − 1)``; when the
    attempt was the last one it performs T9 with ``code`` and ``details = {attempts, stage}``
    instead. A stale token changes nothing and returns ``lost``.
    """
    _non_empty("token", token)
    _positive_int("max_attempts", max_attempts)
    if code not in TRANSIENT_FAULT_CODES:
        raise ValueError("code must be STORAGE_UNAVAILABLE or LLM_UNAVAILABLE")
    with _immediate(sqlite_url) as database:
        row = database.execute(
            "SELECT attempt, stage FROM processing_tasks WHERE id = ? AND lease_token = ?",
            (task_id, token),
        ).fetchone()
        if row is None:
            return ReleaseOutcome("lost")
        attempt, stage = row
        if attempt >= max_attempts:
            if stage not in FAILURE_CODE_STAGES[code]:
                raise ValueError(f"{code} is not a failure code for stage {stage}")
            database.execute(
                f"""UPDATE processing_tasks
                    SET stage = 'failed', error_code = ?, error_message = ?, error_details = ?,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                        updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ?""",
                (code, _FAULT_MESSAGES[code], _error_details(attempt, stage), task_id, token),
            )
            return ReleaseOutcome("failed")
        released = database.execute(
            f"""UPDATE processing_tasks
                SET lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    not_before = unixepoch() + ? * (1 << (attempt - 1)),
                    updated_at = {_NOW_TEXT}
                WHERE id = ? AND lease_token = ?
                RETURNING not_before""",
            (BACKOFF_BASE_SECONDS, task_id, token),
        ).fetchone()
    return ReleaseOutcome("released", released[0])


def release_on_shutdown(sqlite_url: str, task_id: str, token: str) -> bool:
    """Graceful-exit release: claimable at once and the attempt is not counted (§8.3 正常退出)."""
    _non_empty("token", token)
    with connect(sqlite_url) as database:
        changed = database.execute(
            f"""UPDATE processing_tasks
                SET lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    not_before = unixepoch(), attempt = attempt - 1, updated_at = {_NOW_TEXT}
                WHERE id = ? AND lease_token = ?""",
            (task_id, token),
        ).rowcount
    return changed == 1
