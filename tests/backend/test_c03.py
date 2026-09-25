"""C03 identity and course authorization against real SQLite rows."""

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import insert_account, set_disabled
from app.repositories.courses import add_member, create_course, remove_member
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token

from app.api.dependencies import (
    current_user,
    course_reader,
    course_student,
    course_teacher,
    task_teacher,
    teacher_account,
)

SECRET = "c03-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(
        url,
        account_id=uuid.uuid4().hex,
        username="teacher1",
        password_hash=VALID_HASH,
        role="teacher",
    )
    student = insert_account(
        url,
        account_id=uuid.uuid4().hex,
        username="student1",
        password_hash=VALID_HASH,
        role="student",
    )
    outsider = insert_account(
        url,
        account_id=uuid.uuid4().hex,
        username="teacher2",
        password_hash=VALID_HASH,
        role="teacher",
    )
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    add_member(
        url,
        course_id=course.id,
        user_id=student.id,
        role="student",
        added_by=teacher.id,
    )
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    application = create_app()
    router = APIRouter()

    @router.get("/probe/me")
    def me(user=Depends(current_user)):
        return {"id": user.id, "role": user.role}

    @router.post("/probe/write")
    def write(body: dict, user=Depends(current_user)):
        return {"owner_id": user.id, "submitted_user_id": body.get("user_id")}

    @router.post("/probe/create")
    def create(user=Depends(teacher_account)):
        return {"creator_id": user.id}

    @router.get("/probe/courses/{cid}/read")
    def read(access=Depends(course_reader)):
        return {"id": access.user.id, "role": access.member.role}

    @router.get("/probe/courses/{cid}/edit")
    def edit(access=Depends(course_teacher)):
        return {"id": access.user.id}

    @router.get("/probe/courses/{cid}/progress")
    def progress(access=Depends(course_student)):
        return {"id": access.user.id}

    @router.get("/probe/tasks/{tid}")
    def task(access=Depends(task_teacher)):
        return {"id": access.user.id}

    application.include_router(router)
    with TestClient(application) as client:
        yield client, url, teacher, student, outsider, course


def token(user, *, now=None, secret=SECRET):
    return issue_access_token(
        user_id=user.id,
        role=user.role,
        secret=secret.encode(),
        issued_at=int(time.time()) if now is None else now,
        ttl_seconds=3600,
    )


def get(client, path, bearer=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    return client.get(path, headers=headers, **kwargs)


def test_identity_comes_only_from_verified_token_and_live_account(scenario):
    client, url, teacher, student, _, _ = scenario
    path = "/probe/me"
    assert get(
        client,
        path,
        token(student),
        headers={"X-User-Id": teacher.id, "X-Role": "teacher"},
    ).json() == {"id": student.id, "role": "student"}
    assert (
        get(client, path, headers={"X-User-Id": teacher.id}).json()["code"]
        == "UNAUTHENTICATED"
    )
    assert (
        get(client, path, token(student), params={"user_id": teacher.id}).json()["id"]
        == student.id
    )
    posted = client.post(
        "/probe/write",
        headers={"Authorization": f"Bearer {token(student)}", "X-User-Id": teacher.id},
        json={"user_id": teacher.id},
    )
    assert posted.json()["owner_id"] == student.id
    set_disabled(url, "student1", True)
    denied = get(client, path, token(student))
    assert (denied.status_code, denied.json()["code"]) == (401, "UNAUTHENTICATED")


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "tamper_sub",
        "tamper_role",
        "none",
        "other_key",
        "expired",
        "future",
        "bad_shape",
    ],
)
def test_bad_tokens_are_rejected(scenario, kind):
    client, _, teacher, student, _, _ = scenario
    value = token(student)
    if kind == "missing":
        value = None
    elif kind in {"tamper_sub", "tamper_role", "none", "bad_shape"}:
        head, payload, signature = value.split(".")
        decoded = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        if kind == "tamper_sub":
            decoded["sub"] = teacher.id
        elif kind == "tamper_role":
            decoded["role"] = "teacher"
        elif kind == "bad_shape":
            decoded.pop("iat")
        else:
            head = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
        payload = (
            base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=").decode()
        )
        value = f"{head}.{payload}.{signature}"
    elif kind == "other_key":
        value = token(student, secret="another-signing-key-0123456789abcdefgh")
    elif kind == "expired":
        value = token(student, now=1)
    else:
        value = token(student, now=int(time.time()) + 120)
    result = get(client, "/probe/me", value)
    assert (result.status_code, result.json()["code"]) == (401, "UNAUTHENTICATED")


@pytest.mark.parametrize(
    "change", ["missing_exp", "wrong_alg", "extra_claim", "boolean_time"]
)
def test_even_correctly_signed_invalid_claims_are_rejected(scenario, change):
    client, _, _, student, _, _ = scenario
    head, payload, _ = token(student).split(".")
    header_data = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if change == "missing_exp":
        claims.pop("exp")
    elif change == "wrong_alg":
        header_data["alg"] = "none"
    elif change == "extra_claim":
        claims["admin"] = True
    else:
        claims["iat"] = True
    encoded = [
        base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
        for value in (header_data, claims)
    ]
    signed = ".".join(encoded)
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(SECRET.encode(), signed.encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    response = get(client, "/probe/me", f"{signed}.{signature}")
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")


def test_course_membership_role_and_publication_order(scenario):
    client, url, teacher, student, outsider, course = scenario
    base = f"/probe/courses/{course.id}"
    assert get(client, base + "/edit", token(teacher)).status_code == 200
    assert (
        get(client, base + "/edit", token(student)).status_code,
        get(client, base + "/edit", token(student)).json()["code"],
    ) == (403, "ROLE_FORBIDDEN")
    assert (
        get(client, base + "/progress", token(teacher)).json()["code"]
        == "ROLE_FORBIDDEN"
    )
    assert (
        get(client, base + "/read", token(student)).json()["code"]
        == "GRAPH_NOT_PUBLISHED"
    )
    missing = get(client, "/probe/courses/no-such-course/read", token(outsider))
    other = get(client, base + "/read", token(outsider))
    assert missing.status_code == other.status_code == 403
    assert missing.json() == other.json()
    with connect(url) as db:
        db.execute(
            "UPDATE courses SET published_version = 1, published_version_id = ? WHERE id = ?",
            (uuid.uuid4().hex, course.id),
        )
    assert get(client, base + "/read", token(student)).status_code == 200
    remove_member(url, course.id, student.id)
    assert (
        get(client, base + "/read", token(student)).json()["code"] == "COURSE_FORBIDDEN"
    )
    add_member(
        url,
        course_id=course.id,
        user_id=student.id,
        role="student",
        added_by=teacher.id,
    )
    assert get(client, base + "/read", token(student)).status_code == 200


def test_course_role_overrides_account_and_token_role(scenario):
    client, url, teacher, _, outsider, course = scenario
    second = create_course(url, name="B", description=None, creator_id=outsider.id)
    add_member(
        url,
        course_id=second.id,
        user_id=teacher.id,
        role="student",
        added_by=outsider.id,
    )
    base = f"/probe/courses/{second.id}"
    assert (
        get(client, base + "/edit", token(teacher)).json()["code"] == "ROLE_FORBIDDEN"
    )
    assert (
        get(client, base + "/progress", token(teacher)).json()["code"]
        == "GRAPH_NOT_PUBLISHED"
    )


def test_course_creation_depends_on_account_type(scenario):
    client, _, teacher, student, _, _ = scenario
    allowed = client.post(
        "/probe/create", headers={"Authorization": f"Bearer {token(teacher)}"}
    )
    assert allowed.json()["creator_id"] == teacher.id
    denied = client.post(
        "/probe/create", headers={"Authorization": f"Bearer {token(student)}"}
    )
    assert (denied.status_code, denied.json()["code"]) == (403, "ROLE_FORBIDDEN")


def test_task_nonmember_and_missing_are_indistinguishable(scenario):
    client, url, teacher, student, outsider, course = scenario
    with connect(url) as db:
        db.execute(
            "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) VALUES ('doc1', ?, 'a.txt', 'txt', 1, ?, 'stored')",
            (course.id, "sha256:" + "a" * 64),
        )
        db.execute(
            "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key) VALUES ('task1', ?, 'doc1', 'key')",
            (course.id,),
        )
    denied = get(client, "/probe/tasks/task1", token(outsider))
    missing = get(client, "/probe/tasks/missing", token(outsider))
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()
    assert (
        get(client, "/probe/tasks/task1", token(student)).json()["code"]
        == "ROLE_FORBIDDEN"
    )
    assert get(client, "/probe/tasks/task1", token(teacher)).status_code == 200
