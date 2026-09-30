"""ASGI entry point for the portable Windows distribution."""

import os

from app.main import create_served_app
from app.services.portable_static import SpaStaticFiles


def create_portable_app():
    web_dist = os.environ.get("SMARTSKETCH_WEB_DIST")
    if not web_dist:
        raise RuntimeError("SMARTSKETCH_WEB_DIST is required for portable mode")
    application = create_served_app()
    application.mount("/", SpaStaticFiles(directory=web_dist), name="web")
    return application


app = create_portable_app()
