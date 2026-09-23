"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from app.api.health import router as health_router


APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    """Build the API without connecting to external services."""
    application = FastAPI(title="SmartSketch API", version=APP_VERSION)
    application.include_router(health_router)
    return application


app = create_app()
