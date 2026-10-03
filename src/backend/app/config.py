"""Typed runtime settings loaded only from environment variables."""

import base64
import binascii
import math
import os
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError


class SettingsError(ValueError):
    """A configuration error containing variable names, never supplied values."""


RECOMMEND_WEIGHT_NAMES = (
    "RECOMMEND_WEIGHT_UNLOCK",
    "RECOMMEND_WEIGHT_IMPORTANCE",
    "RECOMMEND_WEIGHT_CHAPTER",
    "RECOMMEND_WEIGHT_EASE",
)
DEFAULT_RECOMMEND_WEIGHTS = (0.35, 0.25, 0.20, 0.20)
AUTH_JWT_SECRET_MIN_BYTES = 32
#: EMBEDDING_MODE=demo 的保留模型 ID（ADR-076）：演示向量记为独立的真实空间 ``real/<此 ID>/<维度>``，
#: 不与 ``fake/<维度>`` 或任何供应商模型混用；online/local 不得把 EMBEDDING_MODEL 设成它。
DEMO_EMBEDDING_MODEL = "smartsketch-demo-ngram-v1"


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="ignore", frozen=True, hide_input_in_errors=True, validate_default=True
    )

    APP_ENV: Literal["development", "test", "production"] = "development"
    API_HOST: str = Field(default="127.0.0.1", min_length=1)
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    WEB_ORIGIN: str = "http://localhost:5173"
    SQLITE_URL: str = "sqlite:///./storage/smartsketch.sqlite3"
    # 资料落盘根目录与单文件上限（D-11）；由 C06/C07 传给 FileStorage(root, max_bytes)
    STORAGE_DIR: str = "./storage"
    UPLOAD_MAX_BYTES: int = Field(default=52_428_800, ge=1)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = Field(default="neo4j", min_length=1)
    NEO4J_PASSWORD: SecretStr = SecretStr("")

    # demo：确定性、无网络的规则演示模型与字符 n-gram 向量（ADR-076），用于无付费模型的整链路验收
    # personal（ADR-080）：无全站大模型客户端，任务用快照、问答用本人配置；LLM_* 的地址、key、模型名不读取
    LLM_MODE: Literal["fake", "demo", "live", "personal"] = "fake"
    EMBEDDING_MODE: Literal["fake", "demo", "online", "local"] = "fake"
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
    QA_SIMILARITY_THRESHOLD: float = Field(default=0.7, ge=0, le=1, allow_inf_nan=False)
    QA_CONTEXT_CHUNK_TOKENS: int = Field(default=12000, ge=1)
    QA_CONTEXT_GRAPH_TOKENS: int = Field(default=2000, ge=0)
    QA_CONTEXT_MAX_CHUNKS: int = Field(default=8, ge=1)
    QA_VECTOR_LIMIT: int = Field(default=20, ge=1)
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
    # G05 发布清扫的周期调度（A06 §8.6，ADR-072）：worker 每轮主循环后检查，到点调用 reconcile.sweep。
    # 0 表示不启用周期清扫（发布/回滚前的 reclaim_expired 仍在，见 ADR-036 第 6 条）。
    PUBLISH_SWEEP_INTERVAL_SECONDS: int = Field(default=3600, ge=0)

    # 本地账号登录（ADR-013、specs/identity-access.md §2.1、§6）。密钥不在 load_settings 里强制：
    # worker 与迁移命令不签发令牌；API 服务入口另行调用 check_auth_settings（C13）。
    AUTH_JWT_SECRET: SecretStr = SecretStr("")
    AUTH_ACCESS_TOKEN_TTL_SECONDS: int = Field(default=28800, ge=1)

    # 个人模型凭据（ADR-080）：根密钥为 32 字节的 URL 安全 base64；personal 模式必填。
    MODEL_CREDENTIAL_KEY: SecretStr = SecretStr("")
    # 仅测试：放行回环/内网模型地址（本机假供应商）；production 下为真即拒绝启动。
    MODEL_ENDPOINT_ALLOW_PRIVATE: bool = False

    # 四项成组（ADR-014 修订 1 决定 6）；都不设或都为空时用 S2 缺省值，读取请用 recommend_weights
    RECOMMEND_WEIGHT_UNLOCK: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    RECOMMEND_WEIGHT_IMPORTANCE: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    RECOMMEND_WEIGHT_CHAPTER: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    RECOMMEND_WEIGHT_EASE: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @property
    def recommend_weights(self) -> tuple[float, float, float, float]:
        """(unlock, importance, chapter, ease)，顺序固定。"""
        values = tuple(getattr(self, name) for name in RECOMMEND_WEIGHT_NAMES)
        if all(value is None for value in values):
            return DEFAULT_RECOMMEND_WEIGHTS
        return values  # type: ignore[return-value]  # _check_rules 已保证四项齐全


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


def _valid_credential_key(value: SecretStr) -> bool:
    text = value.get_secret_value().strip()
    try:
        return len(base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)) == 32
    except (binascii.Error, ValueError):
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
    if not settings.STORAGE_DIR.strip():
        invalid.add("STORAGE_DIR")

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
    if settings.EMBEDDING_MODE in ("online", "local") and settings.EMBEDDING_MODEL.strip() == DEMO_EMBEDDING_MODEL:
        invalid.add("EMBEDDING_MODEL")
    if _has_value(settings.MODEL_CREDENTIAL_KEY) or settings.LLM_MODE == "personal":
        if not _valid_credential_key(settings.MODEL_CREDENTIAL_KEY):
            invalid.add("MODEL_CREDENTIAL_KEY")
    if settings.APP_ENV == "production":
        if settings.MODEL_ENDPOINT_ALLOW_PRIVATE:
            invalid.add("MODEL_ENDPOINT_ALLOW_PRIVATE")
        if settings.LLM_MODE in ("fake", "demo"):
            invalid.add("LLM_MODE")
        if settings.EMBEDDING_MODE in ("fake", "demo"):
            invalid.add("EMBEDDING_MODE")
    if settings.LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS >= settings.LLM_CHAT_TIMEOUT_SECONDS:
        invalid.update(("LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS", "LLM_CHAT_TIMEOUT_SECONDS"))
    weights = [getattr(settings, name) for name in RECOMMEND_WEIGHT_NAMES]
    if any(value is not None for value in weights) and (
        any(value is None for value in weights)
        or not any(weights)
        or not math.isclose(sum(weights), 1, rel_tol=0, abs_tol=1e-9)
    ):
        invalid.update(RECOMMEND_WEIGHT_NAMES)
    if invalid:
        raise SettingsError(f"Invalid configuration: {', '.join(sorted(invalid))}")


def embedding_model_id(settings: Settings) -> str:
    """向量请求里的模型 ID：fake 为 ``fake``，demo 为保留 ID，其余取 ``EMBEDDING_MODEL``。"""
    if settings.EMBEDDING_MODE == "fake":
        return "fake"
    if settings.EMBEDDING_MODE == "demo":
        return DEMO_EMBEDDING_MODEL
    return settings.EMBEDDING_MODEL


def embedding_space_identity(settings: Settings) -> tuple[str, int, int]:
    """配置的向量空间在 ``embedding_space_state`` 中的记录形状 ``(model, dimensions, is_fake)``。

    E07、B06 启动门禁、F03 索引创建与 V12 重新向量化共用这一推导（ADR-012、ADR-076）。
    """
    if settings.EMBEDDING_MODE == "fake":
        return "", settings.EMBEDDING_DIMENSIONS, 1
    return embedding_model_id(settings), settings.EMBEDDING_DIMENSIONS, 0


def check_auth_settings(settings: Settings) -> None:
    """Refuse to serve the API without a token signing secret of at least 32 bytes.

    There is no fallback key (specs/identity-access.md §2.1, IAM-23); the error names
    the variable only, never the supplied value.
    """
    raw = settings.AUTH_JWT_SECRET.get_secret_value()
    if not raw.strip() or len(raw.encode("utf-8")) < AUTH_JWT_SECRET_MIN_BYTES:
        raise SettingsError(
            "Invalid configuration: AUTH_JWT_SECRET "
            f"(required, at least {AUTH_JWT_SECRET_MIN_BYTES} bytes)"
        )


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Validate environment values without reading a .env file or contacting services."""
    source = dict(os.environ if environ is None else environ)
    # 空字符串等同未设置，与「都为空时用缺省值」一致
    for name in RECOMMEND_WEIGHT_NAMES:
        if name in source and not source[name].strip():
            del source[name]
    # 布尔变量在 .env 里留空等同未设置
    if "MODEL_ENDPOINT_ALLOW_PRIVATE" in source and not source["MODEL_ENDPOINT_ALLOW_PRIVATE"].strip():
        del source["MODEL_ENDPOINT_ALLOW_PRIVATE"]
    try:
        settings = Settings.model_validate(source)
    except ValidationError as exc:
        names = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        raise SettingsError(f"Invalid configuration: {', '.join(names)}") from None
    _check_rules(settings)
    return settings
