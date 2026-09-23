"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import load_settings


APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    """Validate settings and build the API without connecting to external services."""
    settings = load_settings()
    application = FastAPI(title="SmartSketch API", version=APP_VERSION)
    application.state.settings = settings
    application.include_router(health_router)
    return application


app = create_app()
