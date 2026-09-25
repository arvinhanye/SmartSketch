"""Persistence for courses and course members (migration 003, specs/identity-access.md §3).

Every member read and write is keyed by ``course_id`` first. The in-course role stored here
is the only input to course authorization; ``users.role`` (account type) only limits who may
hold a ``teacher`` member row (IAM-24, enforced by a trigger so every writer is covered).
Authorization, the §4.4 visibility filter and the HTTP rules of §3.3 live in services
(C03/C04/C15). There is deliberately no course deletion: the spec has no such operation.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from app.repositories.sqlite import connect

_TEACHER_ACCOUNT_REQUIRED = "teacher member requires a teacher account"


class UnknownUser(ValueError):
    """A member, creator or ``added_by`` id is not in ``users``."""


class UnknownCourse(ValueError):
    """The ``course_id`` is not in ``courses``."""


class RoleNotAllowed(ValueError):
    """A student account was about to become a ``teacher`` member (IAM-24)."""


@dataclass(frozen=True)
class CourseRecord:
    id: str
    name: str
    description: str | None
    teacher_id: str
    created_at: str
    published_version_id: str | None
    published_version: int | None
    draft_revision: int
    published_from_revision: int | None


@dataclass(frozen=True)
class MemberRecord:
    course_id: str
    user_id: str
    username: str
    role: str
    added_by: str | None
    created_at: str


_COURSE_COLUMNS = (
    "c.id, c.name, c.description, c.teacher_id, c.created_at, c.published_version_id, "
    "c.published_version, c.draft_revision, c.published_from_revision"
)
_MEMBER_SELECT = (
    "SELECT m.course_id, m.user_id, u.username, m.role, m.added_by, m.created_at "
    "FROM course_members AS m JOIN users AS u ON u.id = m.user_id"
)


def _exists(database: sqlite3.Connection, table: str, row_id: str | None) -> bool:
    return row_id is None or database.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)
    ).fetchone() is not None


def _classify(
    database: sqlite3.Connection,
    exc: sqlite3.IntegrityError,
    *,
    course_id: str | None,
    user_ids: tuple[str | None, ...],
) -> ValueError:
    """Turn a rolled-back constraint failure into a specific error (SQLite names no FK)."""
    if _TEACHER_ACCOUNT_REQUIRED in str(exc):
        return RoleNotAllowed("a student account cannot be a teacher member")
    if course_id is not None and not _exists(database, "courses", course_id):
        return UnknownCourse(course_id)
    for user_id in user_ids:
        if not _exists(database, "users", user_id):
            return UnknownUser(user_id)
    return ValueError("row rejected by the courses/course_members constraints")


def _member(database: sqlite3.Connection, course_id: str, user_id: str) -> MemberRecord | None:
    row = database.execute(
        f"{_MEMBER_SELECT} WHERE m.course_id = ? AND m.user_id = ?", (course_id, user_id)
    ).fetchone()
    return MemberRecord(*row) if row else None


def create_course(
    sqlite_url: str, *, name: str, description: str | None, creator_id: str
) -> CourseRecord:
    """Insert a course and its creator's ``teacher`` member row in one transaction.

    Account-type checks belong to the service (C04); a student creator still fails here,
    atomically, because the member row is refused (RoleNotAllowed) and nothing is kept.
    """
    course_id = uuid.uuid4().hex
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            database.execute(
                "INSERT INTO courses (id, name, description, teacher_id) VALUES (?, ?, ?, ?)",
                (course_id, name, description, creator_id),
            )
            database.execute(
                "INSERT INTO course_members (course_id, user_id, role, added_by) "
                "VALUES (?, ?, 'teacher', ?)",
                (course_id, creator_id, creator_id),
            )
        except sqlite3.IntegrityError as exc:
            database.execute("ROLLBACK")
            raise _classify(database, exc, course_id=None, user_ids=(creator_id,)) from None
        except BaseException:
            database.execute("ROLLBACK")
            raise
        database.execute("COMMIT")
        row = database.execute(
            f"SELECT {_COURSE_COLUMNS} FROM courses AS c WHERE c.id = ?", (course_id,)
        ).fetchone()
    return CourseRecord(*row)


def get_course(sqlite_url: str, course_id: str) -> CourseRecord | None:
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COURSE_COLUMNS} FROM courses AS c WHERE c.id = ?", (course_id,)
        ).fetchone()
    return CourseRecord(*row) if row else None


def list_member_courses(sqlite_url: str, user_id: str) -> list[tuple[CourseRecord, str]]:
    """Every course ``user_id`` is a member of, with that user's in-course role.

    Unfiltered: hiding never-published courses from student members (§4.4) is C04's rule.
    """
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_COURSE_COLUMNS}, m.role FROM course_members AS m "
            "JOIN courses AS c ON c.id = m.course_id WHERE m.user_id = ? "
            "ORDER BY c.created_at, c.id",
            (user_id,),
        ).fetchall()
    return [(CourseRecord(*row[:-1]), row[-1]) for row in rows]


def get_member(sqlite_url: str, course_id: str, user_id: str) -> MemberRecord | None:
    """The member row of ``user_id`` in ``course_id`` only; None if not a member there."""
    with connect(sqlite_url) as database:
        return _member(database, course_id, user_id)


def list_members(sqlite_url: str, course_id: str) -> list[MemberRecord]:
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"{_MEMBER_SELECT} WHERE m.course_id = ? ORDER BY m.created_at, m.rowid",
            (course_id,),
        ).fetchall()
    return [MemberRecord(*row) for row in rows]


def add_member(
    sqlite_url: str, *, course_id: str, user_id: str, role: str, added_by: str | None
) -> tuple[MemberRecord, bool]:
    """Add ``user_id`` to ``course_id``; return ``(row, created)``.

    An existing member row is returned unchanged (never re-roled, §3.3 / IAM-8). Disabled
    accounts are not refused here: the add-by-username rule of §3.3 is C15's.
    """
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            cursor = database.execute(
                "INSERT INTO course_members (course_id, user_id, role, added_by) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (course_id, user_id) DO NOTHING",
                (course_id, user_id, role, added_by),
            )
            created = cursor.rowcount == 1
            member = _member(database, course_id, user_id)
        except sqlite3.IntegrityError as exc:
            database.execute("ROLLBACK")
            raise _classify(
                database, exc, course_id=course_id, user_ids=(user_id, added_by)
            ) from None
        except BaseException:
            database.execute("ROLLBACK")
            raise
        database.execute("COMMIT")
    assert member is not None
    return member, created


def remove_member(sqlite_url: str, course_id: str, user_id: str) -> bool:
    """Delete the member row in ``course_id`` only; False if there was none.

    Which members may be removed (students only via API, §3.3; at least one teacher,
    §3.2.4) is decided by the caller. Progress and chat rows are not touched.
    """
    with connect(sqlite_url) as database:
        cursor = database.execute(
            "DELETE FROM course_members WHERE course_id = ? AND user_id = ?", (course_id, user_id)
        )
    return cursor.rowcount == 1
