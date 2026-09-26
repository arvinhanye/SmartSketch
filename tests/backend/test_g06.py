"""G06 HTTP layer: ``listVersions``, ``rollbackVersion`` and ``publishGraph`` through the real app and SQLite.

The publish and rollback services are replaced by stubs here; their behaviour against a real Neo4j
is in ``tests/integration/test_g04.py`` / ``test_g05.py`` / ``test_g06.py``. The version list reads real
``graph_versions`` rows.
"""

from __future__ import annotations

import copy
import hashlib
import time
import uuid
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from app.api import versions as api
from app.main import create_app
from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.neo4j import RepositoryConnectionError
from app.repositories.sqlite import migrate
from app.repositories.versions import PublishInProgress
from app.services.auth import issue_access_token
from app.services.versions.publish import CourseBusy, PublishFailed, PublishOutcome
from app.services.versions.snapshot import BlockReason, SnapshotBlocked

ROOT = Path(__file__).resolve().parents[2]
SECRET = "g06-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
EXCLUDED = {"low_confidence_nodes": 1, "low_confidence_edges": 0, "cascaded_edges": 2}

_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {key: (value.replace("#/components/schemas/", "#/$defs/")
                      if key == "$ref" and isinstance(value, str) else _rewrite(value))
                for key, value in node.items()}
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def assert_schema(name, instance):
    jsonschema.Draft202012Validator({"$defs": _DEFS, "$ref": f"#/$defs/{name}"}).validate(instance)


def _account(url, username, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=username, password_hash=VALID_HASH, role=role)


class Scenario:
    def __init__(self, client, url, teacher, student, outsider, course, other, calls):
        self.client, self.url, self.calls = client, url, calls
        self.teacher, self.student, self.outsider, self.course, self.other = teacher, student, outsider, course, other

    def request(self, method, path, user):
        headers = {} if user is None else {"Authorization": f"Bearer {token(user)}"}
        return self.client.request(method, path, headers=headers)


def token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=int(time.time()),
                              ttl_seconds=3600)


OUTCOME = PublishOutcome(4, "01VERSION", "2026-09-26T10:00:00.000Z", False, 3, 2, EXCLUDED)


@pytest.fixture
def s(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    student = _account(url, "student1", "student")
    outsider = _account(url, "teacher2", "teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    other = create_course(url, name="他课", description=None, creator_id=outsider.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    calls: list[tuple] = []

    def fake_publish(ctx, course_id, *, created_by):
        calls.append(("publish", course_id, created_by))
        return OUTCOME

    def fake_rollback(ctx, course_id, version, *, created_by):
        calls.append(("rollback", course_id, version, created_by))
        return OUTCOME

    monkeypatch.setattr(api, "publish", fake_publish)
    monkeypatch.setattr(api, "rollback", fake_rollback)
    application = create_app()
    application.state.publish_context = object()  # 不连 Neo4j
    with TestClient(application) as client:
        yield Scenario(client, url, teacher, student, outsider, course, other, calls)


def commit(url, course_id, *, kind="publish", source_version=None, nodes=3, fail=False):
    attempt = versions.begin_attempt(url, course_id, kind=kind, created_by=None, lease_seconds=60,
                                     source_version=source_version)
    if kind == "publish":
        data = f'{{"snapshot_format":1,"tag":"{attempt.version_id}"}}'.encode()
        versions.record_snapshot(url, attempt.version_id, snapshot=data,
                                 digest="sha256:" + hashlib.sha256(data).hexdigest(), node_count=nodes, edge_count=2,
                                 excluded=EXCLUDED, draft_revision=0, task_watermark=0, embedding_space="fake/4")
    if fail:
        versions.fail_attempt(url, attempt.version_id, "x")
        return None
    versions.mark_materialized(url, attempt.version_id)
    current = versions.current_version(url, course_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id,
                                       expected_pointer=None if current is None else current.version_id,
                                       published_from_revision=0)


# ---------------------------------------------------------------- listVersions


def test_version_list_is_newest_first_and_marks_rollbacks(s):
    commit(s.url, s.course.id)
    commit(s.url, s.course.id, nodes=4)
    commit(s.url, s.course.id, fail=True)  # 失败尝试不进列表
    commit(s.url, s.course.id, kind="rollback", source_version=1)
    commit(s.url, s.other.id)
    response = s.request("GET", f"/api/v1/courses/{s.course.id}/versions", s.teacher)
    assert response.status_code == 200
    body = response.json()
    for item in body:
        assert_schema("GraphVersion", item)
    assert [(v["version"], v["kind"], v.get("source_version"), v["node_count"]) for v in body] == [
        (3, "rollback", 1, 3), (2, "publish", None, 4), (1, "publish", None, 3)]
    assert s.request("GET", f"/api/v1/courses/{s.other.id}/versions", s.outsider).json()[0]["version"] == 1


def test_empty_version_list(s):
    response = s.request("GET", f"/api/v1/courses/{s.course.id}/versions", s.teacher)
    assert (response.status_code, response.json()) == (200, [])


@pytest.mark.parametrize("method,path", [("GET", "/versions"), ("POST", "/versions/1/rollback"),
                                         ("POST", "/publish")])
def test_only_teachers_of_the_course(s, method, path):
    commit(s.url, s.course.id)
    url = f"/api/v1/courses/{s.course.id}{path}"
    assert s.request(method, url, None).status_code == 401
    assert s.request(method, url, s.student).status_code == 403
    assert s.request(method, url, s.outsider).status_code == 403
    assert s.calls == []


# ---------------------------------------------------------------- rollbackVersion


def test_rollback_success_returns_publish_result(s):
    commit(s.url, s.course.id)
    response = s.request("POST", f"/api/v1/courses/{s.course.id}/versions/1/rollback", s.teacher)
    assert response.status_code == 200
    assert_schema("PublishResult", response.json())
    assert response.json() == {"version": 4, "published_at": "2026-09-26T10:00:00Z", "unchanged": False,
                               "excluded": EXCLUDED, "stats": {"node_count": 3, "edge_count": 2}}
    assert s.calls == [("rollback", s.course.id, 1, s.teacher.id)]


def test_rollback_to_missing_failed_or_foreign_versions_is_404(s):  # PUB-25
    commit(s.url, s.course.id)
    commit(s.url, s.course.id, fail=True)
    commit(s.url, s.other.id)
    commit(s.url, s.other.id)
    for version in (2, 99):
        response = s.request("POST", f"/api/v1/courses/{s.course.id}/versions/{version}/rollback", s.teacher)
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert s.request("POST", f"/api/v1/courses/{s.course.id}/versions/0/rollback", s.teacher).status_code == 422
    assert s.calls == []


# ---------------------------------------------------------------- publishGraph 与错误映射


def test_publish_success_returns_publish_result(s):
    response = s.request("POST", f"/api/v1/courses/{s.course.id}/publish", s.teacher)
    assert response.status_code == 200
    assert_schema("PublishResult", response.json())
    assert s.calls == [("publish", s.course.id, s.teacher.id)]


def _raise(error):
    def action(*args, **kwargs):
        raise error
    return action


def _failed_with(cause):
    error = PublishFailed("P8", type(cause).__name__, "01X")
    error.__cause__ = cause
    return error


@pytest.mark.parametrize("error,status,code,schema", [
    (SnapshotBlocked([BlockReason("cycle", cycle=("a", "b", "a")), BlockReason("empty_graph")]), 409,
     "PUBLISH_BLOCKED", "PublishBlockedError"),
    (PublishInProgress(), 409, "PUBLISH_IN_PROGRESS", "PublishConflictError"),
    (CourseBusy("persisting"), 409, "COURSE_BUSY", "PublishConflictError"),
    (_failed_with(RepositoryConnectionError()), 503, "STORAGE_UNAVAILABLE", "Error"),
    (_failed_with(RuntimeError("boom")), 500, "INTERNAL_ERROR", "Error"),
])
def test_publish_errors_map_to_the_contract(s, monkeypatch, error, status, code, schema):
    monkeypatch.setattr(api, "publish", _raise(error))
    response = s.request("POST", f"/api/v1/courses/{s.course.id}/publish", s.teacher)
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert_schema(schema, response.json())
    if code == "COURSE_BUSY":
        assert response.json()["details"] == {"holder": "persisting"}
    if code == "PUBLISH_BLOCKED":
        assert [r["kind"] for r in response.json()["details"]["reasons"]] == ["cycle", "empty_graph"]
    assert "boom" not in response.text


def test_rollback_conflict_and_failure(s, monkeypatch):
    commit(s.url, s.course.id)
    path = f"/api/v1/courses/{s.course.id}/versions/1/rollback"
    monkeypatch.setattr(api, "rollback", _raise(PublishInProgress()))
    assert s.request("POST", path, s.teacher).json()["code"] == "PUBLISH_IN_PROGRESS"
    monkeypatch.setattr(api, "rollback", _raise(_failed_with(RuntimeError("x"))))
    assert s.request("POST", path, s.teacher).status_code == 500


def test_neo4j_unreachable_when_building_the_context_is_503(s, monkeypatch):
    s.client.app.state.publish_context = None

    def unreachable(settings):
        raise RepositoryConnectionError()

    monkeypatch.setattr(api.Neo4jRepository, "from_settings", staticmethod(unreachable))
    response = s.request("POST", f"/api/v1/courses/{s.course.id}/publish", s.teacher)
    assert (response.status_code, response.json()["code"]) == (503, "STORAGE_UNAVAILABLE")
    assert s.calls == []
