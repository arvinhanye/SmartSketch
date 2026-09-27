"""Teacher relation edits — ``createRelation``, ``updateRelation`` and ``deleteRelation`` (F06, ADR-071).

Contract: ``/api/v1/courses/{cid}/relations`` (POST 201) and ``/api/v1/courses/{cid}/relations/{rid}``
(PATCH 200, DELETE 204). Protocol translation and dependency injection only; the course write lock,
the F06 service-layer write (guard lock, endpoint validation, cycle detection, relation identity) and
the response assembly live in ``app.services.graph.edit_relation``.

* course teacher members only (students 403 ``ROLE_FORBIDDEN``, non-members 403 ``COURSE_FORBIDDEN``);
* a relation that is not visible in this course draft → 404 ``NOT_FOUND``;
* course write lock not free within ``COURSE_LOCK_WAIT_SECONDS`` → 409 ``COURSE_BUSY``;
* a ``PREREQUISITE`` that would close a cycle (including a revival of a ``rejected`` edge) → 409
  ``CYCLE_DETECTED`` with ``details.cycle`` (specs/course-knowledge-graph.md acceptance 4);
* a duplicate relation (same course, type and direction) → 409 ``DUPLICATE_RELATION`` with
  ``details.existing_id``; an endpoint that is absent from the course draft → 422 ``DANGLING_ENDPOINT``
  with ``details.missing`` (``src/contracts/errors.v1.md`` gives both codes that status);
* Neo4j unreachable → 503 ``STORAGE_UNAVAILABLE``. The contract does not declare 503 for these two
  operations; the route follows the existing convention of every other graph route (F11 review D-4
  recorded the same gap). ``src/contracts/`` is not touched.

``RelationUpdate`` is a closed editable set in the contract (``minProperties: 1`` with exactly four
fields, no ``additionalProperties``); the generated model neither forbids extra keys nor explicit
``null``, so the PATCH body is checked here field by field, as ``app.api.graph_nodes`` does for
``KnowledgePointUpdate``. A key the route cannot honour (``course_id``, ``id``, ``revision``, …) is
rejected instead of silently dropped.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dependencies import course_teacher
from app.api.graph import graph_reader
from app.repositories.graph_relation_edit import DraftRelationStore
from app.repositories.neo4j import Neo4jRepository, RepositoryError
from app.schemas.contracts import Relation, RelationCreate, RelationType, KnowledgePointStatus
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.graph import edit_relation
from app.services.graph.edit_node import CourseBusy, EditContext, InvalidEdit
from app.services.graph.relations import (
    CycleDetectedError,
    DanglingEndpointError,
    DuplicateRelationError,
    InvalidRelationError,
)

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["graph"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    404: {"model": Error},
    409: {"model": Error, "description": "`CYCLE_DETECTED`、`DUPLICATE_RELATION` 或 `COURSE_BUSY`"},
    422: {"model": Error, "description": "`VALIDATION_ERROR` 或 `DANGLING_ENDPOINT`"},
    503: {"model": Error, "description": "图数据库暂不可用（`STORAGE_UNAVAILABLE`）"},
}
_EDITABLE: Final = edit_relation.EDITABLE
_TYPES: Final = frozenset(t.value for t in RelationType)
_STATUSES: Final = frozenset(s.value for s in KnowledgePointStatus)


def relation_store(request: Request) -> DraftRelationStore:
    """One store per app, created on first use so the app still builds without Neo4j."""
    store = getattr(request.app.state, "relation_store", None)
    if store is None:
        store = DraftRelationStore(Neo4jRepository.from_settings(request.app.state.settings))
        request.app.state.relation_store = store
    return store


def _context(request: Request, access: CourseAccess) -> EditContext:
    settings = request.app.state.settings
    return EditContext(settings.SQLITE_URL, relation_store(request), graph_reader(request),
                       lock_seconds=settings.TASK_LEASE_SECONDS, wait_seconds=settings.COURSE_LOCK_WAIT_SECONDS,
                       actor_id=access.user.id)


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    content: dict[str, Any] = {"code": code, "message": message}
    if details:
        content["details"] = details
    return JSONResponse(status_code=status, content=content)


def _run(request: Request, access: CourseAccess, operation: Any, status: int = 200) -> Response:
    try:
        body = operation(_context(request, access))
    except RepositoryError:
        return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")
    except CourseBusy as busy:
        return _error(409, busy.code, "课程正在被其他操作写入，请稍后重试", busy.details())
    except DuplicateRelationError as duplicate:
        return _error(409, duplicate.code, "同类型、同方向的关系已存在", {"existing_id": duplicate.existing_id})
    except CycleDetectedError as cycle:
        return _error(409, cycle.code, "该操作会使前置关系成环", {"cycle": list(cycle.cycle)})
    except DanglingEndpointError as dangling:
        return _error(422, dangling.code, "关系端点不存在或不属于本课程", {"missing": list(dangling.missing)})
    except InvalidEdit as invalid:
        raise RequestValidationError([
            {"type": f["reason"], "loc": (f["in"], *[p for p in f["field"].split(".") if p])} for f in invalid.fields
        ]) from None
    except InvalidRelationError:
        # 组合出的关系不满足 F06 的写入约束。路由只可能触发非 PREREQUISITE 的自环（服务层已先行 422），
        # 其余分支（类型、空 ID、confidence、source）都在路由或服务层被挡下；这里只是兜底，不得 500。
        return _error(422, "VALIDATION_ERROR", "关系参数不符合要求，请检查标注的字段",
                      {"fields": [{"in": "body", "field": "to_id", "reason": "invalid_relation"}]})
    if body is None:
        return Response(status_code=status)
    if isinstance(body, dict):
        return JSONResponse(status_code=status, content=body)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json", exclude_none=True))


# ---------------------------------------------------------------- PATCH body


def _field_error(key: str, value: object) -> str | None:
    if key == "type":
        return None if value in _TYPES else "enum" if isinstance(value, str) else "string_type"
    if key == "status":
        return None if value in _STATUSES else "enum" if isinstance(value, str) else "string_type"
    if not isinstance(value, str):
        return "string_type"
    return None if value else "string_too_short"


def _patch(body: object) -> dict[str, Any]:
    """``RelationUpdate``：只允许四个可编辑字段，`null` 与未知键都拒绝（见模块说明）。"""
    if not isinstance(body, dict):
        raise RequestValidationError([{"type": "model_attributes_type", "loc": ("body",)}])
    errors: list[dict[str, Any]] = []
    changes: dict[str, Any] = {}
    for key, value in body.items():
        if key not in _EDITABLE:
            errors.append({"type": "extra_forbidden", "loc": ("body", key)})
            continue
        if value is None:
            errors.append({"type": "null_forbidden", "loc": ("body", key)})
            continue
        problem = _field_error(key, value)
        if problem is not None:
            errors.append({"type": problem, "loc": ("body", key)})
            continue
        changes[key] = value
    if not body:
        errors.append({"type": "too_short", "loc": ("body",)})
    if errors:
        raise RequestValidationError(errors)
    return changes


# ---------------------------------------------------------------- routes


@router.post("/relations", operation_id="createRelation", response_model=Relation, status_code=201,
             responses={k: v for k, v in _ERRORS.items() if k != 404})
def create_relation(
    request: Request,
    body: RelationCreate,
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    def operation(ctx: EditContext) -> dict[str, Any]:
        return edit_relation.create_relation(ctx, access.course.id, type=body.type.value,
                                             from_id=body.from_id, to_id=body.to_id)

    return _run(request, access, operation, status=201)


@router.patch("/relations/{rid}", operation_id="updateRelation", response_model=Relation, responses=_ERRORS)
def update_relation(
    request: Request,
    rid: str,
    body: Any = Body(...),
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    changes = _patch(body)
    return _run(request, access,
                lambda ctx: edit_relation.update_relation(ctx, access.course.id, rid, changes))


@router.delete("/relations/{rid}", operation_id="deleteRelation", status_code=204, response_class=Response,
               responses=_ERRORS)
def delete_relation(
    request: Request,
    rid: str,
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    return _run(request, access, lambda ctx: edit_relation.delete_relation(ctx, access.course.id, rid),
                status=204)
