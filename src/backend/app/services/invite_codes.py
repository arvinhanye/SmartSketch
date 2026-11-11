"""ADR-096 invite-code authorization, generation, joining and process-local throttling."""

from collections import deque
from collections.abc import Callable
import math
import secrets
import threading
import time

from app.repositories import invite_codes as repository
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import Course, InviteCodeResponse
from app.services.access import AccessDenied, course_forbidden, role_forbidden, unauthenticated
from app.services.courses import course_to_contract


INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GENERATION_ATTEMPTS = 16
USER_ATTEMPTS = 10
IP_ATTEMPTS = 60
WINDOW_SECONDS = 60
LIMITER_CAPACITY = 4096


class InviteRateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Invitation attempts are temporarily limited")
        self.retry_after = retry_after


class InviteRateLimiter:
    """Separate user and IP sliding windows, checked and reserved under one mutex.

    Buckets count all admitted attempts, including successful and malformed submissions.
    A denied attempt creates no buckets and extends no window. Capacity exhaustion fails
    closed; live buckets are never evicted to make room for a new identity.
    """

    def __init__(
        self, clock: Callable[[], float] = time.monotonic, *, capacity: int = LIMITER_CAPACITY,
    ) -> None:
        if capacity < 2:
            raise ValueError("Invitation limiter needs room for both user and IP buckets")
        self._clock = clock
        self._capacity = capacity
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._mutex = threading.Lock()

    def acquire(self, user_id: str, ip: str) -> int | None:
        with self._mutex:
            now = self._clock()
            for key, attempts in list(self._buckets.items()):
                while attempts and attempts[0] <= now - WINDOW_SECONDS:
                    attempts.popleft()
                if not attempts:
                    del self._buckets[key]
            keys = (("user", user_id), ("ip", ip))
            waits = [
                attempts[0] + WINDOW_SECONDS - now
                for key, limit in zip(keys, (USER_ATTEMPTS, IP_ATTEMPTS))
                if (attempts := self._buckets.get(key)) is not None and len(attempts) >= limit
            ]
            if waits:
                return max(1, math.ceil(max(waits)))
            missing = sum(key not in self._buckets for key in keys)
            if len(self._buckets) + missing > self._capacity:
                # Wait until all current buckets could expire; this bounded, conservative
                # retry avoids promising a slot freed only by one of this caller's own keys.
                return max(1, math.ceil(max(
                    attempts[-1] + WINDOW_SECONDS - now for attempts in self._buckets.values()
                )))
            for key in keys:
                self._buckets.setdefault(key, deque()).append(now)
            return None


def reserve_join_attempt(user: AccountRecord, ip: str, limiter: InviteRateLimiter) -> None:
    if user.role != "student":
        raise role_forbidden()
    retry_after = limiter.acquire(user.id, ip)
    if retry_after is not None:
        raise InviteRateLimited(retry_after)


def generate_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(6))


def _account_role(transaction: repository.InviteTransaction, user_id: str) -> str:
    state = transaction.account_state(user_id)
    if state is None or state[1] is not None:
        raise unauthenticated()
    return state[0]


def get_course_invite_code(
    sqlite_url: str, user_id: str, course_id: str, *, rotate: bool = False,
) -> InviteCodeResponse:
    with repository.transaction(sqlite_url) as transaction:
        _account_role(transaction, user_id)
        role = transaction.member_role(course_id, user_id)
        if role is None:
            raise course_forbidden()
        if role != "teacher":
            raise role_forbidden()
        current = transaction.active_code(course_id)
        if current is not None and not rotate:
            return InviteCodeResponse(code=current.code, rotated_at=current.rotated_at)
        if rotate:
            transaction.revoke_code(course_id)
        for _ in range(GENERATION_ATTEMPTS):
            created = transaction.insert_code(course_id, generate_code())
            if created is not None:
                return InviteCodeResponse(code=created.code, rotated_at=created.rotated_at)
        # Raising inside the transaction restores the previous active code after collisions.
        raise AccessDenied(500, "INTERNAL_ERROR", "暂时无法生成邀请码，请稍后重试")


def join_course(sqlite_url: str, user_id: str, code: str) -> Course:
    with repository.transaction(sqlite_url) as transaction:
        if _account_role(transaction, user_id) != "student":
            raise role_forbidden()
        course = transaction.course_for_code(code)
        if course is None:
            raise AccessDenied(404, "INVITE_CODE_INVALID", "邀请码不存在或已失效")
        if transaction.member_role(course.id, user_id) is not None:
            raise AccessDenied(409, "ALREADY_MEMBER", "你已在该课程中")
        transaction.add_student(course.id, user_id)
        # This receipt may describe a draft. List/detail/graph retain their existing
        # publication checks; joining does not authorize reading unpublished graph data.
        return course_to_contract(course, "student", transaction.published_kp_count(course.id))
