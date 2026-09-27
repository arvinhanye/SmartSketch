"""Grounded chat HTTP/JSON and SSE transport (J07)."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute

from app.api.dependencies import course_student
from app.repositories.graph_migrations import VectorSpaceError
from app.repositories.model_calls import SqliteCallStore
from app.repositories.neo4j import Neo4jRepository
from app.schemas.contracts import ChatRequest, ChatResponse
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.ai.compatible import CompatibleEmbeddingClient, CompatibleModelClient
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient, FakeModelClient
from app.services.ai.policy import ModelCallPolicy, new_call_id
from app.services.qa.chat import ChatFailure, ChatService
from app.services.qa.generate import AnswerGenerator
from app.services.qa.rewrite import QueryRewriter
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
    if settings.LLM_MODE == "live":
        primary = CompatibleModelClient.from_settings(settings, role="primary")
        fallback = (CompatibleModelClient.from_settings(settings, role="fallback")
                    if settings.LLM_FALLBACK_BASE_URL.strip() else None)
    else:
        primary, fallback = FakeModelClient(), None
    policy = ModelCallPolicy.from_settings(
        settings, primary=primary, fallback=fallback, store=SqliteCallStore(settings.SQLITE_URL),
    )
    embedding_client = (FakeEmbeddingClient() if settings.EMBEDDING_MODE == "fake"
                        else CompatibleEmbeddingClient.from_settings(settings))
    embedding = EmbeddingAdapter(settings, embedding_client)
    model = settings.LLM_CHAT_MODEL.strip() or "fake"
    service = ChatService(settings, Neo4jRepository.from_settings(settings), embedding,
                          QueryRewriter(policy, model=model), AnswerGenerator(policy, model=model))
    request.app.state.chat_service = service
    return service


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _stream(request: Request, service: ChatService, prepared: Any):
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
    terminal = False
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
                break
            yield _sse(event)
            if event["event"] in ("done", "error"):
                terminal = True
                break
    finally:
        stop.set()
        if not terminal:
            logger.info("chat aborted request_id=%s", prepared.request_id)


@router.post(
    "/chat", operation_id="chat", response_model=ChatResponse,
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error},
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
    try:
        service = chat_service(request)
        prepared = service.prepare(
            version=version, request_id=request_id, started=started,
            question=payload.question, history=payload.history, kp_id=payload.kp_id,
        )
    except ChatFailure as failure:
        return JSONResponse(status_code=failure.status_code, content=failure.body(request_id))
    except (VectorSpaceError, sqlite3.Error):
        failure = ChatFailure("STORAGE_UNAVAILABLE")
        return JSONResponse(status_code=failure.status_code, content=failure.body(request_id))
    except Exception as error:
        logger.error("chat preparation failed request_id=%s error_type=%s",
                     request_id, type(error).__name__)
        failure = ChatFailure("INTERNAL_ERROR")
        return JSONResponse(status_code=failure.status_code, content=failure.body(request_id))

    if request.headers.get("accept", "").split(",")[0].strip() == "application/json":
        for event in service.events(prepared):
            if event["event"] == "done":
                return JSONResponse(content=event["final"])
            if event["event"] == "error":
                failure = event["error"]
                status = {"BUDGET_EXCEEDED": 429, "INTERNAL_ERROR": 500}.get(failure["code"], 503)
                return JSONResponse(status_code=status, content=failure)
        failure = ChatFailure("INTERNAL_ERROR")
        return JSONResponse(status_code=500, content=failure.body(request_id))

    return StreamingResponse(
        _stream(request, service, prepared), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
