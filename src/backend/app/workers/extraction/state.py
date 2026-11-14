"""Internal extraction.state responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from app.repositories.extraction_checkpoints import write_checkpoint
from app.repositories.task_leases import (
    Lease,
    LeaseLost,
    leased_transaction,
    release_after_transient_failure,
)
from app.repositories.tasks import read_leased_task
from app.services.task_state import Applied, TaskError, TaskState, TransitionEvent, apply_event
from app.workers.extraction.types import (
    ExtractOutcome,
    ExtractStatus,
    NEXT_STAGE,
    STAGE,
    _MESSAGES,
    _NOW_TEXT,
    _UnitResult,
)

# ---------------------------------------------------------------- 带令牌的读写


def _state_in(database: sqlite3.Connection, lease: Lease) -> TaskState:
    row = read_leased_task(database, lease.task_id, lease.token)
    if row is None:
        raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    return TaskState(row.stage, row.progress, row.cancel_requested)


def _write_progress(database: sqlite3.Connection, lease: Lease, state: TaskState, progress: float) -> None:
    decision = apply_event(state, TransitionEvent("progress", progress=progress))
    if not isinstance(decision, Applied) or not decision.changed:
        return  # 低于当前值（接管后）或超出区间：不写（I2）
    database.execute(
        f"""UPDATE processing_tasks SET progress = ?, updated_at = {_NOW_TEXT}
            WHERE id = ? AND lease_token = ? AND stage = ? AND progress <= ?""",
        (decision.state.progress, lease.task_id, lease.token, STAGE, decision.state.progress),
    )


def _write_unit(
    sqlite_url: str, lease: Lease, kind: str, unit_id: str, result: _UnitResult, progress: float
) -> bool:
    """块/小节边界：取消标志为真 → 不写并返回 ``False``；否则写检查点与进度。"""
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        state = _state_in(database, lease)
        if state.stage != STAGE:
            raise RuntimeError(f"task {lease.task_id} left the {STAGE} stage under this lease")
        if state.cancel_requested:
            return False
        write_checkpoint(
            database,
            task_id=lease.task_id,
            course_id=lease.course_id,
            unit_kind=kind,  # type: ignore[arg-type]
            unit_id=unit_id,
            status=result.status,  # type: ignore[arg-type]
            attempts=result.attempts,
            error_code=result.error_code,
            result=result.result,
            metadata=result.metadata,
        )
        _write_progress(database, lease, state, progress)
    return True


def _boundary(sqlite_url: str, lease: Lease, event: str) -> TaskState:
    """C08 ``checkpoint``/``stage_done``：取消 → T8（清空租约）；``stage_done`` 否则 T4。"""
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        decision = apply_event(_state_in(database, lease), TransitionEvent(event))
        if not isinstance(decision, Applied):
            raise RuntimeError(f"{event} rejected for task {lease.task_id}: {decision.reason}")
        state = decision.state
        if state.stage == "cancelled":
            changed = database.execute(
                f"""UPDATE processing_tasks
                    SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL,
                        lease_expires_at = NULL, updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 1""",
                (lease.task_id, lease.token, STAGE),
            ).rowcount
        elif state.stage == NEXT_STAGE:
            changed = database.execute(
                f"""UPDATE processing_tasks SET stage = ?, progress = ?, updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 0""",
                (NEXT_STAGE, state.progress, lease.task_id, lease.token, STAGE),
            ).rowcount
        else:
            return state
        if changed != 1:
            raise RuntimeError(f"{event} compare-and-swap on task {lease.task_id} matched no row")
    return state


def _fail(
    sqlite_url: str, lease: Lease, code: str, details: Mapping[str, object] | None, counts: Mapping[str, int],
    *, message: str | None = None,
) -> ExtractOutcome:
    message = message or _MESSAGES[code]
    error = TaskError(code, message, details)
    encoded = None if details is None else json.dumps(dict(details), ensure_ascii=False, sort_keys=True)
    try:
        with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
            decision = apply_event(_state_in(database, lease), TransitionEvent("fail", error=error))
            if not isinstance(decision, Applied):
                raise RuntimeError(f"fail rejected for task {lease.task_id}: {decision.reason}")
            changed = database.execute(
                f"""UPDATE processing_tasks
                    SET stage = 'failed', error_code = ?, error_message = ?, error_details = ?,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                        updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ?""",
                (code, message, encoded, lease.task_id, lease.token, STAGE),
            ).rowcount
            if changed != 1:
                raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    except LeaseLost:
        return _lost(lease)
    return ExtractOutcome(ExtractStatus.FAILED, lease.task_id, "failed", "error", error_code=code, **counts)


def _release(sqlite_url: str, lease: Lease, code: str, max_attempts: int, counts: Mapping[str, int]) -> ExtractOutcome:
    released = release_after_transient_failure(
        sqlite_url, lease.task_id, lease.token, code=code, max_attempts=max_attempts
    )
    if released.status == "released":
        return ExtractOutcome(ExtractStatus.RELEASED, lease.task_id, STAGE, None, not_before=released.not_before,
                              **counts)
    if released.status == "failed":
        return ExtractOutcome(ExtractStatus.FAILED, lease.task_id, "failed", "error", error_code=code, **counts)
    return _lost(lease)


def _lost(lease: Lease) -> ExtractOutcome:
    return ExtractOutcome(ExtractStatus.LOST, lease.task_id, None, None)
