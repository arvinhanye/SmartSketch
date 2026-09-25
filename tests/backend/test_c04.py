"""C04 course HTTP contract, access rules, and SQLite transaction boundary."""

import time
import uuid
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.schemas.contracts import Course, CourseCreate
from app.services.auth import issue_access_token


SECRET = "c04-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(
        url, account_id=uuid.uuid4().hex, username="teacher1",
        password_hash=VALID_HASH, role="teacher",
    )
    student = insert_account(
        url, account_id=uuid.uuid4().hex, username="student1",
        password_hash=VALID_HASH, role="student",
    )
    outsider = insert_account(
        url, account_id=uuid.uuid4().hex, username="teacher2",
        password_hash=VALID_HASH, role="teacher",
    )
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    with TestClient(create_app()) as client:
        yield client, url, teacher, student, outsider


def auth(user):
    token = issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(),
        issued_at=int(time.time()), ttl_seconds=3600,
    )
    return {"Authorization": f"Bearer {token}"}


def test_teacher_creates_course_and_member_atomically(scenario):
    client, url, teacher, _, _ = scenario
    response = client.post(
        "/api/v1/courses", headers=auth(teacher),
        json={"name": "Algebra", "description": "First year"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Algebra"
    assert body["description"] == "First year"
    assert body["teacher_id"] == teacher.id
    assert body["my_role"] == "teacher"
    assert body["status"] == "draft"
    assert body.get("published_version") is None
    assert "kp_count" not in body
    assert Course.model_validate(body).id == body["id"]
    contract = json.loads(
        (Path(__file__).resolve().parents[2] / "src/contracts/v1/generated/openapi.json").read_text(encoding="utf-8")
    )
    Draft202012Validator({
        "$ref": "#/components/schemas/Course", "components": contract["components"],
    }).validate(body)
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses WHERE id = ?", (body["id"],)).fetchone()[0] == 1
        assert db.execute(
            "SELECT role FROM course_members WHERE course_id = ? AND user_id = ?",
            (body["id"], teacher.id),
        ).fetchone() == ("teacher",)


def test_list_filters_membership_and_unpublished_student_course(scenario):
    client, url, teacher, student, outsider = scenario
    draft = create_course(url, name="Draft", description=None, creator_id=teacher.id)
    published = create_course(url, name="Published", description=None, creator_id=teacher.id)
    add_member(url, course_id=draft.id, user_id=student.id, role="student", added_by=teacher.id)
    add_member(url, course_id=published.id, user_id=student.id, role="student", added_by=teacher.id)
    with connect(url) as db:
        db.execute(
            "UPDATE courses SET published_version_id = ?, published_version = 1, "
            "published_from_revision = draft_revision WHERE id = ?",
            (uuid.uuid4().hex, published.id),
        )
    assert {c["id"] for c in client.get("/api/v1/courses", headers=auth(teacher)).json()} == {
        draft.id, published.id,
    }
    student_list = client.get("/api/v1/courses", headers=auth(student))
    assert student_list.status_code == 200
    assert [(c["id"], c["my_role"], c["status"]) for c in student_list.json()] == [
        (published.id, "student", "published")
    ]
    assert client.get("/api/v1/courses", headers=auth(outsider)).json() == []


def test_teacher_account_can_have_student_course_role(scenario):
    client, url, teacher, _, outsider = scenario
    course = create_course(url, name="Guest", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=outsider.id, role="student", added_by=teacher.id)
    assert client.get("/api/v1/courses", headers=auth(outsider)).json() == []
    with connect(url) as db:
        db.execute(
            "UPDATE courses SET published_version_id = ?, published_version = 2, "
            "draft_revision = 3, published_from_revision = 2 WHERE id = ?",
            (uuid.uuid4().hex, course.id),
        )
    body = client.get("/api/v1/courses", headers=auth(outsider)).json()
    assert [(c["my_role"], c["status"], c["published_version"]) for c in body] == [
        ("student", "revising", 2)
    ]


def test_create_rejects_student_and_unauthenticated_without_writing(scenario):
    client, url, _, student, _ = scenario
    before = client.post("/api/v1/courses", json={"name": "No token"})
    forbidden = client.post("/api/v1/courses", headers=auth(student), json={"name": "Forbidden"})
    assert (before.status_code, before.json()["code"]) == (401, "UNAUTHENTICATED")
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "ROLE_FORBIDDEN")
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_request_role_and_creator_fields_cannot_override_authenticated_creator(scenario):
    client, url, teacher, _, outsider = scenario
    response = client.post(
        "/api/v1/courses", headers={**auth(teacher), "X-Role": "student"},
        json={"name": "Owned", "teacher_id": outsider.id, "my_role": "student"},
    )
    assert response.status_code == 201
    assert response.json()["teacher_id"] == teacher.id
    assert response.json()["my_role"] == "teacher"
    assert CourseCreate.model_validate({"name": "Owned"}).name == "Owned"
    with connect(url) as db:
        assert db.execute("SELECT teacher_id FROM courses").fetchone() == (teacher.id,)


def test_member_insert_failure_rolls_back_course_creation(scenario):
    client, url, teacher, _, _ = scenario
    with connect(url) as db:
        db.execute(
            "CREATE TRIGGER c04_reject_member BEFORE INSERT ON course_members "
            "BEGIN SELECT RAISE(ABORT, 'rejected by test'); END"
        )
    with pytest.raises(ValueError, match="constraints"):
        client.post("/api/v1/courses", headers=auth(teacher), json={"name": "Atomic"})
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM course_members").fetchone()[0] == 0


@pytest.mark.parametrize("name", ["", "x" * 121])
def test_create_rejects_invalid_name_with_contract_error(scenario, name):
    client, url, teacher, _, _ = scenario
    response = client.post("/api/v1/courses", headers=auth(teacher), json={"name": name})
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_explicit_null_description_is_rejected_by_wire_contract(scenario):
    client, url, teacher, _, _ = scenario
    response = client.post(
        "/api/v1/courses", headers=auth(teacher),
        json={"name": "Algebra", "description": None},
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_list_requires_token(scenario):
    client, _, _, _, _ = scenario
    response = client.get("/api/v1/courses")
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")
