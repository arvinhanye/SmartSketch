"""FastAPI application factory and ASGI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import load_settings
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
    application.include_router(health_router)
    return application


app = create_app()
