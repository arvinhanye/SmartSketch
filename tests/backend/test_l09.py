"""L09：local 向量明确不支持（ADR-081）；personal 模式的启动约束。"""
import base64

import pytest

from app.config import SettingsError, load_settings

ROOT_KEY_B64 = base64.urlsafe_b64encode(bytes(range(32))).decode()


def test_local_embedding_is_rejected_with_a_clear_name():
    with pytest.raises(SettingsError, match="EMBEDDING_MODE"):
        load_settings({"EMBEDDING_MODE": "local", "EMBEDDING_MODEL": "bge-small-zh-v1.5"})


def test_personal_mode_does_not_need_global_llm_variables():
    settings = load_settings({"LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                              "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": "https://e.example/v1",
                              "EMBEDDING_API_KEY": "k", "EMBEDDING_MODEL": "text-embedding-v4"})
    assert settings.LLM_BASE_URL == "" and settings.LLM_MODE == "personal"


def test_personal_mode_is_allowed_in_production_with_online_embedding():
    settings = load_settings({"APP_ENV": "production", "LLM_MODE": "personal", "MODEL_CREDENTIAL_KEY": ROOT_KEY_B64,
                              "EMBEDDING_MODE": "online", "EMBEDDING_BASE_URL": "https://e.example/v1",
                              "EMBEDDING_API_KEY": "k", "EMBEDDING_MODEL": "text-embedding-v4"})
    assert settings.APP_ENV == "production"
