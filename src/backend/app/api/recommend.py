"""Next-step recommendation — contract operation ``getRecommendations`` (I05).

Protocol translation and dependency injection only:

* ``course_student``: 401 without a session, 403 for non-members and teachers, 404
  ``GRAPH_NOT_PUBLISHED`` when the course was never published — distinct from the 200
  ``state = all_mastered`` empty state;
* ``limit`` is an integer 1..50 (default 10); anything else is the generic 422 ``VALIDATION_ERROR``;
* weights come from the ``RECOMMEND_WEIGHT_*`` settings validated at startup, never from the request;
* a committed-version integrity fault (empty graph, cycle, dangling edge, broken chapter tree, invalid
  number, broken snapshot or lineage) or any other unexpected failure is 500 ``INTERNAL_ERROR`` whose
  ``details`` carry only ``request_id``; node IDs and cycle paths stay in the server log (ADR-017 决定 4).
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import course_student
from app.schemas.contracts import RecommendResponse
from app.schemas.errors import Error
from app.services.access import AccessDenied, CourseAccess
from app.services.learning.ranking import RecommendWeights
from app.services.learning.recommend import DEFAULT_LIMIT, MAX_LIMIT, get_recommendations

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["learning"])
logger = logging.getLogger(__name__)

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    404: {"model": Error},
    422: {"model": Error},
    500: {"model": Error, "description": "已提交版完整性故障（`INTERNAL_ERROR`，`details.request_id`）"},
}


@router.get("/recommend", operation_id="getRecommendations", response_model=RecommendResponse,
            responses=_ERRORS)
def read_recommendations(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    access: CourseAccess = Depends(course_student),
) -> JSONResponse:
    settings = request.app.state.settings
    course_id = access.course.id
    try:
        weights = RecommendWeights.from_sequence(settings.recommend_weights)
        result = get_recommendations(settings.SQLITE_URL, access.user.id, course_id, weights, limit)
        body = RecommendResponse.model_validate(result.to_dict())
        return JSONResponse(content=body.model_dump(mode="json"))
    except AccessDenied:
        raise
    except Exception:
        request_id = uuid.uuid4().hex
        logger.exception("recommendation failed: course_id=%s request_id=%s", course_id, request_id)
        return JSONResponse(status_code=500, content={
            "code": "INTERNAL_ERROR", "message": "学习推荐暂时无法生成，请稍后重试",
            "details": {"request_id": request_id},
        })
