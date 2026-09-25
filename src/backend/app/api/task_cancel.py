"""POST /api/v1/tasks/{tid}/cancel — contract operation ``cancelTask`` (C10).

Protocol translation only: authorization is the shared ``task_teacher`` dependency (§4.1:
401 / 404 for non-members and missing tasks / 403 ``ROLE_FORBIDDEN``); the cancel decision,
the compare-and-swap and its serialization with worker writes live in
``app.services.task_cancel``. Every accepted cancel is HTTP 200 with the real ``stage`` and
``cancel_requested`` (``specs/task-processing.md`` §4); rejections are 409
``TASK_NOT_CANCELLABLE`` with the closed ``{stage, reason}`` details.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.dependencies import task_teacher
from app.schemas.errors import Error
from app.services.access import CourseAccess, not_found
from app.services.task_cancel import TaskNotCancellable, TaskNotFound, cancel_task

_NOT_CANCELLABLE_MESSAGE = "任务当前阶段不可取消，请按最新状态刷新"


class CancelledTaskSnapshot(BaseModel):
    """Contract ``Task`` as returned by a cancel (never ``failed``/``completed``: those are 409).

    Kept local until ``app.schemas`` exposes the generated ``Task`` (pending item in
    ``docs/handoffs/claude-c10.md``). ``cancel_requested`` has no default so that a snapshot
    without it can never be emitted (REVIEW-22 B10F-R01).
    """

    id: str
    course_id: str
    document_id: str
    stage: Literal["queued", "parsing", "extracting", "merging", "cancelled"]
    progress: float = Field(ge=0, le=1)
    cancel_requested: bool
    created_at: str
    updated_at: str


class TaskNotCancellableDetails(BaseModel):
    stage: Literal["persisting", "awaiting_review", "completed", "failed", "cancelled"]
    reason: Literal["persisting_uninterruptible", "processing_finished", "already_terminal"]


class TaskNotCancellableError(BaseModel):
    """Contract ``TaskNotCancellableError`` (src/contracts/api.v1.yaml)."""

    code: Literal["TASK_NOT_CANCELLABLE"]
    message: str
    details: TaskNotCancellableDetails


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post(
    "/{tid}/cancel",
    operation_id="cancelTask",
    summary="取消任务（教师）",
    response_model=CancelledTaskSnapshot,
    responses={
        401: {"model": Error, "description": "未认证或令牌失效（`UNAUTHENTICATED`）"},
        403: {"model": Error, "description": "是该课程成员但课程内角色不是教师（`ROLE_FORBIDDEN`）"},
        404: {"model": Error, "description": "任务不存在，或调用者不是任务所在课程成员（`NOT_FOUND`）"},
        409: {"model": TaskNotCancellableError, "description": "`TASK_NOT_CANCELLABLE`，`details: {stage, reason}`"},
    },
)
def cancel(
    tid: str,
    request: Request,
    access: CourseAccess = Depends(task_teacher),
) -> CancelledTaskSnapshot | JSONResponse:
    try:
        outcome = cancel_task(
            request.app.state.settings.SQLITE_URL, tid, course_id=access.course.id
        )
    except TaskNotFound:
        raise not_found() from None
    except TaskNotCancellable as rejected:
        body = TaskNotCancellableError(
            code="TASK_NOT_CANCELLABLE",
            message=_NOT_CANCELLABLE_MESSAGE,
            details=TaskNotCancellableDetails(**rejected.details),
        )
        return JSONResponse(status_code=409, content=body.model_dump())
    task = outcome.task
    return CancelledTaskSnapshot(
        id=task.id,
        course_id=task.course_id,
        document_id=task.document_id,
        stage=task.stage,
        progress=task.progress,
        cancel_requested=task.cancel_requested,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )
