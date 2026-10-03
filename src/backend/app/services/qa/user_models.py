"""personal 模式：按「用户 + 配置版本」缓存问答改写器与生成器（ADR-080 决定 4）。

每个用户一份独立的 ``ModelCallPolicy``：熔断状态、调用归属与日预算都落在本人名下。
配置版本变化即重建；容量有界，最久未用的先淘汰。
"""

from __future__ import annotations

import threading
from collections import OrderedDict

from app.config import Settings
from app.repositories.model_calls import SqliteCallStore
from app.repositories.model_configs import get_config
from app.services.ai.compatible import CompatibleModelClient, HttpTransport
from app.services.ai.outbound import build_transport
from app.services.ai.policy import CallStore, ModelCallPolicy
from app.services.credentials import CredentialCipher, CredentialError, CredentialUnavailable, ModelConfigRequired
from app.services.qa.generate import AnswerGenerator
from app.services.qa.rewrite import QueryRewriter


class UserChatModels:
    def __init__(self, settings: Settings, *, cipher: CredentialCipher | None = None, store: CallStore | None = None,
                 transport: HttpTransport | None = None, capacity: int = 64) -> None:
        self._settings = settings
        self._cipher = cipher or CredentialCipher.from_settings(settings)
        self._store = store or SqliteCallStore(settings.SQLITE_URL)
        self._transport = transport or build_transport(settings)
        self._capacity = capacity
        self._cache: OrderedDict[str, tuple[int, QueryRewriter, AnswerGenerator]] = OrderedDict()
        self._mutex = threading.Lock()

    def __len__(self) -> int:
        return len(self._cache)

    def for_user(self, user_id: str) -> tuple[QueryRewriter, AnswerGenerator]:
        row = get_config(self._settings.SQLITE_URL, user_id)
        with self._mutex:
            if row is None:
                self._cache.pop(user_id, None)
                raise ModelConfigRequired()
            cached = self._cache.get(user_id)
            if cached is not None and cached[0] == row.version:
                self._cache.move_to_end(user_id)
                return cached[1], cached[2]
            try:
                api_key = self._cipher.open(user_id, row.sealed)
                client = CompatibleModelClient(row.base_url, api_key, transport=self._transport,
                                               default_timeout_seconds=self._settings.LLM_REQUEST_TIMEOUT_SECONDS)
            except (CredentialError, ValueError):
                raise CredentialUnavailable("credential_unreadable") from None
            policy = ModelCallPolicy.from_settings(self._settings, primary=client, store=self._store)
            pair = (QueryRewriter(policy, model=row.model, user_id=user_id),
                    AnswerGenerator(policy, model=row.model, user_id=user_id))
            self._cache[user_id] = (row.version, *pair)
            self._cache.move_to_end(user_id)
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)
            return pair
