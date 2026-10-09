"""按 ``LLM_MODE`` / ``EMBEDDING_MODE`` 装配模型与向量客户端（worker、问答、发布与离线脚本共用）。

- ``live``：E03 ``CompatibleModelClient``（备用四项齐全时另建备用）；``online``/``local``：E03 向量客户端。
- ``demo``：ADR-076 演示客户端——确定性、无网络，按规则产出能被真实解析器接受的输出。模型 ID 固定为
  ``DEMO_MODEL_ID``，不沿用 ``LLM_*_MODEL``，免得演示结果记在真实模型名下（``model_calls``、抽取缓存键）。
- ``fake``：E02 缺省 fake 客户端，行为与原先逐字相同（大量测试依赖）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.config import Settings
from app.services.ai.client import EmbeddingClient, ModelClient
from app.services.ai.demo import DEMO_MODEL_ID, DemoEmbeddingClient, DemoModelClient
from app.services.ai.fake import FakeEmbeddingClient, FakeModelClient

if TYPE_CHECKING:
    from app.services.ai.embeddings import EmbeddingAdapter

__all__ = ["FAKE_MODEL_ID", "build_embedding_adapter", "build_embedding_client", "build_model_clients", "model_id"]

FAKE_MODEL_ID = "fake"


def build_model_clients(settings: Settings) -> tuple[ModelClient, ModelClient | None]:
    """返回 ``(主用, 备用)``；只有 ``live`` 且配了备用四项时备用非空。"""
    if settings.LLM_MODE == "personal":
        raise RuntimeError("LLM_MODE=personal has no process-wide model client (ADR-080)")
    if settings.LLM_MODE == "live":
        from app.services.ai.compatible import CompatibleModelClient

        primary = CompatibleModelClient.from_settings(settings, role="primary")
        fallback = (CompatibleModelClient.from_settings(settings, role="fallback")
                    if settings.LLM_FALLBACK_BASE_URL.strip() else None)
        return primary, fallback
    if settings.LLM_MODE == "demo":
        return DemoModelClient(), None
    return FakeModelClient(), None


def model_id(settings: Settings, role: Literal["extraction", "chat"]) -> str:
    """请求里的模型 ID：demo 固定为 ``DEMO_MODEL_ID``；其余取配置，空时退回 ``fake``。"""
    if settings.LLM_MODE == "demo":
        return DEMO_MODEL_ID
    configured = settings.LLM_EXTRACTION_MODEL if role == "extraction" else settings.LLM_CHAT_MODEL
    return configured.strip() or FAKE_MODEL_ID


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    if settings.EMBEDDING_MODE == "fake":
        return FakeEmbeddingClient()
    if settings.EMBEDDING_MODE == "demo":
        return DemoEmbeddingClient()
    from app.services.ai.compatible import CompatibleEmbeddingClient

    return CompatibleEmbeddingClient.from_settings(settings)


def build_embedding_adapter(settings: Settings) -> EmbeddingAdapter:
    """发布与问答共用的系统级向量装配（ADR-082 决定 6）：真实在线向量的每次请求都写 ``model_calls``；
    fake/demo 不出站，不记账。离线脚本自行装配（``scripts/reembed.py`` 有自己的调用台账）。"""
    from app.repositories.model_calls import SqliteCallStore
    from app.services.ai.embeddings import EmbeddingAdapter

    store = SqliteCallStore(settings.SQLITE_URL) if settings.EMBEDDING_MODE == "online" else None
    return EmbeddingAdapter(settings, build_embedding_client(settings), store=store, max_retries=2)
