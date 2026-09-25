"""POST /api/v1/tasks/{tid}/event-ticket — contract operation ``issueEventTicket`` (C16).

Protocol translation only: authorization is the shared ``task_teacher`` dependency (§4.1:
401 / 404 for non-members and missing tasks / 403 ``ROLE_FORBIDDEN``); persistence and the
ticket itself live in ``app.repositories.event_tickets``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.dependencies import task_teacher
from app.repositories.event_tickets import TICKET_TTL_SECONDS, issue_ticket
from app.schemas.errors import Error
from app.services.access import CourseAccess


class EventTicket(BaseModel):
    """Contract schema ``EventTicket`` (src/contracts/api.v1.yaml)."""

    ticket: str = Field(min_length=22, pattern=r"^[A-Za-z0-9_-]+$")
    expires_in: Literal[60]


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post(
    "/{tid}/event-ticket",
    operation_id="issueEventTicket",
    summary="申领任务 SSE 的一次性票据（教师）",
    response_model=EventTicket,
    responses={
        401: {"model": Error, "description": "未认证或令牌失效（`UNAUTHENTICATED`）"},
        403: {"model": Error, "description": "是该课程成员但课程内角色不是教师（`ROLE_FORBIDDEN`）"},
        404: {"model": Error, "description": "任务不存在，或调用者不是任务所在课程成员（`NOT_FOUND`）"},
    },
)
def issue_event_ticket(
    tid: str,
    request: Request,
    response: Response,
    access: CourseAccess = Depends(task_teacher),
) -> EventTicket:
    ticket = issue_ticket(
        request.app.state.settings.SQLITE_URL,
        user_id=access.user.id,
        task_id=tid,
        now=request.app.state.auth_clock(),
    )
    response.headers["Cache-Control"] = "no-store"
    return EventTicket(ticket=ticket, expires_in=TICKET_TTL_SECONDS)
