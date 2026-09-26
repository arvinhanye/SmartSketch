"""Graph reads — contract operations ``getGraph`` and ``getKnowledgePoint`` (F07).

Protocol translation and dependency injection only:

* both routes use the shared ``course_reader`` dependency (401 / 403 for non-members; a
  student on an unpublished course gets 404 ``GRAPH_NOT_PUBLISHED`` before any graph read);
* ``app.services.graph.read`` decides draft vs published, visibility and source locating;
* Neo4j being unreachable is 503 ``STORAGE_UNAVAILABLE``; a knowledge point without any
  locatable source violates ``source_refs`` minItems 1 and is 500 ``INTERNAL_ERROR``.

Optional fields are omitted rather than sent as ``null``; ``graph_version`` is required
by ``GraphExchange`` and is always sent (``null`` for the draft).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import course_reader
from app.repositories.graph_read import GraphReader
from app.repositories.neo4j import Neo4jRepository, RepositoryError
from app.schemas.contracts import GraphExchange, KnowledgePointDetail, KnowledgePointType, RelationType
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.graph.read import (
    GraphFilter,
    SourceUnavailable,
    read_graph,
    read_knowledge_point,
    resolve_target,
)

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["graph"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    404: {"model": Error},
    503: {"model": Error, "description": "图数据库暂不可用（`STORAGE_UNAVAILABLE`）"},
}


def graph_reader(request: Request) -> GraphReader:
    """One repository per app, created on first use so the app still builds without Neo4j."""
    reader = getattr(request.app.state, "graph_reader", None)
    if reader is None:
        reader = GraphReader(Neo4jRepository.from_settings(request.app.state.settings))
        request.app.state.graph_reader = reader
    return reader


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


def _unavailable() -> JSONResponse:
    return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")


@router.get("/graph", operation_id="getGraph", response_model=GraphExchange, responses=_ERRORS)
def get_graph(
    request: Request,
    chapter_id: str | None = Query(default=None),
    type: KnowledgePointType | None = Query(default=None),
    relation_types: list[RelationType] | None = Query(default=None),
    version: int | None = Query(default=None, ge=1),
    access: CourseAccess = Depends(course_reader),
) -> JSONResponse:
    sqlite_url = request.app.state.settings.SQLITE_URL
    target = resolve_target(sqlite_url, access, version)
    graph_filter = GraphFilter(
        chapter_id=chapter_id,
        type=None if type is None else type.value,
        relation_types=None if not relation_types else tuple(t.value for t in relation_types),
    )
    try:
        graph = read_graph(graph_reader(request), sqlite_url, target, graph_filter)
    except RepositoryError:
        return _unavailable()
    body = graph.model_dump(mode="json", exclude_none=True)
    body["graph_version"] = graph.graph_version
    return JSONResponse(content=body)


@router.get("/kp/{kid}", operation_id="getKnowledgePoint", response_model=KnowledgePointDetail,
            responses={**_ERRORS, 500: {"model": Error}})
def get_knowledge_point(
    request: Request,
    kid: str,
    access: CourseAccess = Depends(course_reader),
) -> JSONResponse:
    sqlite_url = request.app.state.settings.SQLITE_URL
    target = resolve_target(sqlite_url, access, None)
    try:
        detail = read_knowledge_point(graph_reader(request), sqlite_url, target, kid)
    except RepositoryError:
        return _unavailable()
    except SourceUnavailable:
        return _error(500, "INTERNAL_ERROR", "知识点来源暂时无法定位")
    return JSONResponse(content=detail.model_dump(mode="json", exclude_none=True))
