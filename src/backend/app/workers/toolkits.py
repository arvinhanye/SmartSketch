"""personal 模式：按任务的密钥快照构建抽取工具包（ADR-080 决定 3）。

每个任务一份独立的 ``ModelCallPolicy``，熔断状态互不影响。快照缺失、已置空或不可解时抛
``CredentialUnavailable``，由流水线把任务终止为 ``LLM_UNAVAILABLE``。
"""

from __future__ import annotations

from app.config import Settings
from app.repositories.model_calls import SqliteCallStore
from app.repositories.model_configs import binding_active, get_binding
from app.repositories.task_leases import Lease
from app.services.ai.compatible import CompatibleModelClient, HttpTransport, thinking_body
from app.services.ai.entities import EntityExtractor
from app.services.ai.outbound import build_transport
from app.services.ai.policy import CallStore, ModelCallPolicy
from app.services.ai.relations import RelationExtractor
from app.services.credentials import CredentialCipher, CredentialError, CredentialUnavailable
from app.workers.extract_task import ExtractionToolkit

# 与 K02 评测脚本的缺省值一致（evaluation/run_live_extraction.py）
MAX_OUTPUT_TOKENS = 4096


class TaskToolkits:
    def __init__(self, settings: Settings, *, cipher: CredentialCipher | None = None,
                 store: CallStore | None = None, transport: HttpTransport | None = None) -> None:
        self._settings = settings
        self._cipher = cipher or CredentialCipher.from_settings(settings)
        self._store = store or SqliteCallStore(settings.SQLITE_URL)
        self._transport = transport or build_transport(settings)

    def _require_active(self, task_id: str) -> None:
        if not binding_active(self._settings.SQLITE_URL, task_id):
            raise CredentialUnavailable("credential_revoked")

    def for_lease(self, lease: Lease) -> ExtractionToolkit:
        binding = get_binding(self._settings.SQLITE_URL, lease.task_id)
        if binding is None:
            raise CredentialUnavailable("credential_missing")
        if binding.sealed is None:
            raise CredentialUnavailable(
                "credential_revoked" if binding.scrub_reason == "revoked" else "credential_missing")
        try:
            api_key = self._cipher.open(binding.user_id, binding.sealed)
            client = CompatibleModelClient(binding.base_url, api_key, transport=self._transport,
                                           default_timeout_seconds=self._settings.LLM_REQUEST_TIMEOUT_SECONDS,
                                           extra_body=thinking_body(binding.disable_thinking))
        except (CredentialError, ValueError):
            raise CredentialUnavailable("credential_unreadable") from None
        policy = ModelCallPolicy.from_settings(self._settings, primary=client, store=self._store)
        model, task_id = binding.model, lease.task_id
        return ExtractionToolkit(
            policy=policy,
            entities=lambda bound: EntityExtractor(bound, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
            relations=lambda bound: RelationExtractor(bound, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
            user_id=binding.user_id,
            guard=lambda: self._require_active(task_id),
            model=model,
        )
