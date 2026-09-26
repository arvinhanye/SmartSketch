"""Teacher knowledge-point writes — ``createKnowledgePoint``, ``updateKnowledgePoint`` and
``unlockKnowledgePoint`` (F08, ADR-035), ``mergeKnowledgePoints`` (F10, ADR-047) and
``deleteKnowledgePoint`` (F09, ADR-048).

Protocol translation and dependency injection only; ``app.services.graph.edit_node`` holds the
course write lock, the revision check and the lock semantics.

* course teacher members only (students 403 ``ROLE_FORBIDDEN``, non-members 403 ``COURSE_FORBIDDEN``);
* stale ``expected_revision`` → 409 ``REVISION_CONFLICT`` with the current content;
* course write lock not free within ``COURSE_LOCK_WAIT_SECONDS`` → 409 ``COURSE_BUSY``;
* a merge whose re-wired ``PREREQUISITE`` edges would close a cycle → 409 ``CYCLE_DETECTED`` with ``cycle``;
* Neo4j unreachable → 503 ``STORAGE_UNAVAILABLE``.

``KnowledgePointUpdate`` is an ``anyOf`` with ``additionalProperties: false``; the generated model
neither forbids extra keys nor explicit ``null``, so the PATCH body is checked here field by field.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dependencies import course_teacher
from app.api.graph import graph_reader
from app.repositories.graph_edit import DraftNodeStore
from app.repositories.neo4j import Neo4jRepository, RepositoryError
from app.schemas.contracts import (
    KnowledgePoint,
    KnowledgePointCreate,
    KnowledgePointStatus,
    KnowledgePointType,
    KnowledgePointUnlock,
    MergeRequest,
)
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.graph.edit_node import (
    CourseBusy,
    EditContext,
    InvalidEdit,
    RevisionConflict,
    SourceInput,
    create_node,
    unlock_node,
    update_node,
)
from app.services.graph.delete_node import delete_node
from app.services.graph.merge_nodes import merge_nodes
from app.services.graph.relations import CycleDetectedError

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["graph"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    409: {"model": Error, "description": "`REVISION_CONFLICT`、`COURSE_BUSY` 或（合并）`CYCLE_DETECTED`"},
    422: {"model": Error},
    503: {"model": Error, "description": "图数据库暂不可用（`STORAGE_UNAVAILABLE`）"},
}
_EDITABLE = ("name", "aliases", "type", "definition", "importance", "difficulty", "status")
_TYPES = frozenset(t.value for t in KnowledgePointType)
_STATUSES = frozenset(s.value for s in KnowledgePointStatus)


def node_store(request: Request) -> DraftNodeStore:
    """One store per app, created on first use so the app still builds without Neo4j."""
    store = getattr(request.app.state, "graph_node_store", None)
    if store is None:
        store = DraftNodeStore(Neo4jRepository.from_settings(request.app.state.settings))
        request.app.state.graph_node_store = store
    return store


def _context(request: Request) -> EditContext:
    settings = request.app.state.settings
    return EditContext(settings.SQLITE_URL, node_store(request), graph_reader(request),
                       lock_seconds=settings.TASK_LEASE_SECONDS, wait_seconds=settings.COURSE_LOCK_WAIT_SECONDS)


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    content: dict[str, Any] = {"code": code, "message": message}
    if details:
        content["details"] = details
    return JSONResponse(status_code=status, content=content)


def _run(request: Request, operation: Any, status: int = 200) -> Response:
    try:
        node: KnowledgePoint | dict[str, Any] | None = operation(_context(request))
    except RepositoryError:
        return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")
    except CourseBusy as busy:
        return _error(409, busy.code, "课程正在被其他操作写入，请稍后重试", busy.details())
    except RevisionConflict as conflict:
        return _error(409, conflict.code, "知识点已被他人修改，请查看最新内容后再提交", conflict.details())
    except CycleDetectedError as cycle:
        return _error(409, cycle.code, "该操作会使前置关系成环", {"cycle": list(cycle.cycle)})
    except InvalidEdit as invalid:
        raise RequestValidationError([
            {"type": f["reason"], "loc": (f["in"], *[p for p in f["field"].split(".") if p])} for f in invalid.fields
        ]) from None
    if node is None:
        return Response(status_code=status)
    if isinstance(node, dict):  # F11 review actions return a ready contract body
        return JSONResponse(status_code=status, content=node)
    return JSONResponse(status_code=status, content=node.model_dump(mode="json", exclude_none=True))


# ---------------------------------------------------------------- PATCH body


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _field_error(key: str, value: object) -> str | None:
    if key in ("name", "definition"):
        return None if isinstance(value, str) else "string_type"
    if key == "aliases":
        if not isinstance(value, list):
            return "list_type"
        return None if all(isinstance(a, str) for a in value) else "string_type"
    if key == "type":
        return None if value in _TYPES else "enum"
    if key == "status":
        return None if value in _STATUSES else "enum"
    if not _is_number(value):
        return "float_type"
    return None if 0 <= value <= 1 else "out_of_range"  # type: ignore[operator]


def _patch(body: object) -> tuple[int, dict[str, Any]]:
    if not isinstance(body, dict):
        raise RequestValidationError([{"type": "model_attributes_type", "loc": ("body",)}])
    errors: list[dict[str, Any]] = []
    revision = body.get("expected_revision")
    if "expected_revision" not in body:
        errors.append({"type": "missing", "loc": ("body", "expected_revision")})
    elif type(revision) is not int or revision < 1:
        errors.append({"type": "int_type" if type(revision) is not int else "greater_than_equal",
                       "loc": ("body", "expected_revision")})
    changes: dict[str, Any] = {}
    for key, value in body.items():
        if key == "expected_revision":
            continue
        if key not in _EDITABLE:
            errors.append({"type": "extra_forbidden", "loc": ("body", key)})
            continue
        problem = _field_error(key, value)
        if problem is not None:
            errors.append({"type": problem, "loc": ("body", key)})
            continue
        changes[key] = value
    if not errors and not changes:
        errors.append({"type": "no_changes", "loc": ("body",)})
    if errors:
        raise RequestValidationError(errors)
    return revision, changes  # type: ignore[return-value]


# ---------------------------------------------------------------- routes


@router.post("/kp", operation_id="createKnowledgePoint", response_model=KnowledgePoint, status_code=201,
             responses=_ERRORS)
def create_knowledge_point(
    request: Request,
    body: KnowledgePointCreate,
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    nulls = [k for k in ("aliases", "chapter_id", "importance", "difficulty")
             if k in body.model_fields_set and getattr(body, k) is None]
    nulls += [f"sources.{i}.{k}" for i, s in enumerate(body.sources) for k in ("evidence_start", "evidence_end")
              if k in s.model_fields_set and getattr(s, k) is None]
    if nulls:
        raise RequestValidationError([{"type": "null_forbidden", "loc": ("body", *k.split("."))} for k in nulls])
    fields = body.model_dump(exclude={"sources"}, exclude_none=True)
    sources = [SourceInput(s.chunk_id, s.evidence_start, s.evidence_end) for s in body.sources]
    return _run(request, lambda ctx: create_node(ctx, access.course.id, fields, sources), status=201)


@router.patch("/kp/{kid}", operation_id="updateKnowledgePoint", response_model=KnowledgePoint,
              responses={**_ERRORS, 404: {"model": Error}})
def update_knowledge_point(
    request: Request,
    kid: str,
    body: Any = Body(...),
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    expected, changes = _patch(body)
    return _run(request, lambda ctx: update_node(ctx, access.course.id, kid, expected, changes))


@router.post("/kp/{kid}/unlock", operation_id="unlockKnowledgePoint", response_model=KnowledgePoint,
             responses={**_ERRORS, 404: {"model": Error}})
def unlock_knowledge_point(
    request: Request,
    kid: str,
    body: KnowledgePointUnlock,
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    return _run(request, lambda ctx: unlock_node(ctx, access.course.id, kid, body.expected_revision))


@router.post("/kp/merge", operation_id="mergeKnowledgePoints", response_model=KnowledgePoint, responses=_ERRORS)
def merge_knowledge_points(
    request: Request,
    body: MergeRequest,
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    if "expected_revisions" in body.model_fields_set and body.expected_revisions is None:
        raise RequestValidationError([{"type": "null_forbidden", "loc": ("body", "expected_revisions")}])
    return _run(request, lambda ctx: merge_nodes(ctx, access.course.id, body.primary_id, body.merged_ids,
                                                 body.expected_revisions))


@router.delete("/kp/{kid}", operation_id="deleteKnowledgePoint", status_code=204, response_class=Response,
               responses={**_ERRORS, 404: {"model": Error}})
def delete_knowledge_point(
    request: Request,
    kid: str,
    expected_revision: int | None = Query(None, ge=1),
    access: CourseAccess = Depends(course_teacher),
) -> Response:
    def operation(ctx: EditContext) -> None:
        delete_node(ctx, access.course.id, kid, expected_revision)

    return _run(request, operation, status=204)
