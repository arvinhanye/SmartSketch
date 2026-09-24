"""FastAPI application factory and ASGI entry point."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.config import check_auth_settings, load_settings
from app.services.auth import LoginRateLimiter
from app.services.startup import validate_embedding_space, validate_schema_current


APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Check persistent runtime invariants before serving requests."""
    validate_schema_current(application.state.settings)
    validate_embedding_space(application.state.settings)
    yield


def create_app() -> FastAPI:
    """Validate settings and build the API without connecting to external services."""
    settings = load_settings()
    application = FastAPI(title="SmartSketch API", version=APP_VERSION, lifespan=lifespan)
    application.state.settings = settings
    application.state.login_limiter = LoginRateLimiter()
    application.state.auth_clock = time.time
    application.include_router(health_router)
    application.include_router(auth_router)
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
