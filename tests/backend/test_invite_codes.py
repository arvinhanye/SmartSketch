"""ADR-096: invitation HTTP behavior, bounded guessing and transaction ordering."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from importlib import import_module
import json
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace
import uuid

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course, get_member
from app.repositories.sqlite import connect
from app.services.access import AccessDenied, AccessService
from app.services.auth import issue_access_token
from tests.backend.helpers.sqlite import migrated_database


SECRET = "invite-tests-only-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
JOIN = "/api/v1/courses/join"
CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "src/contracts/v1/generated/openapi.json")
    .read_text(encoding="utf-8")
)


def auth(user):
    token = issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(),
        issued_at=int(time.time()), ttl_seconds=3600,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scenario(tmp_path, app_factory):
    url = migrated_database(f"sqlite:///{tmp_path / 'state.sqlite3'}")
    users = {
        name: insert_account(
            url, account_id=uuid.uuid4().hex, username=name,
            password_hash=VALID_HASH, role=role,
        )
        for name, role in (
            ("teacher", "teacher"), ("co_teacher", "teacher"),
            ("outsider", "teacher"), ("student", "student"), ("newbie", "student"),
        )
    }
    course = create_course(url, name="Algebra", description="Course A", creator_id=users["teacher"].id)
    add_member(url, course_id=course.id, user_id=users["co_teacher"].id, role="teacher", added_by=None)
    add_member(url, course_id=course.id, user_id=users["student"].id, role="student", added_by=users["teacher"].id)
    app = app_factory(SQLITE_URL=url, AUTH_JWT_SECRET=SECRET)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, url=url, users=users, course=course)


def invite_path(course_id):
    return f"/api/v1/courses/{course_id}/invite-code"


def invite_code(scenario, user="teacher", course_id=None):
    result = scenario.client.get(
        invite_path(course_id or scenario.course.id), headers=auth(scenario.users[user]),
    )
    assert result.status_code == 200, result.text
    return result.json()["code"]


def join(scenario, code, user="newbie", **kwargs):
    return scenario.client.post(JOIN, headers=auth(scenario.users[user]), json={"code": code}, **kwargs)


def publish(scenario):
    version = uuid.uuid4().hex[:26]
    with connect(scenario.url) as db:
        db.execute(
            "INSERT INTO graph_versions(version_id, course_id, kind, expires_at, node_count) "
            "VALUES (?, ?, 'publish', 1, 12)", (version, scenario.course.id),
        )
        db.execute(
            "UPDATE courses SET published_version_id = ?, published_version = 1, "
            "published_from_revision = draft_revision WHERE id = ?",
            (version, scenario.course.id),
        )


def validate(body, schema):
    Draft202012Validator({
        "$ref": f"#/components/schemas/{schema}", "components": CONTRACT["components"],
    }).validate(body)


def module(name="services"):
    return import_module(f"app.{name}.invite_codes")


def test_teachers_share_one_lazy_code_and_no_course_read_leaks_it(scenario):
    path = invite_path(scenario.course.id)
    first = scenario.client.get(path, headers=auth(scenario.users["co_teacher"]))
    assert first.status_code == 200
    validate(first.json(), "InviteCodeResponse")
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", first.json()["code"])
    assert first.headers["cache-control"] == "no-store"
    assert scenario.client.get(path, headers=auth(scenario.users["teacher"])).json() == first.json()
    with connect(scenario.url) as db:
        assert db.execute("SELECT COUNT(*) FROM course_invite_codes").fetchone() == (1,)
    for target in ("/api/v1/courses", f"/api/v1/courses/{scenario.course.id}"):
        assert first.json()["code"] not in scenario.client.get(target, headers=auth(scenario.users["teacher"])).text


@pytest.mark.parametrize("published", [False, True])
def test_join_returns_course_but_retains_publication_boundary(scenario, published):
    if published:
        publish(scenario)
    response = join(scenario, invite_code(scenario))
    assert response.status_code == 201
    body = response.json()
    validate(body, "Course")
    assert body["id"] == scenario.course.id
    assert body["my_role"] == "student"
    assert body["status"] == ("published" if published else "draft")
    assert body.get("kp_count") == (12 if published else None)
    member = get_member(scenario.url, scenario.course.id, scenario.users["newbie"].id)
    assert member.role == "student" and member.added_by == scenario.users["newbie"].id
    listed = scenario.client.get("/api/v1/courses", headers=auth(scenario.users["newbie"])).json()
    assert [row["id"] for row in listed] == ([scenario.course.id] if published else [])
    if not published:
        for suffix in ("", "/graph", "/progress"):
            denied = scenario.client.get(
                f"/api/v1/courses/{scenario.course.id}{suffix}", headers=auth(scenario.users["newbie"]),
            )
            assert (denied.status_code, denied.json()["code"]) == (404, "GRAPH_NOT_PUBLISHED")


def test_rotation_retires_old_code_and_keeps_joined_members(scenario):
    old = invite_code(scenario)
    assert join(scenario, old).status_code == 201
    rotated = scenario.client.post(invite_path(scenario.course.id) + ":rotate", headers=auth(scenario.users["co_teacher"]))
    assert rotated.status_code == 200
    assert rotated.headers["cache-control"] == "no-store"
    validate(rotated.json(), "InviteCodeResponse")
    assert rotated.json()["code"] != old
    invalid = join(scenario, "AAAAAA")
    retired = join(scenario, old)
    assert (retired.status_code, retired.json()["code"]) == (404, "INVITE_CODE_INVALID")
    assert invalid.json() == retired.json()
    assert old not in retired.text and scenario.course.id not in retired.text
    assert get_member(scenario.url, scenario.course.id, scenario.users["newbie"].id) is not None
    with connect(scenario.url) as db:
        assert db.execute("SELECT revoked_at IS NOT NULL FROM course_invite_codes WHERE code = ?", (old,)).fetchone() == (1,)


def test_repeat_join_is_conflict_and_preserves_existing_membership(scenario):
    before = get_member(scenario.url, scenario.course.id, scenario.users["student"].id)
    response = join(scenario, invite_code(scenario), user="student")
    assert (response.status_code, response.json()["code"]) == (409, "ALREADY_MEMBER")
    assert get_member(scenario.url, scenario.course.id, scenario.users["student"].id) == before


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("actor,status,code", [
    (None, 401, "UNAUTHENTICATED"), ("outsider", 403, "COURSE_FORBIDDEN"),
    ("student", 403, "ROLE_FORBIDDEN"),
])
def test_invite_management_is_course_teacher_only(scenario, method, actor, status, code):
    path = invite_path(scenario.course.id) + (":rotate" if method == "post" else "")
    response = getattr(scenario.client, method)(path, headers=auth(scenario.users[actor]) if actor else {})
    assert (response.status_code, response.json()["code"]) == (status, code)
    with connect(scenario.url) as db:
        assert db.execute("SELECT COUNT(*) FROM course_invite_codes").fetchone() == (0,)


def test_other_course_teacher_and_missing_course_are_indistinguishable(scenario):
    other = create_course(scenario.url, name="Other", description=None, creator_id=scenario.users["outsider"].id)
    for suffix, method in (("", "get"), (":rotate", "post")):
        responses = [getattr(scenario.client, method)(invite_path(cid) + suffix, headers=auth(scenario.users["teacher"])) for cid in (other.id, "missing")]
        assert [r.status_code for r in responses] == [403, 403]
        assert responses[0].json() == responses[1].json()


def test_teacher_account_cannot_join_even_when_student_in_another_course(scenario):
    code = invite_code(scenario)
    response = join(scenario, code, user="outsider")
    assert (response.status_code, response.json()["code"]) == (403, "ROLE_FORBIDDEN")
    assert get_member(scenario.url, scenario.course.id, scenario.users["outsider"].id) is None
    add_member(scenario.url, course_id=scenario.course.id, user_id=scenario.users["outsider"].id, role="student", added_by=None)
    response = join(scenario, code, user="outsider")
    assert (response.status_code, response.json()["code"]) == (403, "ROLE_FORBIDDEN")


def test_join_requires_authentication(scenario):
    response = scenario.client.post(JOIN, json={"code": "ABC234"})
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")


@pytest.mark.parametrize("body", [
    {}, {"code": None}, {"code": 123456}, {"code": "ABCDE"}, {"code": "ABCDEFG"},
    {"code": "abc234"}, {"code": " ABC234"}, {"code": "ABIO01"},
    {"code": "ABC234", "user_id": "victim"}, {"code": "ABC234", "role": "teacher"},
])
def test_join_has_closed_strict_code_schema_and_never_echoes_input(scenario, body):
    response = scenario.client.post(JOIN, json=body, headers=auth(scenario.users["newbie"]))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert "input" not in response.text and "victim" not in response.text
    assert get_member(scenario.url, scenario.course.id, scenario.users["newbie"].id) is None


@pytest.mark.parametrize("method,change,status,code", [
    ("get", "remove", 403, "COURSE_FORBIDDEN"),
    ("post", "remove", 403, "COURSE_FORBIDDEN"),
    ("post", "demote", 403, "ROLE_FORBIDDEN"),
    ("get", "disable", 401, "UNAUTHENTICATED"),
])
def test_teacher_authorization_is_rechecked_after_authentication(scenario, monkeypatch, method, change, status, code):
    original = AccessService.authenticate
    def authenticate_then_revoke(service, token):
        user = original(service, token)
        with connect(scenario.url) as db:
            if change == "remove":
                db.execute("DELETE FROM course_members WHERE course_id = ? AND user_id = ?", (scenario.course.id, user.id))
            elif change == "demote":
                db.execute("UPDATE course_members SET role = 'student' WHERE course_id = ? AND user_id = ?", (scenario.course.id, user.id))
            else:
                db.execute("UPDATE users SET disabled_at = 'now' WHERE id = ?", (user.id,))
        return user
    monkeypatch.setattr(AccessService, "authenticate", authenticate_then_revoke)
    path = invite_path(scenario.course.id) + (":rotate" if method == "post" else "")
    response = getattr(scenario.client, method)(path, headers=auth(scenario.users["co_teacher"]))
    assert (response.status_code, response.json()["code"]) == (status, code)
    with connect(scenario.url) as db:
        assert db.execute("SELECT COUNT(*) FROM course_invite_codes").fetchone() == (0,)


@pytest.mark.parametrize("column,value,status,code", [
    ("disabled_at", "now", 401, "UNAUTHENTICATED"),
    ("role", "teacher", 403, "ROLE_FORBIDDEN"),
])
def test_join_rechecks_live_account_inside_transaction(scenario, monkeypatch, column, value, status, code):
    invitation = invite_code(scenario)
    original = AccessService.authenticate
    def authenticate_then_change(service, token):
        user = original(service, token)
        with connect(scenario.url) as db:
            db.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (value, user.id))
        return user
    monkeypatch.setattr(AccessService, "authenticate", authenticate_then_change)
    response = join(scenario, invitation)
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert get_member(scenario.url, scenario.course.id, scenario.users["newbie"].id) is None


def test_collision_retries_cannot_resurrect_any_historical_code(scenario, monkeypatch):
    service = module()
    candidates = iter(("ABC234", "DEF567", "ABC234", "DEF567", "GHJ789"))
    monkeypatch.setattr(service, "generate_code", lambda: next(candidates))
    assert invite_code(scenario) == "ABC234"
    assert scenario.client.post(invite_path(scenario.course.id) + ":rotate", headers=auth(scenario.users["teacher"])).json()["code"] == "DEF567"
    other = create_course(scenario.url, name="Other", description=None, creator_id=scenario.users["teacher"].id)
    assert invite_code(scenario, course_id=other.id) == "GHJ789"
    assert join(scenario, "ABC234").json()["code"] == "INVITE_CODE_INVALID"


def test_collision_exhaustion_rolls_back_rotation_and_hides_code(scenario, monkeypatch, caplog):
    service = module()
    old = invite_code(scenario)
    attempts = []
    def collide():
        attempts.append(1)
        return old
    monkeypatch.setattr(service, "generate_code", collide)
    response = scenario.client.post(invite_path(scenario.course.id) + ":rotate", headers=auth(scenario.users["teacher"]))
    assert (response.status_code, response.json()["code"]) == (500, "INTERNAL_ERROR")
    assert len(attempts) == 16
    assert old not in response.text and old not in caplog.text
    assert invite_code(scenario) == old
    assert join(scenario, old).status_code == 201


@pytest.mark.parametrize("method,suffix", [("get", ""), ("post", ":rotate")])
def test_collision_exhaustion_response_matches_generated_contract(scenario, monkeypatch, method, suffix):
    service = module()
    existing = invite_code(scenario)
    target = scenario.course
    if method == "get":
        target = create_course(scenario.url, name="Needs a first code", description=None, creator_id=scenario.users["teacher"].id)
    monkeypatch.setattr(service, "generate_code", lambda: existing)
    response = getattr(scenario.client, method)(
        invite_path(target.id) + suffix, headers=auth(scenario.users["teacher"]),
    )
    assert (response.status_code, response.json()["code"]) == (500, "INTERNAL_ERROR")
    path = "/api/v1/courses/{cid}/invite-code" + suffix
    declared = CONTRACT["paths"][path][method]["responses"]
    assert "500" in declared, "The generated contract must describe the actual collision failure"
    error_response = declared["500"]
    if "$ref" in error_response:
        error_response = CONTRACT["components"]["responses"][error_response["$ref"].rsplit("/", 1)[1]]
    Draft202012Validator({
        **error_response["content"]["application/json"]["schema"], "components": CONTRACT["components"],
    }).validate(response.json())
    assert "500" in scenario.app.openapi()["paths"][path][method]["responses"]


class Clock:
    now = 100.0
    def __call__(self):
        return self.now


def test_user_limit_counts_success_failure_and_duplicate_and_expires(scenario):
    service = module()
    clock = Clock()
    scenario.app.state.invite_limiter = service.InviteRateLimiter(clock=clock)
    code = invite_code(scenario)
    assert join(scenario, code).status_code == 201
    assert join(scenario, code).status_code == 409
    for _ in range(8):
        assert join(scenario, "AAAAAA").status_code == 404
    denied = join(scenario, code)
    assert (denied.status_code, denied.json()["code"]) == (429, "RATE_LIMITED")
    assert denied.headers["retry-after"] == "60"
    clock.now += 59.2
    assert join(scenario, code).headers["retry-after"] == "1"
    clock.now += 0.8
    assert join(scenario, code).status_code == 409


def test_malformed_authenticated_join_attempts_are_also_limited(scenario):
    for _ in range(10):
        response = scenario.client.post(JOIN, headers=auth(scenario.users["newbie"]), json={"code": "bad"})
        assert response.status_code == 422
    response = scenario.client.post(JOIN, headers=auth(scenario.users["newbie"]), json={"code": "bad"})
    assert (response.status_code, response.json()["code"]) == (429, "RATE_LIMITED")


def test_ip_limit_cannot_be_bypassed_by_forged_forwarded_header(scenario):
    for index in range(61):
        user = insert_account(scenario.url, account_id=uuid.uuid4().hex, username=f"s{index:03}", password_hash=VALID_HASH, role="student")
        response = scenario.client.post(JOIN, json={"code": "AAAAAA"}, headers={**auth(user), "X-Forwarded-For": f"192.0.2.{index}"})
        assert response.status_code == (404 if index < 60 else 429)
    assert response.json()["code"] == "RATE_LIMITED" and int(response.headers["retry-after"]) >= 1


def test_limiter_tracks_independent_user_and_ip_buckets():
    limiter = module().InviteRateLimiter()
    for index in range(10):
        assert limiter.acquire("same-user", f"ip-{index}") is None
    assert limiter.acquire("same-user", "new-ip") == 60
    assert limiter.acquire("different-user", "new-ip") is None
    for index in range(59):
        assert limiter.acquire(f"other-{index}", "new-ip") is None
    assert limiter.acquire("last-user", "new-ip") == 60


def test_limiter_capacity_fails_closed_without_evicting_live_restrictions():
    clock = Clock()
    limiter = module().InviteRateLimiter(clock=clock, capacity=3)
    for _ in range(10):
        assert limiter.acquire("one", "same-ip") is None
    assert limiter.acquire("two", "same-ip") is None
    assert limiter.acquire("three", "new-ip") == 60
    assert limiter.acquire("one", "same-ip") == 60
    clock.now += 60
    assert limiter.acquire("three", "new-ip") is None


def test_limiter_check_and_reserve_is_atomic_across_threads():
    limiter = module().InviteRateLimiter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: limiter.acquire("student", "ip"), range(40)))
    assert results.count(None) == 10
    assert all(value is None or value == 60 for value in results)


@pytest.mark.parametrize("first", ["rotate", "join"])
def test_join_and_rotation_follow_sqlite_transaction_order(scenario, monkeypatch, first):
    service, repo = module(), module("repositories")
    old = invite_code(scenario)
    entered = threading.Event()
    second_started = threading.Event()
    release = threading.Event()
    original = repo.transaction
    first_thread = []
    @contextmanager
    def controlled(url):
        is_first = threading.get_ident() == first_thread[0]
        if not is_first:
            second_started.set()
        with original(url) as tx:
            if is_first:
                entered.set()
                assert release.wait(5)
            yield tx
    monkeypatch.setattr(repo, "transaction", controlled)
    def run(kind, first_call=False):
        if first_call:
            first_thread.append(threading.get_ident())
        try:
            if kind == "join":
                return service.join_course(scenario.url, scenario.users["newbie"].id, old)
            return service.get_course_invite_code(scenario.url, scenario.users["teacher"].id, scenario.course.id, rotate=True)
        except AccessDenied as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(run, first, True)
        assert entered.wait(5)
        other = "join" if first == "rotate" else "rotate"
        second_future = pool.submit(run, other)
        try:
            assert second_started.wait(5)
        finally:
            release.set()
        results = {first: first_future.result(timeout=5), other: second_future.result(timeout=5)}
    if first == "rotate":
        assert results["join"] == "INVITE_CODE_INVALID"
        assert get_member(scenario.url, scenario.course.id, scenario.users["newbie"].id) is None
    else:
        assert results["join"].id == scenario.course.id
        assert get_member(scenario.url, scenario.course.id, scenario.users["newbie"].id) is not None
    assert results["rotate"].code != old


def test_concurrent_joins_create_one_membership_and_one_conflict(scenario):
    service = module()
    code = invite_code(scenario)
    def attempt(_):
        try:
            service.join_course(scenario.url, scenario.users["newbie"].id, code)
            return "created"
        except AccessDenied as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(outcomes) == ["ALREADY_MEMBER", "created"]
    with connect(scenario.url) as db:
        assert db.execute("SELECT COUNT(*) FROM course_members WHERE course_id = ? AND user_id = ?", (scenario.course.id, scenario.users["newbie"].id)).fetchone() == (1,)
