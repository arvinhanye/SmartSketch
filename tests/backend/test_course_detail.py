"""getCourse (GET /api/v1/courses/{cid}): the course page's detail read, found missing in the
2026-09-27 end-to-end run (the page showed「课程加载失败」for every course)."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token

SECRET = "detail-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    users = {
        name: insert_account(url, account_id=uuid.uuid4().hex, username=name,
                             password_hash=VALID_HASH, role=role)
        for name, role in (("teacher1", "teacher"), ("student1", "student"), ("teacher2", "teacher"))
    }
    course = create_course(url, name="数据结构", description=None, creator_id=users["teacher1"].id)
    add_member(url, course_id=course.id, user_id=users["student1"].id, role="student",
               added_by=users["teacher1"].id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    with TestClient(create_app()) as client:
        yield client, url, users, course


def auth(user):
    token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                               issued_at=int(time.time()), ttl_seconds=3600)
    return {"Authorization": f"Bearer {token}"}


def test_teacher_reads_own_course(scenario):
    client, _, users, course = scenario
    response = client.get(f"/api/v1/courses/{course.id}", headers=auth(users["teacher1"]))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == course.id and body["name"] == "数据结构"
    assert body["my_role"] == "teacher" and body["status"] == "draft"
    assert "published_version" not in body


def test_student_on_unpublished_course_gets_404(scenario):
    client, _, users, course = scenario
    response = client.get(f"/api/v1/courses/{course.id}", headers=auth(users["student1"]))
    assert response.status_code == 404
    assert response.json()["code"] == "GRAPH_NOT_PUBLISHED"


def test_student_reads_published_course(scenario):
    client, url, users, course = scenario
    with connect(url) as db:
        db.execute("INSERT INTO graph_versions(version_id, course_id, kind, expires_at) VALUES (?, ?, 'publish', 1)",
                   ("v" * 26, course.id))
        db.execute("UPDATE courses SET published_version_id = ?, published_version = 1, "
                   "published_from_revision = draft_revision WHERE id = ?", ("v" * 26, course.id))
    response = client.get(f"/api/v1/courses/{course.id}", headers=auth(users["student1"]))
    assert response.status_code == 200
    assert response.json()["my_role"] == "student"
    assert response.json()["status"] == "published"


@pytest.mark.parametrize("cid", ["missing", None])
def test_non_member_and_unknown_course_are_both_403(scenario, cid):
    client, _, users, course = scenario
    response = client.get(f"/api/v1/courses/{cid or course.id}", headers=auth(users["teacher2"]))
    assert response.status_code == 403
    assert response.json()["code"] == "COURSE_FORBIDDEN"


def test_requires_authentication(scenario):
    client, _, _, course = scenario
    assert client.get(f"/api/v1/courses/{course.id}").status_code == 401
