"""Business rules for a user's own model configuration (ADR-080)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings
from app.repositories import model_configs as repo
from app.repositories.model_configs import KeyRequired, ModelConfigRow
from app.services.ai.client import Message, ModelCallError, ModelRequest
from app.services.ai.compatible import CompatibleModelClient, HttpTransport
from app.services.ai.outbound import EndpointBlocked, Resolver, check_endpoint, system_resolver
from app.services.credentials import CredentialCipher, CredentialError, ModelConfigRequired

TEST_TIMEOUT_SECONDS = 15.0
TEST_PURPOSE = "config_test"
BLOCKED_ADDRESS = "blocked_address"

__all__ = ["BLOCKED_ADDRESS", "ConfigTestLimiter", "CredentialStoreDisabled", "InvalidKey", "KeyRequired",
           "ModelConfigView", "TestOutcome", "clear", "run_test", "save", "view"]


class CredentialStoreDisabled(Exception):
    """``MODEL_CREDENTIAL_KEY`` is not configured, so nothing can be sealed or opened."""


class InvalidKey(Exception):
    """The API key cannot go into an HTTP header (non-printable, non-ASCII or spaces)."""


@dataclass(frozen=True)
class ModelConfigView:
    runtime_mode: str
    row: ModelConfigRow | None


@dataclass(frozen=True)
class TestOutcome:
    ok: bool
    error_class: str | None
    latency_ms: int


def _cipher(settings: Settings) -> CredentialCipher:
    try:
        return CredentialCipher.from_settings(settings)
    except CredentialError:
        raise CredentialStoreDisabled() from None


def _check_key(api_key: str) -> None:
    if not api_key or any(not 33 <= ord(c) <= 126 for c in api_key):
        raise InvalidKey()


def view(settings: Settings, user_id: str) -> ModelConfigView:
    return ModelConfigView(settings.LLM_MODE, repo.get_config(settings.SQLITE_URL, user_id))


def save(settings: Settings, user_id: str, *, base_url: str, model: str, api_key: str | None,
         resolver: Resolver | None = None) -> ModelConfigView:
    cipher = _cipher(settings)
    check_endpoint(base_url, allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE,
                   resolver=resolver or system_resolver)
    sealed = hint = None
    if api_key is not None:
        _check_key(api_key)
        sealed, hint = cipher.seal(user_id, api_key), api_key[-4:]
    row = repo.save_config(settings.SQLITE_URL, user_id=user_id, base_url=base_url, model=model.strip(),
                           sealed=sealed, key_hint=hint)
    return ModelConfigView(settings.LLM_MODE, row)


def clear(settings: Settings, user_id: str) -> None:
    repo.delete_config(settings.SQLITE_URL, user_id)


def run_test(settings: Settings, user_id: str, *, base_url: str | None, model: str | None, api_key: str | None,
             transport: HttpTransport, resolver: Resolver | None = None,
             clock: Callable[[], float] = time.monotonic) -> TestOutcome:
    """One minimal chat call. With no values the saved configuration is tested and the result recorded."""
    saved = base_url is None
    if saved:
        row = repo.get_config(settings.SQLITE_URL, user_id)
        if row is None:
            raise ModelConfigRequired()
        try:
            base_url, model, api_key = row.base_url, row.model, _cipher(settings).open(user_id, row.sealed)
        except CredentialError:
            raise CredentialStoreDisabled() from None
    else:
        _check_key(api_key or "")
    started = clock()
    try:
        check_endpoint(base_url or "", allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE,
                       resolver=resolver or system_resolver)
    except EndpointBlocked:
        outcome = TestOutcome(False, BLOCKED_ADDRESS, 0)
    else:
        try:
            client = CompatibleModelClient(base_url or "", api_key or "", transport=transport,
                                           default_timeout_seconds=TEST_TIMEOUT_SECONDS)
            client.complete(ModelRequest(purpose=TEST_PURPOSE, model=model or "",
                                         messages=(Message("user", "ping"),), max_output_tokens=1))
            outcome = TestOutcome(True, None, max(0, int((clock() - started) * 1000)))
        except ModelCallError as error:
            outcome = TestOutcome(False, error.error_class.value, max(0, int((clock() - started) * 1000)))
    if saved:
        repo.record_test(settings.SQLITE_URL, user_id, ok=outcome.ok, error_class=outcome.error_class)
    return outcome


class ConfigTestLimiter:
    """At most ``limit`` test calls per user in any ``window_seconds``; in-process, bounded."""

    def __init__(self, *, limit: int = 5, window_seconds: float = 60.0, capacity: int = 4096,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._limit, self._window, self._capacity, self._clock = limit, window_seconds, capacity, clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._mutex = threading.Lock()

    def acquire(self, user_id: str) -> int:
        """Return 0 when allowed, otherwise the whole seconds to wait."""
        now = self._clock()
        with self._mutex:
            hits = self._hits.setdefault(user_id, deque())
            self._hits.move_to_end(user_id)
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return max(1, int(self._window - (now - hits[0])) + 1)
            hits.append(now)
            while len(self._hits) > self._capacity:
                self._hits.popitem(last=False)
            return 0
