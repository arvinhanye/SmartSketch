"""Runtime checks shared by API startup and the future worker entry point."""

import sqlite3

from app.config import Settings, SettingsError, embedding_space_identity
from app.repositories.embedding_space import read_or_initialize_space
from app.repositories.sqlite import MigrationError, pending_migrations


def validate_schema_current(settings: Settings) -> None:
    """Fail startup unless every migration in the codebase has been applied."""
    try:
        pending = pending_migrations(settings.SQLITE_URL)
    except MigrationError as exc:
        raise SettingsError(f"SQLite schema history is inconsistent: {exc}") from None
    except (OSError, sqlite3.Error):
        raise SettingsError("Invalid configuration: SQLITE_URL (database unavailable)") from None
    if pending:
        raise SettingsError(
            f"SQLite schema is not migrated (pending: {', '.join(pending)}); "
            "stop API and worker, then run: python -m app.repositories.sqlite"
        )


def validate_embedding_space(settings: Settings) -> None:
    """Fail startup when the configured embedding space differs from SQLite."""
    configured = embedding_space_identity(settings)
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


def check_embedding_space_change(settings: Settings) -> str:
    """向量空间与已有数据是否一致：一致返回空串，不一致返回用户可读说明。

    不能因为「设置改了、旧数据还是旧的」就拒绝启动：用户必须能打开软件、进「API 设置」和
    课程页去重新处理资料。真正需要隔离的读写仍由各自的服务校验。
    """
    configured = embedding_space_identity(settings)
    try:
        recorded = read_or_initialize_space(settings.SQLITE_URL, *configured)
    except (OSError, sqlite3.Error):
        return ""
    if recorded == configured:
        return ""
    return (
        "课程里已有内容是用之前的向量设置生成的：请在课程页点「重新处理资料」，"
        "处理完成后才会使用新设置。"
    )
