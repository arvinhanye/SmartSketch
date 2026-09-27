"""FastAPI adapters for the C03 access service; routes reuse these dependencies."""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from app.config import SettingsError
from app.repositories.accounts import AccountRecord
from app.services.access import (
    AccessDenied,
    AccessService,
    CourseAccess,
    role_forbidden,
    unauthenticated,
)


logger = logging.getLogger(__name__)


def access_error_response(request: Request, error: AccessDenied) -> JSONResponse:
    if request.url.path.endswith("/chat"):
        logger.info("chat request rejected status=%s code=%s course_id=%s user_id=%s",
                    error.status_code, error.code, request.path_params.get("cid"),
                    getattr(request.state, "authenticated_user_id", None))
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message},
    )


def access_service(request: Request) -> AccessService:
    try:
        return AccessService(request.app.state.settings, request.app.state.auth_clock)
    except SettingsError:
        # Factory-created apps may omit the secret; never treat this as anonymous success.
        raise unauthenticated() from None


def current_user(
    request: Request,
    service: AccessService = Depends(access_service),
) -> AccountRecord:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or token.strip() != token:
        raise unauthenticated()
    user = service.authenticate(token)
    request.state.authenticated_user_id = user.id
    return user


def teacher_account(user: AccountRecord = Depends(current_user)) -> AccountRecord:
    if user.role != "teacher":
        raise role_forbidden()
    return user


def course_reader(
    cid: str,
    user: AccountRecord = Depends(current_user),
    service: AccessService = Depends(access_service),
) -> CourseAccess:
    return service.require_course(user, cid, student_published=True)


def course_teacher(
    cid: str,
    user: AccountRecord = Depends(current_user),
    service: AccessService = Depends(access_service),
) -> CourseAccess:
    return service.require_course(user, cid, role="teacher")


def course_student(
    cid: str,
    user: AccountRecord = Depends(current_user),
    service: AccessService = Depends(access_service),
) -> CourseAccess:
    return service.require_course(user, cid, role="student", student_published=True)


def task_teacher(
    tid: str,
    user: AccountRecord = Depends(current_user),
    service: AccessService = Depends(access_service),
) -> CourseAccess:
    return service.require_task(user, tid)
