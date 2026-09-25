"""Course visibility and contract projection from identity and repository records."""

from app.repositories.accounts import AccountRecord
from app.repositories.courses import CourseRecord, create_course, list_member_courses
from app.schemas.contracts import Course, CourseStatus, Role


def _status(row: CourseRecord) -> CourseStatus:
    if row.published_version_id is None:
        return CourseStatus.draft
    if row.draft_revision == row.published_from_revision:
        return CourseStatus.published
    return CourseStatus.revising


def _wire(row: CourseRecord, role: str) -> Course:
    return Course(
        id=row.id,
        name=row.name,
        description=row.description,
        status=_status(row),
        my_role=Role(role),
        teacher_id=row.teacher_id,
        published_version=row.published_version,
        created_at=row.created_at,
    )


def list_courses(sqlite_url: str, user: AccountRecord) -> list[Course]:
    rows = list_member_courses(sqlite_url, user.id)
    return [
        _wire(row, role)
        for row, role in rows
        if role != "student" or row.published_version is not None
    ]


def create_new_course(
    sqlite_url: str, user: AccountRecord, *, name: str, description: str | None
) -> Course:
    row = create_course(sqlite_url, name=name, description=description, creator_id=user.id)
    return _wire(row, "teacher")
