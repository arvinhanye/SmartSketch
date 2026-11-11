"""SQLite setup shared by tests; callers own the URL and temporary database."""

from pathlib import Path

from app.repositories.sqlite import migrate


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def migrated_database(url: str) -> str:
    """Apply current migrations to the caller-owned database and return its URL.

    No path allocation, state cache, or fixture-scope widening happens here.
    Migration/upgrade assertions should keep calling migrate directly.
    """
    migrate(url)
    return url
