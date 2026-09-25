"""C02: course and course-member repository (specs/identity-access.md §3, ADR-013).

Covers the C02 acceptance (members unique per course; one user's roles in different courses
are independent; foreign keys correct and enforced) and IAM-24 (a student account can never
hold a ``teacher`` member row, whichever code path writes it). Authorization, the student
visibility filter of §4.4 and the HTTP semantics of §3.3 belong to C03/C04/C15.
"""

import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.repositories import courses as repo
from app.repositories.accounts import insert_account
from app.repositories.courses import (
    RoleNotAllowed,
    UnknownCourse,
    UnknownUser,
    add_member,
    create_course,
    get_course,
    get_member,
    list_member_courses,
    list_members,
    remove_member,
)
from app.repositories.sqlite import connect, migrate

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "backend" / "migrations"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _new_id() -> str:
    return uuid.uuid4().hex


def _dump(url: str) -> dict[str, list[tuple]]:
    with connect(url) as database:
        return {
            table: database.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in ("users", "courses", "course_members")
        }


@pytest.fixture
def db_url(tmp_path):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    return url


@pytest.fixture
def make_user(db_url):
    def _make(username: str, role: str) -> str:
        user_id = _new_id()
        insert_account(
            db_url, account_id=user_id, username=username, password_hash=VALID_HASH, role=role
        )
        return user_id

    return _make


@pytest.fixture
def people(make_user):
    return {
        "teacher": make_user("t_alice", "teacher"),
        "teacher2": make_user("t_bob", "teacher"),
        "student": make_user("s_carol", "student"),
        "student2": make_user("s_dave", "student"),
    }


# --- migration --------------------------------------------------------------------------


def test_migration_adds_course_tables_after_002_and_keeps_a_restorable_backup(tmp_path):
    path = tmp_path / "state.sqlite3"
    earlier = tmp_path / "up-to-002"
    earlier.mkdir()
    for name in ("001_base.sql", "002_accounts.sql"):
        shutil.copyfile(MIGRATIONS / name, earlier / name)
    assert migrate(_url(path), earlier) == ["001", "002"]
    user_id = _new_id()
    insert_account(
        _url(path), account_id=user_id, username="t_keep", password_hash=VALID_HASH, role="teacher"
    )

    assert migrate(_url(path)) == ["003"]
    assert migrate(_url(path)) == []

    with connect(_url(path)) as database:
        assert database.execute("SELECT id FROM users").fetchall() == [(user_id,)]
        assert database.execute(
            "SELECT version, filename FROM schema_migrations WHERE version = '003'"
        ).fetchone() == ("003", "003_courses.sql")
    backup = next((tmp_path / "backups").glob("*-before-003.sqlite"))
    with sqlite3.connect(backup) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copy.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('courses', 'course_members')"
        ).fetchall() == []
        assert copy.execute("SELECT id FROM users").fetchall() == [(user_id,)]


def test_course_tables_have_the_specified_columns(db_url):
    with connect(db_url) as database:
        course_columns = {row[1] for row in database.execute("PRAGMA table_info(courses)")}
        member_info = database.execute("PRAGMA table_info(course_members)").fetchall()
    member_columns = {row[1] for row in member_info}
    member_pk = [row[1] for row in sorted(member_info, key=lambda r: r[5]) if row[5]]
    # Course/CourseCreate (api.v1.yaml) + teacher-review-publish.md「courses 增加」
    assert course_columns == {
        "id", "name", "description", "teacher_id", "created_at",
        "published_version_id", "published_version", "draft_revision", "published_from_revision",
    }
    # identity-access.md §3.1
    assert member_columns == {"course_id", "user_id", "role", "added_by", "created_at"}
    assert member_pk == ["course_id", "user_id"]


def test_foreign_keys_point_at_users_and_courses_and_are_enforced(db_url):
    with connect(db_url) as database:
        assert database.execute("PRAGMA foreign_keys").fetchone() == (1,)
        member_fks = {
            (row[3], row[2], row[4], row[6])  # from, table, to, on_delete
            for row in database.execute("PRAGMA foreign_key_list(course_members)")
        }
        course_fks = {
            (row[3], row[2], row[4], row[6])
            for row in database.execute("PRAGMA foreign_key_list(courses)")
        }
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    assert member_fks == {
        ("course_id", "courses", "id", "NO ACTION"),
        ("user_id", "users", "id", "NO ACTION"),
        ("added_by", "users", "id", "NO ACTION"),
    }
    assert course_fks == {("teacher_id", "users", "id", "NO ACTION")}


# --- courses ----------------------------------------------------------------------------


def test_create_course_writes_course_and_creator_teacher_membership(db_url, people):
    course = create_course(db_url, name="数据结构", description=None, creator_id=people["teacher"])

    assert len(course.id) == 32 and course.id != people["teacher"]
    assert (course.name, course.description, course.teacher_id) == (
        "数据结构", None, people["teacher"]
    )
    assert course.published_version_id is None and course.published_version is None
    assert course.draft_revision == 0 and course.published_from_revision is None
    assert course.created_at.endswith("Z")
    assert get_course(db_url, course.id) == course

    member = get_member(db_url, course.id, people["teacher"])
    assert (member.role, member.added_by, member.username) == ("teacher", people["teacher"], "t_alice")

    other = create_course(db_url, name="数据结构", description="同名课程", creator_id=people["teacher"])
    assert other.id != course.id


def test_create_course_is_atomic_when_the_member_row_is_rejected(db_url, people):
    before = _dump(db_url)
    with pytest.raises(RoleNotAllowed):
        create_course(db_url, name="学生建课", description=None, creator_id=people["student"])
    with pytest.raises(UnknownUser):
        create_course(db_url, name="幽灵建课", description=None, creator_id=_new_id())
    assert _dump(db_url) == before


@pytest.mark.parametrize(
    ("name", "description"),
    [("", None), ("x" * 121, None), ("ok", "d" * 1001)],
)
def test_create_course_rejects_out_of_range_fields(db_url, people, name, description):
    before = _dump(db_url)
    with pytest.raises(ValueError):
        create_course(db_url, name=name, description=description, creator_id=people["teacher"])
    assert _dump(db_url) == before


def test_create_course_accepts_boundary_lengths(db_url, people):
    course = create_course(
        db_url, name="名" * 120, description="述" * 1000, creator_id=people["teacher"]
    )
    assert len(course.name) == 120 and len(course.description) == 1000


def test_get_course_unknown_returns_none(db_url):
    assert get_course(db_url, _new_id()) is None


def test_publish_pointer_and_version_number_are_set_together(db_url, people):
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    with connect(db_url) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "UPDATE courses SET published_version_id = 'v1' WHERE id = ?", (course.id,)
            )
        database.execute(
            "UPDATE courses SET published_version_id = 'v1', published_version = 1 WHERE id = ?",
            (course.id,),
        )
    assert get_course(db_url, course.id).published_version == 1


# --- members ----------------------------------------------------------------------------


def test_member_is_unique_per_course_and_readding_changes_nothing(db_url, people):
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    first, created = add_member(
        db_url, course_id=course.id, user_id=people["student"], role="student",
        added_by=people["teacher"],
    )
    assert created is True and first.role == "student"

    again, created = add_member(
        db_url, course_id=course.id, user_id=people["student"], role="student", added_by=None
    )
    assert created is False and again == first  # same added_by / created_at: row untouched

    # IAM-8 at the repository: re-adding a teacher member as student keeps them a teacher
    kept, created = add_member(
        db_url, course_id=course.id, user_id=people["teacher"], role="student",
        added_by=people["teacher"],
    )
    assert created is False and kept.role == "teacher"

    with connect(db_url) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM course_members WHERE course_id = ?", (course.id,)
        ).fetchone() == (2,)
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "INSERT INTO course_members (course_id, user_id, role) VALUES (?, ?, 'student')",
                (course.id, people["student"]),
            )


def test_one_user_holds_independent_roles_in_different_courses(db_url, people):
    # IAM-5 data shape: teacher account U teaches A and is a student member of B
    a = create_course(db_url, name="A", description=None, creator_id=people["teacher"])
    b = create_course(db_url, name="B", description=None, creator_id=people["teacher2"])
    add_member(db_url, course_id=b.id, user_id=people["teacher"], role="student",
               added_by=people["teacher2"])

    assert get_member(db_url, a.id, people["teacher"]).role == "teacher"
    assert get_member(db_url, b.id, people["teacher"]).role == "student"
    assert {(c.id, role) for c, role in list_member_courses(db_url, people["teacher"])} == {
        (a.id, "teacher"), (b.id, "student")
    }

    assert remove_member(db_url, b.id, people["teacher"]) is True
    assert get_member(db_url, a.id, people["teacher"]).role == "teacher"
    assert get_member(db_url, b.id, people["teacher"]) is None


def test_reads_and_deletes_are_scoped_by_course(db_url, people):
    a = create_course(db_url, name="A", description=None, creator_id=people["teacher"])
    b = create_course(db_url, name="B", description=None, creator_id=people["teacher2"])
    add_member(db_url, course_id=a.id, user_id=people["student"], role="student",
               added_by=people["teacher"])
    before = _dump(db_url)

    assert get_member(db_url, b.id, people["student"]) is None
    assert [m.user_id for m in list_members(db_url, b.id)] == [people["teacher2"]]
    assert remove_member(db_url, b.id, people["student"]) is False
    assert _dump(db_url) == before
    assert list_member_courses(db_url, people["student2"]) == []
    assert list_members(db_url, _new_id()) == []


def test_list_members_returns_usernames_in_join_order(db_url, people):
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    for key in ("student2", "student"):
        add_member(db_url, course_id=course.id, user_id=people[key], role="student",
                   added_by=people["teacher"])
    members = list_members(db_url, course.id)
    assert [(m.username, m.role) for m in members] == [
        ("t_alice", "teacher"), ("s_dave", "student"), ("s_carol", "student")
    ]
    assert all(m.course_id == course.id for m in members)


def test_removed_member_can_rejoin(db_url, people):
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    add_member(db_url, course_id=course.id, user_id=people["student"], role="student",
               added_by=people["teacher"])
    assert remove_member(db_url, course.id, people["student"]) is True
    assert remove_member(db_url, course.id, people["student"]) is False
    _, created = add_member(db_url, course_id=course.id, user_id=people["student"],
                            role="student", added_by=None)
    assert created is True


def test_teacher_account_may_be_added_as_teacher_member(db_url, people):
    # collaborating teacher via CLI: added_by is NULL (§3.1)
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    member, created = add_member(db_url, course_id=course.id, user_id=people["teacher2"],
                                 role="teacher", added_by=None)
    assert created is True and (member.role, member.added_by) == ("teacher", None)


# --- failure paths ----------------------------------------------------------------------


def test_student_account_can_never_be_a_teacher_member(db_url, people):
    """IAM-24: rejected through the repository and through raw SQL (e.g. a CLI), no change."""
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    add_member(db_url, course_id=course.id, user_id=people["student2"], role="student",
               added_by=people["teacher"])
    before = _dump(db_url)

    with pytest.raises(RoleNotAllowed):
        add_member(db_url, course_id=course.id, user_id=people["student"], role="teacher",
                   added_by=None)
    with connect(db_url) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "INSERT INTO course_members (course_id, user_id, role) VALUES (?, ?, 'teacher')",
                (course.id, people["student"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "UPDATE course_members SET role = 'teacher' WHERE course_id = ? AND user_id = ?",
                (course.id, people["student2"]),
            )
    assert _dump(db_url) == before


def test_unknown_user_course_or_adder_is_rejected_without_change(db_url, people):
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    before = _dump(db_url)

    with pytest.raises(UnknownUser):
        add_member(db_url, course_id=course.id, user_id=_new_id(), role="student", added_by=None)
    with pytest.raises(UnknownUser):
        add_member(db_url, course_id=course.id, user_id=_new_id(), role="teacher", added_by=None)
    with pytest.raises(UnknownCourse):
        add_member(db_url, course_id=_new_id(), user_id=people["student"], role="student",
                   added_by=None)
    with pytest.raises(UnknownUser):
        add_member(db_url, course_id=course.id, user_id=people["student"], role="student",
                   added_by=_new_id())
    with pytest.raises(ValueError):
        add_member(db_url, course_id=course.id, user_id=people["student"], role="admin",
                   added_by=None)
    assert _dump(db_url) == before


def test_courses_and_users_with_members_cannot_be_deleted(db_url, people):
    """No delete API exists (spec); rows referenced by memberships are restricted, not cascaded."""
    course = create_course(db_url, name="课", description=None, creator_id=people["teacher"])
    add_member(db_url, course_id=course.id, user_id=people["student"], role="student",
               added_by=people["teacher2"])
    before = _dump(db_url)
    with connect(db_url) as database:
        for statement, value in (
            ("DELETE FROM courses WHERE id = ?", course.id),
            ("DELETE FROM users WHERE id = ?", people["student"]),
            ("DELETE FROM users WHERE id = ?", people["teacher2"]),  # only referenced as added_by
        ):
            with pytest.raises(sqlite3.IntegrityError):
                database.execute(statement, (value,))
    assert _dump(db_url) == before


def test_module_exposes_no_course_deletion():
    assert not hasattr(repo, "delete_course")
