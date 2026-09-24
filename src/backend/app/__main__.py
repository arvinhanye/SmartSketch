"""Start the API with its validated environment listener settings."""

import uvicorn

from app.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.API_HOST, port=settings.API_PORT)


if __name__ == "__main__":
    main()
