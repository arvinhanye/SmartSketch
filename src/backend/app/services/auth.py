"""Local account login and access-token issuance (specs/identity-access.md §1–§2.1, ADR-013).

Only issuance lives here. Verifying bearer tokens on each request and resolving the caller
identity belong to C03; the event ticket to C16; account commands and demo seeding to C14.
Passwords, hashes and tokens are never logged or placed in exception messages.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings, check_auth_settings
from app.repositories.accounts import AccountRecord, find_by_username, insert_account

# Fixed by the spec, deliberately not configurable (§1.3, §6).
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 60
LOGIN_LIMITER_CAPACITY = 10_000

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = re.compile(rf"[a-z0-9_.-]{{{USERNAME_MIN_LENGTH},{USERNAME_MAX_LENGTH}}}")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
ROLES = ("teacher", "student")

# argon2id with the RFC 9106 "second recommended" (low-memory) profile, spelled out so an
# upgrade of argon2-cffi cannot silently change the cost of new hashes.
_HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID
)
_dummy_hash: str | None = None
_dummy_lock = threading.Lock()


class AccountValidationError(ValueError):
    """Account input violates §1.1 / §1.4; the message names the field, never its value."""


class InvalidCredentials(Exception):
    """Unknown user, disabled account or wrong password — deliberately indistinguishable."""


class LoginRateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("login rate limited")
        self.retry_after = retry_after


# --- password hashing ---------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _timing_dummy_hash() -> str:
    """A fixed hash with the real parameters, verified when the user does not exist (§1.3.2)."""
    global _dummy_hash
    with _dummy_lock:
        if _dummy_hash is None:
            _dummy_hash = hash_password(secrets.token_urlsafe(32))
        return _dummy_hash


def prepare_timing_dummy_hash() -> None:
    """Build the dummy hash ahead of the first request (called from ``create_app``).

    Generating it lazily made the first unknown-username login pay one hash plus one
    verification — about twice the usual time — which is itself a timing signal.
    """
    _timing_dummy_hash()


# --- accounts -----------------------------------------------------------------------------


def normalize_username(username: str) -> str:
    return username.lower()


def create_account(
    sqlite_url: str, username: str, password: str, role: str
) -> AccountRecord:
    """Validate and store a new enabled account; the building block for C14's commands."""
    normalized = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise AccountValidationError("username must be 3-32 characters of [a-z0-9_.-]")
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise AccountValidationError(
            f"password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters"
        )
    if role not in ROLES:
        raise AccountValidationError("role must be teacher or student")
    return insert_account(
        sqlite_url,
        account_id=uuid.uuid4().hex,
        username=normalized,
        password_hash=hash_password(password),
        role=role,
    )


# --- failed-login limiter -----------------------------------------------------------------


@dataclass
class _Streak:
    failures: int = 0
    locked_until: float | None = None


class LoginRateLimiter:
    """In-process counter of consecutive failed logins per lower-cased username (§1.3.3).

    After ``max_failures`` consecutive failures the key is locked for ``lock_seconds``;
    when the lock expires the streak starts over, and a successful login clears it.
    Unknown usernames are counted too. At most ``capacity`` keys are kept. When full, the
    evicted entry is, in order of preference: an expired lock; the least recently failed
    unlocked streak; and only when every entry is an active lock, the lock expiring first.
    Flooding with fresh usernames therefore cannot lift a lock while any unlocked entry
    remains. Each API process counts separately: a mitigation, not a guarantee.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_failures: int = LOGIN_MAX_FAILURES,
        lock_seconds: int = LOGIN_LOCK_SECONDS,
        capacity: int = LOGIN_LIMITER_CAPACITY,
    ) -> None:
        self._clock = clock
        self._max_failures = max_failures
        self._lock_seconds = lock_seconds
        self._capacity = capacity
        # Unlocked streaks in least-recently-failed order.
        self._open: OrderedDict[str, _Streak] = OrderedDict()
        # Active locks in lock order; every lock lasts ``lock_seconds``, so this is also
        # expiry order and the first entry is always the one expiring soonest.
        self._locked: OrderedDict[str, _Streak] = OrderedDict()
        self._mutex = threading.Lock()

    def __len__(self) -> int:
        return len(self._open) + len(self._locked)

    def _drop_expired_locks(self, now: float) -> None:
        while self._locked:
            key, streak = next(iter(self._locked.items()))
            if streak.locked_until is not None and streak.locked_until > now:
                break
            del self._locked[key]

    def retry_after(self, key: str) -> int | None:
        """Whole seconds until ``key`` may try again, or None when it is not locked."""
        with self._mutex:
            self._drop_expired_locks(self._clock())
            streak = self._locked.get(key)
            if streak is None or streak.locked_until is None:
                return None
            return max(1, math.ceil(streak.locked_until - self._clock()))

    def record_failure(self, key: str) -> None:
        with self._mutex:
            now = self._clock()
            self._drop_expired_locks(now)
            if key in self._locked:
                return  # callers check retry_after first; a locked key is never re-counted
            streak = self._open.pop(key, None) or _Streak()
            streak.failures += 1
            if streak.failures >= self._max_failures:
                streak.locked_until = now + self._lock_seconds
                self._locked[key] = streak
            else:
                self._open[key] = streak
            while len(self) > self._capacity:
                # The key just recorded is never the victim, or a table full of locks would
                # leave every new username uncounted.
                if self._open and next(iter(self._open)) != key:
                    self._open.popitem(last=False)
                elif self._locked and next(iter(self._locked)) != key:
                    self._locked.popitem(last=False)
                else:
                    break  # only reachable with capacity < 1

    def reset(self, key: str) -> None:
        with self._mutex:
            self._open.pop(key, None)
            self._locked.pop(key, None)


def _limiter_key(normalized_username: str) -> str:
    # Valid usernames are at most 32 characters, so truncating at 33 keeps every real key
    # distinct while bounding the memory an attacker can make each key occupy. The API already
    # rejects longer usernames with 422; this guards any other caller of AuthService.
    return normalized_username[: USERNAME_MAX_LENGTH + 1]


# --- access token -------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def issue_access_token(
    *, user_id: str, role: str, secret: bytes, issued_at: int, ttl_seconds: int
) -> str:
    """Compact JWS, HS256 only; the payload carries exactly sub, role, iat and exp (§2.1)."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "role": role, "iat": issued_at, "exp": issued_at + ttl_seconds}
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":")).encode("utf-8"))
        for part in (header, payload)
    )
    signature = hmac.new(secret, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


# --- login --------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    expires_in: int
    user_id: str
    username: str
    role: Literal["teacher", "student"]

    def __repr__(self) -> str:  # the token must not leak through logs or tracebacks
        return f"LoginResult(user_id={self.user_id!r}, role={self.role!r})"


class AuthService:
    def __init__(
        self,
        settings: Settings,
        limiter: LoginRateLimiter,
        clock: Callable[[], float] = time.time,
    ) -> None:
        check_auth_settings(settings)  # never sign with a missing or short key
        self._settings = settings
        self._limiter = limiter
        self._clock = clock

    def login(self, username: str, password: str) -> LoginResult:
        normalized = normalize_username(username)
        key = _limiter_key(normalized)
        retry_after = self._limiter.retry_after(key)
        if retry_after is not None:
            raise LoginRateLimited(retry_after)  # no password check while locked

        account = (
            find_by_username(self._settings.SQLITE_URL, normalized)
            if USERNAME_PATTERN.fullmatch(normalized)
            else None
        )
        # Exactly one slow-hash verification on every path, so response time does not
        # reveal whether the username exists (§1.3.2).
        stored_hash = account.password_hash if account else _timing_dummy_hash()
        password_ok = verify_password(stored_hash, password)
        if account is None or account.disabled_at is not None or not password_ok:
            self._limiter.record_failure(key)
            raise InvalidCredentials()

        self._limiter.reset(key)
        ttl = self._settings.AUTH_ACCESS_TOKEN_TTL_SECONDS
        token = issue_access_token(
            user_id=account.id,
            role=account.role,
            secret=self._settings.AUTH_JWT_SECRET.get_secret_value().encode("utf-8"),
            issued_at=int(self._clock()),
            ttl_seconds=ttl,
        )
        return LoginResult(
            access_token=token,
            expires_in=ttl,
            user_id=account.id,
            username=account.username,
            role=account.role,  # type: ignore[arg-type]  # CHECK constraint on users.role
        )
