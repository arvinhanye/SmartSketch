"""FastAPI application factory and ASGI entry point."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.dependencies import access_error_response
from app.api.event_tickets import router as event_tickets_router
from app.api.graph import router as graph_router
from app.api.graph_nodes import router as graph_nodes_router
from app.api.versions import router as versions_router
from app.api.progress import router as progress_router
from app.api.health import router as health_router
from app.api.task_cancel import router as task_cancel_router
from app.api.tasks import router as tasks_router
from app.api.materials import policy_router as upload_policy_router
from app.api.materials import router as materials_router
from app.api.members import router as members_router
from app.config import check_auth_settings, load_settings
from app.schemas.errors import Error
from app.services.auth import LoginRateLimiter, prepare_timing_dummy_hash
from app.services.access import AccessDenied
from app.services.startup import validate_embedding_space, validate_schema_current


APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Check persistent runtime invariants before serving requests."""
    validate_schema_current(application.state.settings)
    validate_embedding_space(application.state.settings)
    yield


_REQUEST_SOURCES = frozenset({"body", "query", "path", "header", "cookie"})
_VALIDATION_MESSAGE = "请求参数不符合要求，请检查标注的字段"


def _field_reason(error: dict) -> dict[str, str]:
    """One ``details.fields`` entry: where, which field, and the error type — never the input.

    ``in`` is the request part (body, query, path, header, cookie); ``field`` is the dotted
    path inside it, empty when the problem is the part as a whole (missing or unparsable
    body); ``reason`` is the machine-readable Pydantic error type such as ``missing``.
    """
    location = [str(part) for part in error.get("loc", ())]
    source = location[0] if location and location[0] in _REQUEST_SOURCES else ""
    path = location[1:] if source else location
    if error.get("type") == "json_invalid":
        path = []  # the location is a character offset, not a field
    return {"in": source, "field": ".".join(path), "reason": str(error.get("type", ""))}


async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Answer every request-validation failure with the contract ``Error`` (VALIDATION_ERROR).

    FastAPI's default body echoes the submitted ``input`` — including passwords — so only
    locations and error types are returned.
    """
    body = Error(
        code="VALIDATION_ERROR",
        message=_VALIDATION_MESSAGE,
        details={"fields": [_field_reason(error) for error in exc.errors()]},
    )
    return JSONResponse(status_code=422, content=body.model_dump())


def create_app() -> FastAPI:
    """Validate settings and build the API without connecting to external services."""
    settings = load_settings()
    application = FastAPI(title="SmartSketch API", version=APP_VERSION, lifespan=lifespan)
    application.state.settings = settings
    application.state.login_limiter = LoginRateLimiter()
    application.state.auth_clock = time.time
    prepare_timing_dummy_hash()  # never let the first unknown-user login take twice as long
    application.add_exception_handler(RequestValidationError, _validation_error_handler)
    application.add_exception_handler(AccessDenied, access_error_response)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(event_tickets_router)
    application.include_router(task_cancel_router)
    application.include_router(tasks_router)
    application.include_router(courses_router)
    application.include_router(materials_router)
    application.include_router(upload_policy_router)
    application.include_router(members_router)
    application.include_router(graph_router)
    application.include_router(graph_nodes_router)
    application.include_router(versions_router)
    application.include_router(progress_router)
    return application


def create_served_app() -> FastAPI:
    """Build the served ASGI app; serving additionally requires AUTH_JWT_SECRET (IAM-23).

    ``create_app`` stays buildable without secrets (B05); every served entry point —
    ``python -m app`` and ``uvicorn app.main:app`` — imports ``app`` below and therefore
    refuses to start when the signing secret is missing or shorter than 32 bytes.
    """
    application = create_app()
    check_auth_settings(application.state.settings)
    return application


app = create_served_app()
