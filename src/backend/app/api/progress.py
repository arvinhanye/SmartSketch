"""Learning progress — contract operations ``getProgress`` and ``updateProgress`` (I02).

Protocol translation and dependency injection only:

* both routes use ``course_student``: 401 without a session, 403 for non-members and teachers, 404
  ``GRAPH_NOT_PUBLISHED`` before any projection when the course was never published;
* the student is always the authenticated account; ``ProgressUpdate`` is closed, so a body item
  carrying ``user_id`` fails schema validation (422) and nothing is written;
* a repeated ``kp_id`` in one batch is the generic 422 ``VALIDATION_ERROR``; a target outside the
  published version at commit time is 422 with ``ProgressNotInPublishedVersionDetails`` (ADR-017 决定 5);
* a committed-version integrity fault, or any other unexpected failure, is 500 ``INTERNAL_ERROR``
  whose ``details`` carry only ``request_id``; node IDs stay in the server log (ADR-017 决定 4).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import course_student
from app.schemas.contracts import ProgressResponse, ProgressUpdate
from app.schemas.errors import Error
from app.services.access import AccessDenied, CourseAccess
from app.services.learning.progress import (
    DuplicateProgressTarget,
    ProgressNotInPublishedVersion,
    ProgressView,
    get_progress,
    update_progress,
)

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["learning"])
logger = logging.getLogger(__name__)

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    404: {"model": Error},
    500: {"model": Error, "description": "已提交版完整性故障（`INTERNAL_ERROR`，`details.request_id`）"},
}


def _error(status: int, code: str, message: str, details: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, "details": details})


def _respond(action: Callable[[], ProgressView], course_id: str) -> JSONResponse:
    try:
        view = action()
        body = ProgressResponse.model_validate(view.to_dict())
        return JSONResponse(content=body.model_dump(mode="json"))
    except AccessDenied:
        raise
    except DuplicateProgressTarget as error:
        return _error(422, "VALIDATION_ERROR", "请求参数不符合要求，请检查标注的字段",
                      {"fields": [{"in": "body", "field": f"{i}.kp_id", "reason": "duplicate"}
                                  for i in error.indices]})
    except ProgressNotInPublishedVersion as error:
        return _error(422, "VALIDATION_ERROR", "部分知识点不在当前发布的课程图谱中，请刷新后重试", error.details())
    except Exception:
        request_id = uuid.uuid4().hex
        logger.exception("learning progress failed: course_id=%s request_id=%s", course_id, request_id)
        return _error(500, "INTERNAL_ERROR", "学习进度暂时无法读取，请稍后重试", {"request_id": request_id})


@router.get("/progress", operation_id="getProgress", response_model=ProgressResponse, responses=_ERRORS)
def read_progress(request: Request, access: CourseAccess = Depends(course_student)) -> JSONResponse:
    sqlite_url = request.app.state.settings.SQLITE_URL
    course_id = access.course.id
    return _respond(lambda: get_progress(sqlite_url, access.user.id, course_id), course_id)


@router.put("/progress", operation_id="updateProgress", response_model=ProgressResponse,
            responses={**_ERRORS, 422: {"model": Error}})
def write_progress(
    request: Request,
    updates: Annotated[list[ProgressUpdate], Body(min_length=1)],
    access: CourseAccess = Depends(course_student),
) -> JSONResponse:
    sqlite_url = request.app.state.settings.SQLITE_URL
    course_id = access.course.id
    items = [(update.kp_id, update.status.value) for update in updates]
    return _respond(lambda: update_progress(sqlite_url, access.user.id, course_id, items), course_id)
