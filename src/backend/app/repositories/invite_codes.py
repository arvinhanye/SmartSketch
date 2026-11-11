"""SQLite operations for permanent invite-code history (migration 020).

The service makes authorization and membership decisions while this transaction owns the
write lock. Rotation, authorization changes and joining therefore have one database order.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3

from app.repositories.courses import CourseRecord
from app.repositories.sqlite import connect


@dataclass(frozen=True, repr=False)
class InviteCodeRecord:
    code: str
    rotated_at: str


class InviteTransaction:
    def __init__(self, database: sqlite3.Connection) -> None:
        self._database = database

    def account_state(self, user_id: str) -> tuple[str, str | None] | None:
        return self._database.execute(
            "SELECT role, disabled_at FROM users WHERE id = ?", (user_id,),
        ).fetchone()

    def member_role(self, course_id: str, user_id: str) -> str | None:
        row = self._database.execute(
            "SELECT role FROM course_members WHERE course_id = ? AND user_id = ?",
            (course_id, user_id),
        ).fetchone()
        return row[0] if row else None

    def active_code(self, course_id: str) -> InviteCodeRecord | None:
        row = self._database.execute(
            "SELECT code, rotated_at FROM course_invite_codes "
            "WHERE course_id = ? AND revoked_at IS NULL", (course_id,),
        ).fetchone()
        return InviteCodeRecord(*row) if row else None

    def revoke_code(self, course_id: str) -> None:
        self._database.execute(
            "UPDATE course_invite_codes SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE course_id = ? AND revoked_at IS NULL", (course_id,),
        )

    def insert_code(self, course_id: str, code: str) -> InviteCodeRecord | None:
        # Only a collision with any historical code is retryable. FK, shape and active-code
        # constraint failures remain errors, so they cannot be mistaken for random collisions.
        cursor = self._database.execute(
            "INSERT INTO course_invite_codes (course_id, code) VALUES (?, ?) "
            "ON CONFLICT (code) DO NOTHING", (course_id, code),
        )
        return self.active_code(course_id) if cursor.rowcount == 1 else None

    def course_for_code(self, code: str) -> CourseRecord | None:
        row = self._database.execute(
            "SELECT c.id, c.name, c.description, c.teacher_id, c.created_at, "
            "c.published_version_id, c.published_version, c.draft_revision, "
            "c.published_from_revision FROM course_invite_codes AS i "
            "JOIN courses AS c ON c.id = i.course_id WHERE i.code = ? AND i.revoked_at IS NULL",
            (code,),
        ).fetchone()
        return CourseRecord(*row) if row else None

    def add_student(self, course_id: str, user_id: str) -> None:
        self._database.execute(
            "INSERT INTO course_members (course_id, user_id, role, added_by) "
            "VALUES (?, ?, 'student', ?)", (course_id, user_id, user_id),
        )

    def published_kp_count(self, course_id: str) -> int | None:
        row = self._database.execute(
            "SELECT v.node_count FROM courses AS c JOIN graph_versions AS v "
            "ON v.version_id = c.published_version_id AND v.course_id = c.id WHERE c.id = ?",
            (course_id,),
        ).fetchone()
        return row[0] if row else None


@contextmanager
def transaction(sqlite_url: str) -> Iterator[InviteTransaction]:
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            yield InviteTransaction(database)
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
