"""Teacher review queue — ``getReviewQueue`` and ``resolveReviewItem`` (F11, ADR-060).

Protocol translation and dependency injection only; ``app.services.graph.review`` classifies the
draft, paginates with keyset cursors and applies the one-click actions.

* course teacher members only (students 403 ``ROLE_FORBIDDEN``, non-members 403 ``COURSE_FORBIDDEN``);
* the item is no longer in the queue → 404 ``NOT_FOUND``; repeating an action that already took effect → 200
  with ``changed = false``;
* course write lock not free within ``COURSE_LOCK_WAIT_SECONDS`` → 409 ``COURSE_BUSY``; merges also report
  ``REVISION_CONFLICT`` / ``CYCLE_DETECTED`` exactly like ``mergeKnowledgePoints``;
* Neo4j unreachable → 503 ``STORAGE_UNAVAILABLE``.

``ReviewAction`` is a discriminated ``oneOf`` with ``additionalProperties: false``; the body is checked here
field by field so every problem is reported as a ``VALIDATION_ERROR`` field, as in ``app.api.graph_nodes``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dependencies import course_teacher
from app.api.graph_nodes import _context, _run
from app.schemas.contracts import ReviewActionResult, ReviewItemKind, ReviewQueue
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.graph.edit_node import EditContext
from app.services.graph.review import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    InvalidCursor,
    read_queue,
    resolve_duplicate,
    resolve_isolated,
    resolve_relation,
)
from app.repositories.neo4j import RepositoryError

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["review"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    404: {"model": Error},
    409: {"model": Error, "description": "`COURSE_BUSY`；合并另有 `REVISION_CONFLICT`、`CYCLE_DETECTED`"},
    422: {"model": Error},
    503: {"model": Error, "description": "图数据库暂不可用（`STORAGE_UNAVAILABLE`）"},
}
_ACTIONS = {
    "low_confidence_relation": ("rel_id", ("approve", "reject")),
    "suspected_duplicate": ("kp_ids", ("merge", "reject")),
    "isolated_node": ("kp_id", ("approve", "reject")),
}


@router.get("/review", operation_id="getReviewQueue", response_model=ReviewQueue,
            responses={k: v for k, v in _ERRORS.items() if k in (401, 403, 422, 503)})
def get_review_queue(
    request: Request,
    kind: ReviewItemKind | None = Query(None),
    cursor: str | None = Query(None, min_length=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    try:
        body = read_queue(_context(request), access.course.id, kind=None if kind is None else kind.value,
                          cursor=cursor, limit=limit)
    except InvalidCursor as invalid:
        raise RequestValidationError([{"type": invalid.reason, "loc": ("query", "cursor")}]) from None
    except RepositoryError:
        return JSONResponse(status_code=503, content={"code": "STORAGE_UNAVAILABLE",
                                                      "message": "图数据库暂不可用，请稍后重试"})
    return JSONResponse(content=body)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _action(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise RequestValidationError([{"type": "model_attributes_type", "loc": ("body",)}])
    item = body.get("item")
    if item not in _ACTIONS:
        raise RequestValidationError([{"type": "missing" if "item" not in body else "union_tag_invalid",
                                       "loc": ("body", "item")}])
    target, actions = _ACTIONS[item]
    allowed = {"item", "action", target} | ({"primary_id"} if item == "suspected_duplicate" else set())
    errors: list[dict[str, Any]] = [{"type": "extra_forbidden", "loc": ("body", k)} for k in body if k not in allowed]
    for key in ("action", target):
        if key not in body:
            errors.append({"type": "missing", "loc": ("body", key)})
    if "action" in body and body["action"] not in actions:
        errors.append({"type": "enum", "loc": ("body", "action")})
    value = body.get(target)
    if target == "kp_ids" and target in body:
        if not isinstance(value, list) or len(value) != 2:
            errors.append({"type": "list_type" if not isinstance(value, list) else "too_short" if len(value) < 2
                           else "too_long", "loc": ("body", target)})
        else:
            errors += [{"type": "string_type", "loc": ("body", target, i)} for i, v in enumerate(value) if not _text(v)]
            if all(_text(v) for v in value) and value[0] == value[1]:
                errors.append({"type": "unique_items", "loc": ("body", target)})
    elif target in body and not _text(value):
        errors.append({"type": "string_type", "loc": ("body", target)})
    if "primary_id" in body and not _text(body["primary_id"]):
        errors.append({"type": "string_type", "loc": ("body", "primary_id")})
    if errors:
        raise RequestValidationError(errors)
    return body


@router.post("/review/actions", operation_id="resolveReviewItem", response_model=ReviewActionResult,
             responses=_ERRORS)
def resolve_review_item(
    request: Request,
    body: Any = Body(...),
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    action = _action(body)
    course_id, user_id, verb = access.course.id, access.user.id, action["action"]

    def operation(ctx: EditContext) -> dict[str, Any]:
        if action["item"] == "low_confidence_relation":
            return resolve_relation(ctx, course_id, action["rel_id"], verb).body()
        if action["item"] == "isolated_node":
            return resolve_isolated(ctx, course_id, action["kp_id"], verb, user_id).body()
        return resolve_duplicate(ctx, course_id, action["kp_ids"], verb, action.get("primary_id"), user_id).body()

    return _run(request, operation)
