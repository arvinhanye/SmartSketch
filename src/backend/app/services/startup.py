"""Runtime checks shared by API startup and the future worker entry point."""

import sqlite3

from app.config import Settings, SettingsError
from app.repositories.embedding_space import read_or_initialize_space


def validate_embedding_space(settings: Settings) -> None:
    """Fail startup when the configured embedding space differs from SQLite."""
    configured = (
        settings.EMBEDDING_MODEL if settings.EMBEDDING_MODE != "fake" else "",
        settings.EMBEDDING_DIMENSIONS,
        int(settings.EMBEDDING_MODE == "fake"),
    )
    try:
        recorded = read_or_initialize_space(settings.SQLITE_URL, *configured)
    except (OSError, sqlite3.Error):
        raise SettingsError("Invalid configuration: SQLITE_URL (embedding space unavailable)") from None
    if recorded != configured:
        def describe(space: tuple[str, int, int]) -> str:
            model, dimensions, is_fake = space
            return f"{'fake' if is_fake else model}/{dimensions}"

        raise SettingsError(
            "EMBEDDING_MODEL/EMBEDDING_DIMENSIONS mismatch: "
            f"recorded {describe(recorded)}, configured {describe(configured)}; "
            "需运行离线重新向量化命令（见 specs/teacher-review-publish.md V12）"
        )
