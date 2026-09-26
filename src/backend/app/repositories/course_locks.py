"""§8.5 课程写锁（F13；ADR-012 V4）：与任务租约同构的 SQLite 行锁。

- ``try_acquire``：一条 ``INSERT … ON CONFLICT(course_id) DO UPDATE … WHERE expires_at < unixepoch()
  RETURNING``；锁空闲或已过期时拿到，否则返回 ``None``。
- ``acquire``：有界等待（``COURSE_LOCK_WAIT_SECONDS``），超时返回 ``None``，由调用方决定 409 ``COURSE_BUSY``
  或释放任务退避。
- ``renew``/``release`` 都带令牌条件；过期的锁可被他人取走，旧持有者的续约与释放影响 0 行。

时间一律由 SQLite ``unixepoch()`` 计算，与迁移器的活锁检查 ``expires_at >= unixepoch()`` 一致。
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from app.repositories.sqlite import connect

__all__ = ["CourseLock", "acquire", "held", "release", "renew", "try_acquire"]


@dataclass(frozen=True)
class CourseLock:
    course_id: str
    holder: str
    token: str
    expires_at: int


def _check(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _seconds(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be an int >= 1")
    return value


def try_acquire(sqlite_url: str, course_id: str, *, holder: str, lease_seconds: int) -> CourseLock | None:
    _check("course_id", course_id)
    _check("holder", holder)
    _seconds("lease_seconds", lease_seconds)
    token = secrets.token_hex(16)
    with connect(sqlite_url) as database:
        row = database.execute(
            """INSERT INTO course_locks (course_id, holder, token, expires_at)
               VALUES (:course, :holder, :token, unixepoch() + :seconds)
               ON CONFLICT(course_id) DO UPDATE
                   SET holder = excluded.holder, token = excluded.token, expires_at = excluded.expires_at
                   WHERE course_locks.expires_at < unixepoch()
               RETURNING token, expires_at""",
            {"course": course_id, "holder": holder, "token": token, "seconds": lease_seconds},
        ).fetchone()
    if row is None or row[0] != token:
        return None
    return CourseLock(course_id, holder, token, row[1])


def acquire(
    sqlite_url: str,
    course_id: str,
    *,
    holder: str,
    lease_seconds: int,
    wait_seconds: float,
    poll_seconds: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> CourseLock | None:
    """有界等待取锁；``wait_seconds = 0`` 只试一次。"""
    if not isinstance(wait_seconds, (int, float)) or wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    deadline = clock() + wait_seconds
    while True:
        lock = try_acquire(sqlite_url, course_id, holder=holder, lease_seconds=lease_seconds)
        if lock is not None or clock() >= deadline:
            return lock
        sleep(min(poll_seconds, max(0.0, deadline - clock())))


def renew(sqlite_url: str, lock: CourseLock, *, lease_seconds: int) -> bool:
    _seconds("lease_seconds", lease_seconds)
    with connect(sqlite_url) as database:
        changed = database.execute(
            "UPDATE course_locks SET expires_at = unixepoch() + ? WHERE course_id = ? AND token = ?",
            (lease_seconds, lock.course_id, lock.token),
        ).rowcount
    return changed == 1


def release(sqlite_url: str, lock: CourseLock) -> bool:
    with connect(sqlite_url) as database:
        changed = database.execute(
            "DELETE FROM course_locks WHERE course_id = ? AND token = ?", (lock.course_id, lock.token)
        ).rowcount
    return changed == 1


@contextmanager
def held(sqlite_url: str, lock: CourseLock, *, lease_seconds: int | None = None) -> Iterator[CourseLock]:
    """持有已取得的锁直到块结束，无论成功与否都释放。给出 ``lease_seconds`` 时每 ``L/3`` 续约一次（§8.5）。"""
    stop = threading.Event()
    thread = None
    if lease_seconds is not None:
        _seconds("lease_seconds", lease_seconds)

        def beat() -> None:
            while not stop.wait(lease_seconds / 3):
                try:
                    if not renew(sqlite_url, lock, lease_seconds=lease_seconds):
                        return  # 已被他人取走：写入方的令牌条件与守卫节点仍保证正确性
                except Exception:  # SQLite 暂时不可用：下个周期再试
                    continue

        thread = threading.Thread(target=beat, name=f"course-lock-{lock.course_id}", daemon=True)
        thread.start()
    try:
        yield lock
    finally:
        stop.set()
        if thread is not None:
            thread.join()
        release(sqlite_url, lock)
