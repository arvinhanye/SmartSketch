"""Identity and course access decisions from specs/identity-access.md §2 and §4."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings, check_auth_settings
from app.repositories.accounts import AccountRecord, find_by_id
from app.repositories.courses import CourseRecord, MemberRecord, get_course, get_member
from app.repositories.tasks import find_task_course_id


class AccessDenied(Exception):
    """A public error code; messages do not include credentials or resource identifiers."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


UNAUTHENTICATED = AccessDenied(401, "UNAUTHENTICATED", "请先登录或重新登录")
COURSE_FORBIDDEN = AccessDenied(403, "COURSE_FORBIDDEN", "无权访问该课程")
ROLE_FORBIDDEN = AccessDenied(403, "ROLE_FORBIDDEN", "当前课程角色无权执行此操作")
NOT_FOUND = AccessDenied(404, "NOT_FOUND", "资源不存在")
GRAPH_NOT_PUBLISHED = AccessDenied(404, "GRAPH_NOT_PUBLISHED", "课程图谱尚未发布")


@dataclass(frozen=True)
class CourseAccess:
    user: AccountRecord
    member: MemberRecord
    course: CourseRecord


def _decode_part(part: str) -> dict:
    if (
        not part
        or len(part) > 4096
        or any(
            c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for c in part
        )
    ):
        raise UNAUTHENTICATED
    try:
        raw = base64.b64decode(
            part + "=" * (-len(part) % 4), altchars=b"-_", validate=True
        )
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise UNAUTHENTICATED from None
    if not isinstance(value, dict):
        raise UNAUTHENTICATED
    return value


class AccessService:
    def __init__(
        self, settings: Settings, clock: Callable[[], float] = time.time
    ) -> None:
        check_auth_settings(settings)
        self._settings = settings
        self._clock = clock

    def authenticate(self, token: str) -> AccountRecord:
        """Verify the C13 compact HS256 token and reload account state."""
        if not token or len(token) > 8192:
            raise UNAUTHENTICATED
        parts = token.split(".")
        if len(parts) != 3:
            raise UNAUTHENTICATED
        header, payload, signature = parts
        if _decode_part(header) != {"alg": "HS256", "typ": "JWT"}:
            raise UNAUTHENTICATED
        claims = _decode_part(payload)
        if set(claims) != {"sub", "role", "iat", "exp"}:
            raise UNAUTHENTICATED
        if (
            not isinstance(claims["sub"], str)
            or not claims["sub"]
            or claims["role"] not in ("teacher", "student")
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
        ):
            raise UNAUTHENTICATED
        now = self._clock()
        if (
            claims["iat"] > now
            or claims["exp"] <= now
            or claims["exp"] <= claims["iat"]
        ):
            raise UNAUTHENTICATED
        signed = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(
            self._settings.AUTH_JWT_SECRET.get_secret_value().encode("utf-8"),
            signed,
            hashlib.sha256,
        ).digest()
        try:
            supplied = base64.b64decode(
                signature + "=" * (-len(signature) % 4), altchars=b"-_", validate=True
            )
        except (ValueError, binascii.Error):
            raise UNAUTHENTICATED from None
        if not hmac.compare_digest(supplied, expected):
            raise UNAUTHENTICATED
        account = find_by_id(self._settings.SQLITE_URL, claims["sub"])
        if account is None or account.disabled_at is not None:
            raise UNAUTHENTICATED
        return account

    def require_course(
        self,
        user: AccountRecord,
        course_id: str,
        *,
        role: str | None = None,
        student_published: bool = False,
    ) -> CourseAccess:
        member = get_member(self._settings.SQLITE_URL, course_id, user.id)
        if member is None:
            raise COURSE_FORBIDDEN
        if role is not None and member.role != role:
            raise ROLE_FORBIDDEN
        course = get_course(self._settings.SQLITE_URL, course_id)
        if course is None:
            raise COURSE_FORBIDDEN
        if (
            student_published
            and member.role == "student"
            and course.published_version is None
        ):
            raise GRAPH_NOT_PUBLISHED
        return CourseAccess(user, member, course)

    def require_task(self, user: AccountRecord, task_id: str) -> CourseAccess:
        course_id = find_task_course_id(self._settings.SQLITE_URL, task_id)
        if course_id is None:
            raise NOT_FOUND
        try:
            return self.require_course(user, course_id, role="teacher")
        except AccessDenied as error:
            if error.code == "COURSE_FORBIDDEN":
                raise NOT_FOUND from None
            raise
