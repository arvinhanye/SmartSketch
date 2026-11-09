"""Assemble shared and per-request chat dependencies without HTTP state."""

from __future__ import annotations

import copy

from app.config import Settings
from app.repositories.model_calls import SqliteCallStore
from app.repositories.neo4j import Neo4jRepository
from app.services.ai.factory import build_embedding_adapter, build_model_clients, model_id
from app.services.ai.policy import ModelCallPolicy
from app.services.credentials import CredentialUnavailable, ModelConfigRequired
from app.services.qa.chat import ChatFailure, ChatService
from app.services.qa.generate import AnswerGenerator
from app.services.qa.rewrite import QueryRewriter
from app.services.qa.user_models import UserChatModels


def build_chat_service(settings: Settings) -> ChatService:
    embedding = build_embedding_adapter(settings)
    repo = Neo4jRepository.from_settings(settings)
    if settings.LLM_MODE == "personal":
        # ADR-080：没有全站模型；每个请求由 user_chat_service 换上提问者自己的改写器与生成器
        service = ChatService(settings, repo, embedding, None, None)
    else:
        primary, fallback = build_model_clients(settings)
        policy = ModelCallPolicy.from_settings(
            settings, primary=primary, fallback=fallback, store=SqliteCallStore(settings.SQLITE_URL),
        )
        model = model_id(settings, "chat")
        service = ChatService(settings, repo, embedding,
                              QueryRewriter(policy, model=model), AnswerGenerator(policy, model=model))
    return service


def with_course_embedding(base: ChatService, settings: Settings, course_id: str | None) -> ChatService:
    if course_id is not None:
        from app.services.embedding_configs import for_course
        embedding = for_course(settings, course_id)
        if embedding is not None:
            base = copy.copy(base)
            base.embedding = embedding
            # Bind a space for this request; old properties survive later config switches.
            base.current_space = lambda: embedding.space
    return base


def with_user_models(base: ChatService, models: UserChatModels, user_id: str) -> ChatService:
    try:
        rewriter, generator = models.for_user(user_id)
    except ModelConfigRequired:
        raise ChatFailure("MODEL_CONFIG_REQUIRED") from None
    except CredentialUnavailable:
        raise ChatFailure("LLM_UNAVAILABLE", reason="auth") from None
    return base.with_models(rewriter, generator)
