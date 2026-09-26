"""Publish, rollback and version list — contract operations ``publishGraph``, ``rollbackVersion`` and
``listVersions`` (G04/G06; specs/teacher-review-publish.md V5, V6).

Protocol translation and dependency injection only. All three routes require a teacher of the
course (``course_teacher``: 401 / 403). The services decide everything else:

* ``PUBLISH_BLOCKED`` (409) carries ``details.reasons``; ``PUBLISH_IN_PROGRESS`` (409) and
  ``COURSE_BUSY`` (409, ``details.holder``) use the generic conflict body;
* a rollback target that is missing, failed or belongs to another course is 404 ``NOT_FOUND``;
* Neo4j or SQLite being unreachable is 503 ``STORAGE_UNAVAILABLE``; any other failure after the
  attempt started is 500 ``INTERNAL_ERROR`` (the old pointer is kept, the teacher may retry).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import course_teacher
from app.repositories import versions
from app.repositories.graph_migrations import sqlite_current_space
from app.repositories.neo4j import Neo4jRepository, RepositoryConnectionError, RepositoryError
from app.repositories.versions import PublishInProgress, VersionNotFound
from app.schemas.contracts import GraphVersion, PublishResult
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.ai.compatible import CompatibleEmbeddingClient
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient
from app.services.versions.publish import CourseBusy, PublishContext, PublishFailed, PublishOutcome, publish
from app.services.versions.rollback import rollback
from app.services.versions.snapshot import SnapshotBlocked

router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["review"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": Error},
    403: {"model": Error},
    409: {"model": Error},
    500: {"model": Error},
    503: {"model": Error, "description": "图数据库或数据库暂不可用（`STORAGE_UNAVAILABLE`）"},
}


def publish_context(request: Request) -> PublishContext:
    """One context per app, built on first use so the app still starts without Neo4j."""
    ctx = getattr(request.app.state, "publish_context", None)
    if ctx is None:
        settings = request.app.state.settings
        client = (FakeEmbeddingClient() if settings.EMBEDDING_MODE == "fake"
                  else CompatibleEmbeddingClient.from_settings(settings))
        ctx = PublishContext(
            settings.SQLITE_URL,
            Neo4jRepository.from_settings(settings),
            EmbeddingAdapter(settings, client),
            sqlite_current_space(settings.SQLITE_URL),
            lease_seconds=settings.PUBLISH_LEASE_SECONDS,
            lock_wait_seconds=settings.COURSE_LOCK_WAIT_SECONDS,
        )
        request.app.state.publish_context = ctx
    return ctx


def _error(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


def _result(outcome: PublishOutcome) -> JSONResponse:
    result = PublishResult.model_validate({
        "version": outcome.version,
        "published_at": outcome.published_at,
        "unchanged": outcome.unchanged,
        "excluded": dict(outcome.excluded),
        "stats": {"node_count": outcome.node_count, "edge_count": outcome.edge_count},
    })
    return JSONResponse(content=result.model_dump(mode="json", exclude_none=True))


def _storage_failure(error: BaseException) -> bool:
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, (RepositoryError, RepositoryConnectionError)):
            return True
        cause = cause.__cause__
    return False


def _run(action: Any) -> JSONResponse:
    try:
        return _result(action())
    except PublishInProgress:
        return _error(409, "PUBLISH_IN_PROGRESS", "本课程已有发布或回滚在进行，请稍后重试")
    except CourseBusy as error:
        return _error(409, "COURSE_BUSY", "课程正在写入，请稍后重试", error.details())
    except SnapshotBlocked as error:
        return _error(409, "PUBLISH_BLOCKED", "图谱未通过发布校验", error.details())
    except VersionNotFound:
        return _error(404, "NOT_FOUND", "版本不存在")
    except RepositoryError:
        return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")
    except PublishFailed as error:
        if _storage_failure(error):
            return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")
        return _error(500, "INTERNAL_ERROR", "发布未完成，当前版本保持不变，请重试")


@router.post("/publish", operation_id="publishGraph", response_model=PublishResult, responses=_ERRORS)
def publish_graph(request: Request, access: CourseAccess = Depends(course_teacher)) -> JSONResponse:
    try:
        ctx = publish_context(request)
    except RepositoryError:
        return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")
    return _run(lambda: publish(ctx, access.course.id, created_by=access.user.id))


@router.post("/versions/{version}/rollback", operation_id="rollbackVersion", response_model=PublishResult,
             responses={**_ERRORS, 404: {"model": Error}})
def rollback_version(
    request: Request,
    version: int = Path(ge=1),
    access: CourseAccess = Depends(course_teacher),
) -> JSONResponse:
    if versions.get_committed(request.app.state.settings.SQLITE_URL, access.course.id, version) is None:
        return _error(404, "NOT_FOUND", "版本不存在")  # R2 在连 Neo4j 之前：他课或失败版本同样 404
    try:
        ctx = publish_context(request)
    except RepositoryError:
        return _error(503, "STORAGE_UNAVAILABLE", "图数据库暂不可用，请稍后重试")
    return _run(lambda: rollback(ctx, access.course.id, version, created_by=access.user.id))


@router.get("/versions", operation_id="listVersions", response_model=list[GraphVersion],
            responses={401: {"model": Error}, 403: {"model": Error}})
def list_graph_versions(request: Request, access: CourseAccess = Depends(course_teacher)) -> JSONResponse:
    rows = versions.list_versions(request.app.state.settings.SQLITE_URL, access.course.id)
    items = []
    for row in rows:
        item: dict[str, Any] = {"version": row.version, "published_at": row.committed_at, "kind": row.kind,
                                "node_count": row.node_count, "edge_count": row.edge_count}
        if row.kind == "rollback":
            item["source_version"] = row.source_version
        items.append(GraphVersion.model_validate(item).model_dump(mode="json", exclude_none=True))
    return JSONResponse(content=items)
