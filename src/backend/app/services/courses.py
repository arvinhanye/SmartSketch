"""Course visibility and contract projection from identity and repository records."""

from app.repositories.accounts import AccountRecord
from app.repositories.courses import CourseRecord, create_course, list_member_courses, published_kp_counts
from app.services.access import CourseAccess
from app.schemas.contracts import Course, CourseStatus, Role


def _status(row: CourseRecord) -> CourseStatus:
    if row.published_version_id is None:
        return CourseStatus.draft
    if row.draft_revision == row.published_from_revision:
        return CourseStatus.published
    return CourseStatus.revising


def _wire(row: CourseRecord, role: str, kp_count: int | None = None) -> Course:
    return Course(
        id=row.id,
        name=row.name,
        description=row.description,
        status=_status(row),
        my_role=Role(role),
        teacher_id=row.teacher_id,
        kp_count=kp_count,
        published_version=row.published_version,
        created_at=row.created_at,
    )


def list_courses(sqlite_url: str, user: AccountRecord) -> list[Course]:
    rows = [
        (row, role) for row, role in list_member_courses(sqlite_url, user.id)
        if role != "student" or row.published_version is not None
    ]
    counts = published_kp_counts(sqlite_url, [row.id for row, _ in rows])
    return [_wire(row, role, counts.get(row.id)) for row, role in rows]


def course_detail(sqlite_url: str, access: CourseAccess) -> Course:
    counts = published_kp_counts(sqlite_url, [access.course.id])
    return _wire(access.course, access.member.role, counts.get(access.course.id))


def create_new_course(
    sqlite_url: str, user: AccountRecord, *, name: str, description: str | None
) -> Course:
    row = create_course(sqlite_url, name=name, description=description, creator_id=user.id)
    return _wire(row, "teacher")
