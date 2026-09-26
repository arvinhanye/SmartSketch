"""ADR-022：上传上限经 getUploadPolicy 下发（取值即 UPLOAD_MAX_BYTES）。"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import migrate
from app.services.auth import issue_access_token

SECRET = "adr022-test-signing-key-0123456789abcdef"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


def _account(url: str, username: str, role: str):
    return insert_account(url, account_id=uuid.uuid4().hex, username=username, password_hash=VALID_HASH, role=role)


def _headers(user) -> dict[str, str]:
    token = issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=int(time.time()), ttl_seconds=3600
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    student = _account(url, "student1", "student")
    outsider = _account(url, "teacher2", "teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))

    def client(limit: int | None = None) -> TestClient:
        if limit is None:
            monkeypatch.delenv("UPLOAD_MAX_BYTES", raising=False)
        else:
            monkeypatch.setenv("UPLOAD_MAX_BYTES", str(limit))
        return TestClient(create_app())

    return {"teacher": teacher, "student": student, "outsider": outsider, "course": course, "client": client}


def _path(course_id: str) -> str:
    return f"/api/v1/courses/{course_id}/upload-policy"


def test_policy_reports_configured_limit(world):
    with world["client"](123_456) as client:
        response = client.get(_path(world["course"].id), headers=_headers(world["teacher"]))

    assert response.status_code == 200
    assert response.json() == {"max_bytes": 123_456}


def test_policy_defaults_to_50_mib(world):
    with world["client"]() as client:
        response = client.get(_path(world["course"].id), headers=_headers(world["teacher"]))

    assert response.json() == {"max_bytes": 50 * 1024 * 1024}


def test_policy_matches_413_limit_bytes(world):
    with world["client"](8) as client:
        policy = client.get(_path(world["course"].id), headers=_headers(world["teacher"])).json()
        rejected = client.post(
            f"/api/v1/courses/{world['course'].id}/documents",
            headers=_headers(world["teacher"]),
            files={"file": ("notes.txt", b"123456789", "text/plain")},
        )

    assert rejected.status_code == 413
    assert rejected.json()["details"]["limit_bytes"] == policy["max_bytes"]


@pytest.mark.parametrize(
    ("who", "status", "code"),
    [("anonymous", 401, "UNAUTHENTICATED"), ("student", 403, "ROLE_FORBIDDEN"), ("outsider", 403, "COURSE_FORBIDDEN")],
)
def test_access_matrix(world, who, status, code):
    headers = {} if who == "anonymous" else _headers(world[who])
    with world["client"](1024) as client:
        response = client.get(_path(world["course"].id), headers=headers)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_openapi_exposes_operation(world):
    with world["client"](1024) as client:
        operation = client.app.openapi()["paths"]["/api/v1/courses/{cid}/upload-policy"]["get"]

    assert operation["operationId"] == "getUploadPolicy"
