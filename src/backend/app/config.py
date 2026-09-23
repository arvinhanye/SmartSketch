"""Typed runtime settings loaded only from environment variables."""

import os
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError


class SettingsError(ValueError):
    """A configuration error containing variable names, never supplied values."""


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="ignore", frozen=True, hide_input_in_errors=True, validate_default=True
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    API_HOST: str = Field(default="127.0.0.1", min_length=1)
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    WEB_ORIGIN: str = "http://localhost:5173"
    SQLITE_URL: str = "sqlite:///./storage/smartsketch.sqlite3"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = Field(default="neo4j", min_length=1)
    NEO4J_PASSWORD: SecretStr = SecretStr("")

    LLM_MODE: Literal["fake", "live"] = "fake"
    EMBEDDING_MODE: Literal["fake", "online", "local"] = "fake"
    LLM_BASE_URL: str = ""
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_EXTRACTION_MODEL: str = ""
    LLM_CHAT_MODEL: str = ""
    LLM_FALLBACK_BASE_URL: str = ""
    LLM_FALLBACK_API_KEY: SecretStr = SecretStr("")
    LLM_FALLBACK_EXTRACTION_MODEL: str = ""
    LLM_FALLBACK_CHAT_MODEL: str = ""

    LLM_REQUEST_TIMEOUT_SECONDS: float = Field(default=60, gt=0, allow_inf_nan=False)
    LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS: float = Field(default=5, gt=0, allow_inf_nan=False)
    LLM_CHAT_TIMEOUT_SECONDS: float = Field(default=15, gt=0, allow_inf_nan=False)
    LLM_MAX_CONCURRENCY: int = Field(default=4, ge=1)
    LLM_MAX_RETRIES: int = Field(default=2, ge=0)
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = Field(default=5, ge=1)
    LLM_CIRCUIT_OPEN_SECONDS: int = Field(default=30, ge=1)
    LLM_TASK_TOKEN_BUDGET: int = Field(default=500000, ge=0)
    LLM_DAILY_TOKEN_BUDGET: int = Field(default=5000000, ge=0)

    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: SecretStr = SecretStr("")
    EMBEDDING_MODEL: str = ""
    EMBEDDING_DIMENSIONS: int = Field(default=1024, ge=1)
    EMBEDDING_BATCH_SIZE: int = Field(default=10, ge=1)

    TASK_MAX_FAILED_CHUNK_RATIO: float = Field(default=0.2, ge=0, lt=1, allow_inf_nan=False)
    WORKER_PROCESSES: int = Field(default=1, ge=1)
    TASK_LEASE_SECONDS: int = Field(default=60, ge=15)
    TASK_MAX_ATTEMPTS: int = Field(default=3, ge=1)
    TASK_CHUNK_MAX_ATTEMPTS: int = Field(default=2, ge=1)
    TASK_ARTIFACT_RETENTION_DAYS: int = Field(default=7, ge=0)
    PUBLISH_LEASE_SECONDS: int = Field(default=60, ge=15)
    COURSE_LOCK_WAIT_SECONDS: int = Field(default=5, ge=0)


def _has_value(value: str | SecretStr) -> bool:
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    return bool(raw.strip())


def _valid_url(value: str, schemes: set[str]) -> bool:
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in schemes
            and parsed.hostname is not None
            and parsed.port != 0
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _check_rules(settings: Settings) -> None:
    invalid: set[str] = set()
    if not _valid_url(settings.WEB_ORIGIN, {"http", "https"}):
        invalid.add("WEB_ORIGIN")
    else:
        origin = urlsplit(settings.WEB_ORIGIN)
        if origin.path or origin.query or origin.fragment:
            invalid.add("WEB_ORIGIN")
    for name in ("LLM_BASE_URL", "LLM_FALLBACK_BASE_URL", "EMBEDDING_BASE_URL"):
        value = getattr(settings, name)
        if value and not _valid_url(value, {"http", "https"}):
            invalid.add(name)
    if not _valid_url(settings.NEO4J_URI, {"bolt", "neo4j"}):
        invalid.add("NEO4J_URI")
    if (
        not settings.SQLITE_URL.startswith("sqlite:///")
        or not settings.SQLITE_URL[10:].strip()
        or settings.SQLITE_URL[10:] == ":memory:"
        or "?" in settings.SQLITE_URL
        or "#" in settings.SQLITE_URL
    ):
        invalid.add("SQLITE_URL")

    primary = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_EXTRACTION_MODEL", "LLM_CHAT_MODEL")
    fallback = (
        "LLM_FALLBACK_BASE_URL",
        "LLM_FALLBACK_API_KEY",
        "LLM_FALLBACK_EXTRACTION_MODEL",
        "LLM_FALLBACK_CHAT_MODEL",
    )
    if settings.LLM_MODE == "live":
        invalid.update(name for name in primary if not _has_value(getattr(settings, name)))
    if any(_has_value(getattr(settings, name)) for name in fallback):
        invalid.update(name for name in fallback if not _has_value(getattr(settings, name)))
    if settings.EMBEDDING_MODE == "online":
        invalid.update(
            name
            for name in ("EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL")
            if not _has_value(getattr(settings, name))
        )
    elif settings.EMBEDDING_MODE == "local" and not _has_value(settings.EMBEDDING_MODEL):
        invalid.add("EMBEDDING_MODEL")
    if settings.APP_ENV == "production":
        if settings.LLM_MODE == "fake":
            invalid.add("LLM_MODE")
        if settings.EMBEDDING_MODE == "fake":
            invalid.add("EMBEDDING_MODE")
    if settings.LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS >= settings.LLM_CHAT_TIMEOUT_SECONDS:
        invalid.update(("LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS", "LLM_CHAT_TIMEOUT_SECONDS"))
    if invalid:
        raise SettingsError(f"Invalid configuration: {', '.join(sorted(invalid))}")


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Validate environment values without reading a .env file or contacting services."""
    source = os.environ if environ is None else environ
    try:
        settings = Settings.model_validate(source)
    except ValidationError as exc:
        names = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        raise SettingsError(f"Invalid configuration: {', '.join(names)}") from None
    _check_rules(settings)
    return settings
