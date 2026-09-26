"""C15 course member management API (specs/identity-access.md §3.3, §4).

Covers list/add/remove members: only course teacher members may use them; adding is
idempotent and never re-roles (a teacher member is not downgraded); only student members
can be removed; non-members and unknown courses get the same 403 COURSE_FORBIDDEN, and every
lookup is scoped by ``course_id``.
"""

import json
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.courses import (
    RoleNotAllowed,
    add_member,
    create_course,
    get_member,
    list_members,
)
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token


SECRET = "c15-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "src/contracts/v1/generated/openapi.json").read_text(
        encoding="utf-8"
    )
)


def _account(url, username, role):
    return insert_account(
        url, account_id=uuid.uuid4().hex, username=username,
        password_hash=VALID_HASH, role=role,
    )


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    users = {
        "teacher": _account(url, "teacher1", "teacher"),
        "co_teacher": _account(url, "teacher2", "teacher"),
        "outsider": _account(url, "teacher3", "teacher"),
        "student": _account(url, "student1", "student"),
        "newbie": _account(url, "student2", "student"),
    }
    course = create_course(url, name="Algebra", description=None, creator_id=users["teacher"].id)
    add_member(
        url, course_id=course.id, user_id=users["co_teacher"].id, role="teacher", added_by=None
    )
    add_member(
        url, course_id=course.id, user_id=users["student"].id, role="student",
        added_by=users["teacher"].id,
    )
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    with TestClient(create_app()) as client:
        yield client, url, course, users


def auth(user):
    token = issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(),
        issued_at=int(time.time()), ttl_seconds=3600,
    )
    return {"Authorization": f"Bearer {token}"}


def members_path(course_id):
    return f"/api/v1/courses/{course_id}/members"


def validate_member(body):
    Draft202012Validator(
        {"$ref": "#/components/schemas/CourseMember", "components": CONTRACT["components"]}
    ).validate(body)


def roles(url, course_id):
    return {(m.username, m.role) for m in list_members(url, course_id)}


# --- list ------------------------------------------------------------------------------


def test_teacher_lists_members_with_contract_fields(scenario):
    client, _, course, users = scenario
    response = client.get(members_path(course.id), headers=auth(users["co_teacher"]))
    assert response.status_code == 200
    body = response.json()
    assert [(m["username"], m["role"]) for m in body] == [
        ("teacher1", "teacher"), ("teacher2", "teacher"), ("student1", "student"),
    ]
    for member in body:
        validate_member(member)
        assert set(member) == {"user_id", "username", "role", "created_at"}
    assert body[0]["user_id"] == users["teacher"].id


def test_list_is_scoped_to_the_course(scenario):
    client, url, course, users = scenario
    other = create_course(url, name="Other", description=None, creator_id=users["outsider"].id)
    add_member(
        url, course_id=other.id, user_id=users["newbie"].id, role="student",
        added_by=users["outsider"].id,
    )
    names = {m["username"] for m in client.get(
        members_path(course.id), headers=auth(users["teacher"])
    ).json()}
    assert "student2" not in names and "teacher3" not in names


# --- access matrix (§4.3 listMembers / addMember / removeMember) ----------------------


def _requests(course_id, target_id):
    return [
        ("GET", members_path(course_id), None),
        ("POST", members_path(course_id), {"username": "student2"}),
        ("DELETE", f"{members_path(course_id)}/{target_id}", None),
    ]


def test_anonymous_and_bad_token_get_401(scenario):
    client, url, course, users = scenario
    before = roles(url, course.id)
    for method, path, body in _requests(course.id, users["student"].id):
        for headers in ({}, {"Authorization": "Bearer not.a.token"}):
            response = client.request(method, path, json=body, headers=headers)
            assert response.status_code == 401, (method, headers)
            assert response.json()["code"] == "UNAUTHENTICATED"
    assert roles(url, course.id) == before


def test_student_member_gets_role_forbidden(scenario):
    client, url, course, users = scenario
    before = roles(url, course.id)
    for method, path, body in _requests(course.id, users["student"].id):
        response = client.request(method, path, json=body, headers=auth(users["student"]))
        assert response.status_code == 403, method
        assert response.json()["code"] == "ROLE_FORBIDDEN"
    assert roles(url, course.id) == before


def test_teacher_account_with_student_role_in_course_gets_role_forbidden(scenario):
    client, url, course, users = scenario
    add_member(
        url, course_id=course.id, user_id=users["outsider"].id, role="student",
        added_by=users["teacher"].id,
    )
    before = roles(url, course.id)
    for method, path, body in _requests(course.id, users["student"].id):
        response = client.request(method, path, json=body, headers=auth(users["outsider"]))
        assert response.status_code == 403, method
        assert response.json()["code"] == "ROLE_FORBIDDEN"
    assert roles(url, course.id) == before


def test_non_member_and_unknown_course_get_same_course_forbidden(scenario):
    client, url, course, users = scenario
    before = roles(url, course.id)
    shapes = set()
    for course_id, user in ((course.id, users["outsider"]), (uuid.uuid4().hex, users["teacher"])):
        for method, path, body in _requests(course_id, users["student"].id):
            response = client.request(method, path, json=body, headers=auth(user))
            assert response.status_code == 403, (method, course_id)
            shapes.add(json.dumps(response.json(), sort_keys=True))
    assert len(shapes) == 1
    assert json.loads(shapes.pop())["code"] == "COURSE_FORBIDDEN"
    assert roles(url, course.id) == before


def test_teacher_of_another_course_cannot_manage_this_one(scenario):
    client, url, course, users = scenario
    create_course(url, name="Mine", description=None, creator_id=users["outsider"].id)
    response = client.post(
        members_path(course.id), json={"username": "student2"}, headers=auth(users["outsider"])
    )
    assert response.status_code == 403
    assert response.json()["code"] == "COURSE_FORBIDDEN"
    assert get_member(url, course.id, users["newbie"].id) is None


# --- add -------------------------------------------------------------------------------


def test_teacher_adds_student_by_username(scenario):
    client, url, course, users = scenario
    response = client.post(
        members_path(course.id), json={"username": "student2"}, headers=auth(users["teacher"])
    )
    assert response.status_code == 201
    body = response.json()
    validate_member(body)
    assert (body["user_id"], body["username"], body["role"]) == (
        users["newbie"].id, "student2", "student",
    )
    stored = get_member(url, course.id, users["newbie"].id)
    assert stored.role == "student" and stored.added_by == users["teacher"].id


def test_username_lookup_is_case_insensitive(scenario):
    client, _, course, users = scenario
    response = client.post(
        members_path(course.id), json={"username": "Student2"}, headers=auth(users["teacher"])
    )
    assert response.status_code == 201
    assert response.json()["user_id"] == users["newbie"].id


def test_teacher_account_is_added_as_student_member(scenario):
    client, url, course, users = scenario
    response = client.post(
        members_path(course.id), json={"username": "teacher3"}, headers=auth(users["teacher"])
    )
    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert get_member(url, course.id, users["outsider"].id).role == "student"


def test_repeat_add_is_idempotent(scenario):
    client, url, course, users = scenario
    first = client.post(
        members_path(course.id), json={"username": "student2"}, headers=auth(users["teacher"])
    )
    second = client.post(
        members_path(course.id), json={"username": "student2"}, headers=auth(users["co_teacher"])
    )
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()
    stored = get_member(url, course.id, users["newbie"].id)
    assert stored.added_by == users["teacher"].id  # the existing row is not rewritten
    with connect(url) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM course_members WHERE course_id = ? AND user_id = ?",
            (course.id, users["newbie"].id),
        ).fetchone()[0] == 1


@pytest.mark.parametrize("username", ["teacher1", "teacher2"])
def test_adding_existing_teacher_member_does_not_downgrade(scenario, username):
    client, url, course, users = scenario
    response = client.post(
        members_path(course.id), json={"username": username}, headers=auth(users["teacher"])
    )
    assert response.status_code == 200
    assert response.json()["role"] == "teacher"
    validate_member(response.json())
    assert (username, "teacher") in roles(url, course.id)


def test_unknown_or_disabled_username_is_not_found(scenario):
    client, url, course, users = scenario
    with connect(url) as db:
        db.execute(
            "UPDATE users SET disabled_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (users["newbie"].id,),
        )
    before = roles(url, course.id)
    shapes = set()
    for username in ("nobody", "student2"):
        response = client.post(
            members_path(course.id), json={"username": username}, headers=auth(users["teacher"])
        )
        assert response.status_code == 404
        shapes.add(json.dumps(response.json(), sort_keys=True))
    assert len(shapes) == 1 and json.loads(shapes.pop())["code"] == "NOT_FOUND"
    assert roles(url, course.id) == before


@pytest.mark.parametrize(
    "body",
    [{}, {"username": ""}, {"username": 5}, {"username": "student2", "role": "teacher"}],
)
def test_invalid_body_is_validation_error_or_ignored_role(scenario, body):
    client, url, course, users = scenario
    response = client.post(members_path(course.id), json=body, headers=auth(users["teacher"]))
    if "role" in body:
        # The caller cannot choose the role: the new member is always a student.
        assert response.status_code == 201
        assert response.json()["role"] == "student"
    else:
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
        assert get_member(url, course.id, users["newbie"].id) is None


def test_repository_still_refuses_student_account_as_teacher_member(scenario):
    # §3.2.1: the API never writes teacher rows; the repository guard stays in force.
    _, url, course, users = scenario
    with pytest.raises(RoleNotAllowed):
        add_member(
            url, course_id=course.id, user_id=users["newbie"].id, role="teacher",
            added_by=users["teacher"].id,
        )


# --- remove ----------------------------------------------------------------------------


def test_teacher_removes_student_member(scenario):
    client, url, course, users = scenario
    response = client.delete(
        f"{members_path(course.id)}/{users['student'].id}", headers=auth(users["teacher"])
    )
    assert response.status_code == 204
    assert response.content == b""
    assert get_member(url, course.id, users["student"].id) is None


@pytest.mark.parametrize("target", ["teacher", "co_teacher"])
def test_removing_teacher_member_including_self_is_forbidden(scenario, target):
    client, url, course, users = scenario
    before = roles(url, course.id)
    response = client.delete(
        f"{members_path(course.id)}/{users[target].id}", headers=auth(users["teacher"])
    )
    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_FORBIDDEN"
    assert roles(url, course.id) == before


def test_removing_non_member_is_not_found(scenario):
    client, url, course, users = scenario
    other = create_course(url, name="Other", description=None, creator_id=users["outsider"].id)
    add_member(
        url, course_id=other.id, user_id=users["newbie"].id, role="student",
        added_by=users["outsider"].id,
    )
    before = roles(url, course.id)
    for target in (users["newbie"].id, uuid.uuid4().hex):
        response = client.delete(
            f"{members_path(course.id)}/{target}", headers=auth(users["teacher"])
        )
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
    assert roles(url, course.id) == before
    # The same user's membership in another course is untouched.
    assert get_member(url, other.id, users["newbie"].id).role == "student"


def test_remove_twice_second_is_not_found(scenario):
    client, _, course, users = scenario
    path = f"{members_path(course.id)}/{users['student'].id}"
    assert client.delete(path, headers=auth(users["teacher"])).status_code == 204
    assert client.delete(path, headers=auth(users["teacher"])).status_code == 404


def test_removed_student_loses_membership_and_can_rejoin(scenario):
    client, url, course, users = scenario
    # getCourse is not implemented yet; listDocuments shows the member check (§4.1 step 3).
    probe = f"/api/v1/courses/{course.id}/documents"
    before = client.get(probe, headers=auth(users["student"]))
    assert before.json()["code"] == "ROLE_FORBIDDEN"  # member, wrong role
    client.delete(f"{members_path(course.id)}/{users['student'].id}", headers=auth(users["teacher"]))
    after = client.get(probe, headers=auth(users["student"]))
    assert after.status_code == 403 and after.json()["code"] == "COURSE_FORBIDDEN"
    rejoin = client.post(
        members_path(course.id), json={"username": "student1"}, headers=auth(users["teacher"])
    )
    assert rejoin.status_code == 201 and rejoin.json()["role"] == "student"
    assert client.get(probe, headers=auth(users["student"])).json()["code"] == "ROLE_FORBIDDEN"


# --- OpenAPI wiring ----------------------------------------------------------------------


def test_operations_are_registered_with_contract_ids(scenario):
    client, _, _, _ = scenario
    paths = client.app.openapi()["paths"]
    assert paths["/api/v1/courses/{cid}/members"]["get"]["operationId"] == "listMembers"
    assert paths["/api/v1/courses/{cid}/members"]["post"]["operationId"] == "addMember"
    assert paths["/api/v1/courses/{cid}/members/{uid}"]["delete"]["operationId"] == "removeMember"
    for method, codes in (("get", {"200", "401", "403"}),
                          ("post", {"200", "201", "401", "403", "404", "422"})):
        assert codes <= set(paths["/api/v1/courses/{cid}/members"][method]["responses"])
    assert {"204", "401", "403", "404"} <= set(
        paths["/api/v1/courses/{cid}/members/{uid}"]["delete"]["responses"]
    )
