"""Task snapshot and task SSE — contract operations ``getTask`` and ``streamTaskEvents`` (C11).

Protocol translation and dependency injection only:

* ``GET /api/v1/tasks/{tid}``: the shared ``task_teacher`` dependency (§4.1: 401 / 404 for
  non-members and missing tasks alike / 403 ``ROLE_FORBIDDEN``), then the ``Task`` snapshot.
  ``failed`` is a domain state and still HTTP 200.
* ``GET /api/v1/tasks/{tid}/events``: authenticated only by the one-time ``ticket`` query
  parameter (``specs/identity-access.md`` §5.2; the ``Authorization`` header is never read);
  every check runs before the stream opens. Polling, diffing and frame encoding live in
  ``app.services.task_events``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.types import Receive, Scope, Send

from app.api.dependencies import access_service, task_teacher
from app.schemas.errors import Error
from app.services.access import AccessService, CourseAccess, not_found
from app.services.task_events import TaskEventStreams, authorize_ticket, load_task, task_body

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class TaskErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class TaskSnapshotBody(BaseModel):
    """Contract ``Task`` (all four ``stage`` branches).

    Kept local like C10's ``CancelledTaskSnapshot`` until ``app.schemas`` exposes the generated
    ``Task``. ``cancel_requested`` has no default so it is always emitted (REVIEW-22 B10F-R01).
    """

    id: str
    course_id: str
    document_id: str
    stage: Literal[
        "queued", "parsing", "extracting", "merging", "persisting", "awaiting_review",
        "completed", "failed", "cancelled",
    ]
    progress: int | float = Field(ge=0, le=1)
    cancel_requested: bool
    created_at: str
    updated_at: str
    error: TaskErrorBody | None = None


class _EventStreamResponse(StreamingResponse):
    """Always close the event generator, however the client left.

    Starlette cancels the stream when it sees ``http.disconnect``; with ASGI spec ≥ 2.4 it only
    notices a failed send and leaves the generator suspended. ``aclose()`` runs its ``finally``
    in both cases, releasing the poller and the subscription.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()  # type: ignore[attr-defined]


def task_event_streams(request: Request) -> TaskEventStreams:
    """Per-application stream settings and subscriber registry (tests inject short intervals)."""
    streams = getattr(request.app.state, "task_event_streams", None)
    if streams is None:
        streams = TaskEventStreams()
        request.app.state.task_event_streams = streams
    return streams


def ticket_task_teacher(
    tid: str,
    request: Request,
    ticket: str | None = Query(default=None),
    service: AccessService = Depends(access_service),
) -> CourseAccess:
    return authorize_ticket(
        request.app.state.settings.SQLITE_URL,
        service,
        ticket=ticket,
        task_id=tid,
        now=request.app.state.auth_clock(),
    )


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

_DENIALS = {
    401: {"model": Error, "description": "未认证或凭据无效（`UNAUTHENTICATED`）"},
    403: {"model": Error, "description": "是该课程成员但课程内角色不是教师（`ROLE_FORBIDDEN`）"},
    404: {"model": Error, "description": "任务不存在，或调用者不是任务所在课程成员（`NOT_FOUND`）"},
}


@router.get(
    "/{tid}",
    operation_id="getTask",
    summary="任务状态快照",
    response_model=TaskSnapshotBody,
    response_model_exclude_none=True,
    responses=_DENIALS,
)
def get_task(
    tid: str,
    request: Request,
    access: CourseAccess = Depends(task_teacher),
) -> TaskSnapshotBody:
    snapshot = load_task(request.app.state.settings.SQLITE_URL, tid, course_id=access.course.id)
    if snapshot is None:
        raise not_found()
    return TaskSnapshotBody.model_validate(task_body(snapshot))


@router.get(
    "/{tid}/events",
    operation_id="streamTaskEvents",
    summary="订阅任务进度（SSE）",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "事件流"}, **_DENIALS},
)
def stream_task_events(
    tid: str,
    request: Request,
    access: CourseAccess = Depends(ticket_task_teacher),
    streams: TaskEventStreams = Depends(task_event_streams),
) -> StreamingResponse:
    sqlite_url = request.app.state.settings.SQLITE_URL
    course_id = access.course.id
    return _EventStreamResponse(
        streams.stream(lambda: load_task(sqlite_url, tid, course_id=course_id), tid),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
