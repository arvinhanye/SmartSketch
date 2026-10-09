"""Grounded chat HTTP/JSON and SSE transport (J07)."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute

from app.api.dependencies import course_student
from app.repositories.graph_migrations import VectorSpaceError
from app.repositories.chat_logs import ChatLog, write_chat_log
from app.repositories.model_calls import SqliteCallStore
from app.repositories.neo4j import Neo4jRepository
from app.schemas.contracts import ChatRequest, ChatResponse
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.ai.factory import build_embedding_adapter, build_model_clients, model_id
from app.services.ai.policy import ModelCallPolicy, new_call_id
from app.services.credentials import CredentialUnavailable, ModelConfigRequired
from app.services.qa.chat import ChatAudit, ChatFailure, ChatService
from app.services.qa.generate import AnswerGenerator
from app.services.qa.rewrite import QueryRewriter
from app.services.qa.user_models import UserChatModels
from app.services.versions.resolver import VersionIntegrityError, resolve_published



class ChatRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def with_start(request: Request):
            request.state.chat_started = time.monotonic()
            return await handler(request)

        return with_start


router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["chat"], route_class=ChatRoute)
logger = logging.getLogger(__name__)


def chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service is not None:
        return service
    settings = request.app.state.settings
    embedding = build_embedding_adapter(settings)
    repo = Neo4jRepository.from_settings(settings)
    if settings.LLM_MODE == "personal":
        # ADR-080：没有全站模型；每个请求由 user_chat_service 换上提问者自己的改写器与生成器
        service = ChatService(settings, repo, embedding, None, None)
    else:
        primary, fallback = build_model_clients(settings)
        policy = ModelCallPolicy.from_settings(
            settings, primary=primary, fallback=fallback, store=SqliteCallStore(settings.SQLITE_URL),
        )
        model = model_id(settings, "chat")
        service = ChatService(settings, repo, embedding,
                              QueryRewriter(policy, model=model), AnswerGenerator(policy, model=model))
    request.app.state.chat_service = service
    return service


def user_chat_service(request: Request, user_id: str, course_id: str | None = None) -> ChatService:
    """当前用户可用的问答服务；personal 模式下换上本人的模型（ADR-080 决定 4）。"""
    base = chat_service(request)
    settings = request.app.state.settings
    if course_id is not None:
        import copy
        from app.services.embedding_configs import for_course
        embedding = for_course(settings, course_id)
        if embedding is not None:
            base = copy.copy(base)
            base.embedding = embedding
            # Bind a space for this request; old properties survive later config switches.
            base.current_space = lambda: embedding.space
    # 既有测试用只带 SQLITE_URL 的替身设置并替换 chat_service（test_j10）：缺属性按非 personal 处理。
    if getattr(settings, "LLM_MODE", "") != "personal":
        return base
    models = getattr(request.app.state, "user_chat_models", None)
    if models is None:
        models = UserChatModels(settings, transport=getattr(request.app.state, "model_transport", None))
        request.app.state.user_chat_models = models
    try:
        rewriter, generator = models.for_user(user_id)
    except ModelConfigRequired:
        raise ChatFailure("MODEL_CONFIG_REQUIRED") from None
    except CredentialUnavailable:
        raise ChatFailure("LLM_UNAVAILABLE", reason="auth") from None
    return base.with_models(rewriter, generator)


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _record_outcome(
    sqlite_url: str, *, request_id: str, user_id: str, course_id: str,
    version_id: str, question: str, started: float,
    terminal: dict[str, Any] | None, audit: ChatAudit | None = None,
) -> None:
    audit = audit or ChatAudit()
    latency_ms = max(0, int((time.monotonic() - started) * 1000))
    reason = error_code = error_reason = None
    citations: tuple[tuple[int, str], ...] = ()
    if terminal is None:
        outcome = "aborted"
    elif terminal["event"] == "done":
        final = terminal["final"]
        outcome = final["status"]
        reason = final.get("reason")
        latency_ms = final["latency_ms"]
        citations = tuple((item["index"], item["chunk_id"]) for item in final["citations"])
    else:
        outcome = "error"
        error = terminal["error"]
        error_code = error["code"]
        error_reason = error.get("details", {}).get("reason")
    write_chat_log(sqlite_url, ChatLog(
        request_id=request_id, user_id=user_id, course_id=course_id,
        version_id=version_id, question=question, outcome=outcome,
        latency_ms=latency_ms, reason=reason, error_code=error_code,
        error_reason=error_reason, citations=citations,
        unknown_citation_count=audit.unknown_citation_count,
        invalidation_subtype=audit.invalidation_subtype,
        uncovered_unit_count=audit.uncovered_unit_count,
        truncated=audit.truncated,
        first_delta_latency_ms=audit.first_delta_latency_ms,
    ))


async def _stream(
    request: Request, service: ChatService, prepared: Any,
    record: Callable[[dict[str, Any] | None], None],
):
    queue: Queue[dict[str, Any] | None] = Queue(maxsize=8)
    stop = Event()

    def put(item: dict[str, Any] | None) -> None:
        while not stop.is_set():
            try:
                queue.put(item, timeout=0.2)
                return
            except Full:
                continue

    def produce() -> None:
        events = service.events(prepared, stop)
        try:
            for event in events:
                if stop.is_set():
                    break
                put(event)
        finally:
            events.close()
            put(None)

    Thread(target=produce, daemon=True, name="chat-stream").start()
    terminal_event: dict[str, Any] | None = None
    try:
        while not stop.is_set():
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.to_thread(queue.get, True, 15)
            except Empty:
                yield ":ping\n\n"
                continue
            if event is None:
                terminal_event = {"event": "error", "error": ChatFailure("INTERNAL_ERROR").body(prepared.request_id)}
                break
            yield _sse(event)
            if event["event"] in ("done", "error"):
                terminal_event = event
                break
    finally:
        stop.set()
        record(terminal_event)
        if terminal_event is None:
            logger.info("chat aborted request_id=%s", prepared.request_id)


@router.post(
    "/chat", operation_id="chat", response_model=ChatResponse,
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error},
               422: {"model": Error}, 429: {"model": Error}, 500: {"model": Error},
               503: {"model": Error}},
)
def chat(
    request: Request, payload: ChatRequest, access: CourseAccess = Depends(course_student),
) -> JSONResponse | StreamingResponse:
    started = request.state.chat_started
    settings = request.app.state.settings
    try:
        version = resolve_published(settings.SQLITE_URL, access.course.id)
    except sqlite3.Error:
        logger.warning("chat publish pointer unavailable course_id=%s user_id=%s", access.course.id, access.user.id)
        failure = ChatFailure("STORAGE_UNAVAILABLE")
        return JSONResponse(status_code=failure.status_code, content=failure.body())
    except VersionIntegrityError:
        logger.error("chat publish pointer invalid course_id=%s user_id=%s", access.course.id, access.user.id)
        failure = ChatFailure("INTERNAL_ERROR")
        return JSONResponse(status_code=failure.status_code, content=failure.body())
    request_id = new_call_id()
    def record(terminal: dict[str, Any] | None, prepared: Any = None) -> None:
        _record_outcome(
            settings.SQLITE_URL, request_id=request_id, user_id=access.user.id,
            course_id=access.course.id, version_id=version.version_id,
            question=payload.question, started=started, terminal=terminal,
            audit=prepared.audit if prepared is not None else None,
        )

    def failed(failure: ChatFailure) -> JSONResponse:
        body = failure.body(request_id)
        record({"event": "error", "error": body})
        return JSONResponse(status_code=failure.status_code, content=body)

    try:
        service = user_chat_service(request, access.user.id, access.course.id)
        prepared = service.prepare(
            version=version, request_id=request_id, started=started,
            question=payload.question, history=payload.history, kp_id=payload.kp_id,
        )
    except ChatFailure as failure:
        return failed(failure)
    except (VectorSpaceError, sqlite3.Error):
        return failed(ChatFailure("STORAGE_UNAVAILABLE"))
    except Exception as error:
        logger.error("chat preparation failed request_id=%s error_type=%s",
                     request_id, type(error).__name__)
        return failed(ChatFailure("INTERNAL_ERROR"))

    if request.headers.get("accept", "").split(",")[0].strip() == "application/json":
        for event in service.events(prepared):
            if event["event"] == "done":
                record(event, prepared)
                return JSONResponse(content=event["final"])
            if event["event"] == "error":
                record(event, prepared)
                failure = event["error"]
                status = {"BUDGET_EXCEEDED": 429, "INTERNAL_ERROR": 500}.get(failure["code"], 503)
                return JSONResponse(status_code=status, content=failure)
        failure = ChatFailure("INTERNAL_ERROR")
        body = failure.body(request_id)
        record({"event": "error", "error": body}, prepared)
        return JSONResponse(status_code=500, content=body)

    return StreamingResponse(
        _stream(request, service, prepared, lambda terminal: record(terminal, prepared)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
