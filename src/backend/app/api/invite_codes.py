"""Invitation protocol adapters; all authorization and write rules live in services."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api.dependencies import current_user
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import Course, CourseJoinRequest, InviteCodeResponse
from app.schemas.errors import Error
from app.services.invite_codes import (
    InviteRateLimited,
    get_course_invite_code,
    join_course,
    reserve_join_attempt,
)


router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


def invite_rate_limit_response(request: Request, error: InviteRateLimited) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"code": "RATE_LIMITED", "message": "加入课程请求过于频繁，请稍后再试"},
        headers={"Retry-After": str(error.retry_after), "Cache-Control": "no-store"},
    )


def joining_user(request: Request, user: AccountRecord = Depends(current_user)) -> AccountRecord:
    # FastAPI resolves this dependency before body validation, so malformed submissions
    # consume the same guessing budget. Only ASGI's peer is used, never a supplied XFF.
    reserve_join_attempt(
        user, request.client.host if request.client else "unknown", request.app.state.invite_limiter,
    )
    return user


@router.post(
    "/join", operation_id="joinCourse", response_model=Course, status_code=201,
    response_model_exclude_none=True,
    responses={status: {"model": Error} for status in (401, 403, 404, 409, 422, 429)},
)
def join_by_code(
    body: CourseJoinRequest, request: Request, response: Response,
    user: AccountRecord = Depends(joining_user),
) -> Course:
    response.headers["Cache-Control"] = "no-store"
    return join_course(request.app.state.settings.SQLITE_URL, user.id, body.code)


@router.get(
    "/{cid}/invite-code", operation_id="getCourseInviteCode", response_model=InviteCodeResponse,
    responses={401: {"model": Error}, 403: {"model": Error}, 500: {"model": Error}},
)
def read_invite_code(
    cid: str, request: Request, response: Response, user: AccountRecord = Depends(current_user),
) -> InviteCodeResponse:
    response.headers["Cache-Control"] = "no-store"
    return get_course_invite_code(request.app.state.settings.SQLITE_URL, user.id, cid)


@router.post(
    "/{cid}/invite-code:rotate", operation_id="rotateCourseInviteCode", response_model=InviteCodeResponse,
    responses={401: {"model": Error}, 403: {"model": Error}, 500: {"model": Error}},
)
def rotate_invite_code(
    cid: str, request: Request, response: Response, user: AccountRecord = Depends(current_user),
) -> InviteCodeResponse:
    response.headers["Cache-Control"] = "no-store"
    return get_course_invite_code(request.app.state.settings.SQLITE_URL, user.id, cid, rotate=True)
