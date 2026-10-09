"""Business rules for a user's own model configuration (ADR-080)."""

from __future__ import annotations

import json
import http.client
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from typing import Protocol
from dataclasses import dataclass

from app.config import Settings
from app.repositories import model_configs as repo
from app.repositories.model_configs import KeyRequired, ModelConfigRow
from app.services.ai.client import Message, ModelCallError, ModelRequest
from app.services.ai.compatible import CompatibleModelClient, HttpResponse, HttpTransport, thinking_body
from app.services.ai.outbound import EndpointBlocked, Resolver, check_endpoint, check_endpoint_url, system_resolver
from app.services.credentials import CredentialCipher, CredentialError, ModelConfigRequired

TEST_TIMEOUT_SECONDS = 15.0
TEST_PURPOSE = "config_test"
BLOCKED_ADDRESS = "blocked_address"

__all__ = ["BLOCKED_ADDRESS", "ConfigTestLimiter", "CredentialStoreDisabled", "InvalidKey", "InvalidModel", "KeyRequired",
           "ModelConfigView", "TestOutcome", "clear", "normalize_model", "run_test", "save", "view"]

MODEL_MAX_LENGTH = 128


class CredentialStoreDisabled(Exception):
    """``MODEL_CREDENTIAL_KEY`` is not configured, so nothing can be sealed or opened."""


class InvalidKey(Exception):
    """The API key cannot go into an HTTP header (non-printable, non-ASCII or spaces)."""


class InvalidModel(Exception):
    """The model name is blank after trimming (N08); ``reason`` is machine-readable."""

    def __init__(self, reason: str = "blank") -> None:
        super().__init__(reason)
        self.reason = reason


def normalize_model(model: str) -> str:
    """Shared by save and test: trim, then refuse an empty name before anything is stored or sent."""
    value = model.strip()
    if not value:
        raise InvalidModel("blank")
    if len(value) > MODEL_MAX_LENGTH:
        raise InvalidModel("too_long")
    return value


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
         resolver: Resolver | None = None, disable_thinking: bool | None = None) -> ModelConfigView:
    cipher = _cipher(settings)
    model = normalize_model(model)
    check_endpoint(base_url, allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE,
                   resolver=resolver or system_resolver)
    sealed = hint = None
    if api_key is not None:
        _check_key(api_key)
        sealed, hint = cipher.seal(user_id, api_key), api_key[-4:]
    row = repo.save_config(settings.SQLITE_URL, user_id=user_id, base_url=base_url, model=model,
                           sealed=sealed, key_hint=hint, disable_thinking=disable_thinking)
    return ModelConfigView(settings.LLM_MODE, row)


def clear(settings: Settings, user_id: str) -> None:
    repo.delete_config(settings.SQLITE_URL, user_id)


def run_test(settings: Settings, user_id: str, *, base_url: str | None, model: str | None, api_key: str | None,
             transport: HttpTransport, resolver: Resolver | None = None,
             clock: Callable[[], float] = time.monotonic, disable_thinking: bool = False) -> TestOutcome:
    """One minimal chat call. With no values the saved configuration is tested and the result recorded.

    The credential store is checked first on every branch (N07): without a root key nothing is
    resolved or sent, even for a complete request body. The request carries the same thinking switch
    that would be used after saving: the form value, or the saved value when testing the saved row (ADR-090).
    """
    cipher = _cipher(settings)
    saved = base_url is None
    revision = None
    if saved:
        row = repo.get_config(settings.SQLITE_URL, user_id)
        if row is None:
            raise ModelConfigRequired()
        revision = row.revision
        disable_thinking = row.disable_thinking
        try:
            base_url, model, api_key = row.base_url, row.model, cipher.open(user_id, row.sealed)
        except CredentialError:
            raise CredentialStoreDisabled() from None
    else:
        model = normalize_model(model or "")
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
                                           default_timeout_seconds=TEST_TIMEOUT_SECONDS,
                                           extra_body=thinking_body(disable_thinking))
            client.complete(ModelRequest(purpose=TEST_PURPOSE, model=model or "",
                                         messages=(Message("user", "ping"),), max_output_tokens=1))
            outcome = TestOutcome(True, None, max(0, int((clock() - started) * 1000)))
        except ModelCallError as error:
            outcome = TestOutcome(False, error.error_class.value, max(0, int((clock() - started) * 1000)))
    if saved and revision is not None:
        # Conditional on the tested revision: a configuration saved or recreated meanwhile keeps its own state.
        repo.record_test(settings.SQLITE_URL, user_id, revision=revision, ok=outcome.ok,
                         error_class=outcome.error_class)
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


class ModelDirectoryTransport(Protocol):
    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse: ...


@dataclass(frozen=True)
class ModelDirectory:
    ok: bool
    models: list[str]
    error_class: str | None = None


def discover_models(settings: Settings, user_id: str, *, base_url: str | None, api_key: str | None,
                    transport: ModelDirectoryTransport) -> ModelDirectory:
    """Read a bounded OpenAI-compatible directory without changing credentials or test state."""
    cipher = _cipher(settings)
    if api_key is None:
        row = repo.get_config(settings.SQLITE_URL, user_id)
        if row is None:
            raise ModelConfigRequired()
        if base_url is not None and base_url != row.base_url:
            raise KeyRequired()
        base_url = row.base_url
        try:
            api_key = cipher.open(user_id, row.sealed)
        except CredentialError:
            raise CredentialStoreDisabled() from None
    elif not base_url:
        raise KeyRequired()
    _check_key(api_key)
    response = None
    started = time.monotonic()
    def failed(reason: str) -> ModelDirectory:
        return ModelDirectory(False, [], reason)
    try:
        check_endpoint_url(base_url or "", allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE)
        # GuardedTransport.get resolves and pins public addresses within the same deadline.
        response = transport.get((base_url or "").rstrip("/") + "/models",
                                 {"Authorization": "Bearer " + api_key, "Accept": "application/json"},
                                 TEST_TIMEOUT_SECONDS)
        code = response.status
        if code != 200:
            reason = ("auth" if code in (401, 403) else "unsupported" if code in (404, 405, 501)
                      else "rate_limited" if code == 429 else "server" if code >= 500 else "malformed_response")
            return failed(reason)
        data = bytearray()
        while True:
            remaining = TEST_TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError()
            chunk = response.read(min(65536, 1048577 - len(data)), remaining)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 1048576:
                return failed("malformed_response")
        payload = json.loads(data)
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or len(entries) > 1000:
            return failed("malformed_response")
        models = set()
        for entry in entries:
            name = entry.get("id") if isinstance(entry, dict) else None
            if (not isinstance(name, str) or not name.strip() or len(name) > MODEL_MAX_LENGTH
                    or any(ord(c) < 32 or ord(c) == 127 for c in name) or api_key in name):
                return failed("malformed_response")
            models.add(name)
        return ModelDirectory(True, sorted(models))
    except EndpointBlocked:
        return failed("blocked_address")
    except TimeoutError:
        return failed("timeout")
    except (OSError, http.client.HTTPException):
        return failed("connection")
    except (ValueError, UnicodeError):
        return failed("malformed_response")
    finally:
        if response is not None:
            response.close()
