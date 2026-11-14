"""020 keeps revoked codes unavailable without changing existing memberships."""

import sqlite3

import pytest

from app.repositories.accounts import insert_account
from app.repositories.courses import create_course, get_member
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate


@pytest.fixture
def invitation_db(tmp_path):
    url = f"sqlite:///{tmp_path / 'invite.sqlite3'}"
    migrate(url)
    teacher = insert_account(
        url, account_id="a" * 32, username="invite_teacher",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA", role="teacher",
    )
    course = create_course(url, name="Invite migration", description=None, creator_id=teacher.id)
    return url, teacher, course


def test_active_course_and_historical_code_uniqueness(invitation_db):
    url, _, course = invitation_db
    with connect(url) as db:
        db.execute("INSERT INTO course_invite_codes (code, course_id) VALUES (?, ?)", ("ABC234", course.id))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO course_invite_codes (code, course_id) VALUES (?, ?)", ("DEF567", course.id))
        db.execute("UPDATE course_invite_codes SET revoked_at = rotated_at WHERE code = ?", ("ABC234",))
        db.execute("INSERT INTO course_invite_codes (code, course_id) VALUES (?, ?)", ("DEF567", course.id))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO course_invite_codes (code, course_id, revoked_at) VALUES (?, ?, ?)", ("ABC234", course.id, "2026-11-05T00:00:00Z"))
        assert db.execute("SELECT code FROM course_invite_codes WHERE course_id = ? AND revoked_at IS NULL", (course.id,)).fetchall() == [("DEF567",)]


@pytest.mark.parametrize("code", ["ABC23", "ABC2345", "ABC23O", "ABC23I", "ABC230", "ABC231", "abc234"])
def test_invite_code_format_is_enforced_in_database(invitation_db, code):
    url, _, course = invitation_db
    with connect(url) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO course_invite_codes (code, course_id) VALUES (?, ?)", (code, course.id))


def test_invite_rollback_preserves_course_members_and_reapplies(invitation_db):
    url, teacher, course = invitation_db
    # Roll back dependent migrations first; history must remain a contiguous prefix.
    migrations = [p for p in sorted(MIGRATIONS_DIR.glob("*.sql")) if p.name[:3] >= "020"]
    with connect(url) as db:
        db.execute("INSERT INTO course_invite_codes (code, course_id) VALUES (?, ?)", ("ABC234", course.id))
        for migration in reversed(migrations):
            for line in migration.read_text().splitlines():
                if line.startswith("-- ROLLBACK:"):
                    db.execute(line.split("ROLLBACK:", 1)[1].strip())
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'course_invite_codes'").fetchone() is None
    assert get_member(url, course.id, teacher.id).role == "teacher"
    assert migrate(url) == [p.name[:3] for p in migrations]
