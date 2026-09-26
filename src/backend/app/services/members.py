"""Course member management rules of specs/identity-access.md §3.3 (C15).

Callers have already passed the §4.1 checks for a course *teacher* member (the
``course_teacher`` dependency). Every lookup and write here is keyed by ``course_id``.
The API only ever writes ``student`` rows; collaborating teachers are CLI-only (§3.3), and
the repository trigger still refuses a student account as a teacher member (§3.2.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.repositories.accounts import AccountRecord, find_by_username
from app.repositories.courses import (
    MemberRecord,
    add_member,
    get_member,
    list_members,
    remove_member,
)
from app.schemas import contracts
from app.services.access import not_found, role_forbidden
from app.services.auth import normalize_username

# Generated contract DTOs (not yet re-exported by app.schemas.contracts; see handoff C15).
CourseMember = contracts._module.CourseMember
MemberAdd = contracts._module.MemberAdd


@dataclass(frozen=True)
class AddResult:
    member: CourseMember
    created: bool


def _wire(row: MemberRecord) -> CourseMember:
    return CourseMember(
        user_id=row.user_id,
        username=row.username,
        role=contracts.Role(row.role),
        created_at=row.created_at,
    )


def list_course_members(sqlite_url: str, course_id: str) -> list[CourseMember]:
    return [_wire(row) for row in list_members(sqlite_url, course_id)]


def add_student_member(
    sqlite_url: str, course_id: str, actor: AccountRecord, username: str
) -> AddResult:
    """Add ``username`` as a student; an existing member row (any role) is returned as is.

    Unknown and disabled accounts share one 404 so the response does not reveal which.
    """
    account = find_by_username(sqlite_url, normalize_username(username))
    if account is None or account.disabled_at is not None:
        raise not_found()
    row, created = add_member(
        sqlite_url, course_id=course_id, user_id=account.id, role="student", added_by=actor.id
    )
    return AddResult(_wire(row), created)


def remove_student_member(sqlite_url: str, course_id: str, user_id: str) -> None:
    """Remove a student member; teacher members (including the caller) are refused."""
    member = get_member(sqlite_url, course_id, user_id)
    if member is None:
        raise not_found()
    if member.role != "student":
        raise role_forbidden()
    if not remove_member(sqlite_url, course_id, user_id):
        raise not_found()  # removed concurrently between the check and the delete
