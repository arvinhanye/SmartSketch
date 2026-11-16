"""Live activity is derived from durable work without exposing model payloads."""

from datetime import datetime, timezone
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.repositories.courses import add_member, create_course
from app.repositories.extraction_checkpoints import write_checkpoint
from app.repositories.sqlite import connect
from app.services.auth import issue_access_token
from tests.backend.helpers.accounts import make_account
from tests.backend.helpers.tasks import insert_queued_task

NOW = 1_900_000_000
SECRET = "task-activity-test-key-0123456789abcdef"


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture
def activity_env(db_url, app_factory):
    users = {name: make_account(db_url, name, role) for name, role in (
        ("owner", "teacher"), ("cohost", "teacher"), ("student", "student"), ("outsider", "teacher"),
    )}
    course = create_course(db_url, name="test", description=None, creator_id=users["owner"].id)
    for name in ("cohost", "student"):
        add_member(db_url, course_id=course.id, user_id=users[name].id,
                   role=users[name].role, added_by=users["owner"].id)
    insert_queued_task(db_url, course.id, "task")
    with connect(db_url) as db:
        db.execute("UPDATE processing_tasks SET created_by=?, stage='extracting', attempt=2,"
                   " lease_owner='worker',lease_token='00000000000000000000000000000000',lease_expires_at=?,updated_at=? WHERE id='task'",
                   (users["owner"].id, NOW + 30, stamp(NOW - 200)))
    app = app_factory(SQLITE_URL=db_url, AUTH_JWT_SECRET=SECRET)
    app.state.auth_clock = lambda: NOW
    with TestClient(app) as client:
        yield dict(url=db_url, users=users, course=course.id, app=app, client=client)


def get_activity(env, who="owner", task="task"):
    headers = {}
    if who:
        user = env["users"][who]
        token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                                   issued_at=NOW, ttl_seconds=3600)
        headers["Authorization"] = f"Bearer {token}"
    return env["client"].get(f"/api/v1/tasks/{task}/activity", headers=headers)


def call(env, call_id, purpose, *, attempt=2, seconds=100, status="sent", course=None):
    with connect(env["url"]) as db:
        db.execute("INSERT INTO model_calls(call_id,course_id,task_id,purpose,task_attempt,"
                   "provider_role,is_repair,model_requested,input_tokens_est,max_output_tokens,status,created_at)"
                   " VALUES(?,?,'task',?,?,'primary',0,'private-model-name',1,1024,?,?)",
                   (call_id, course or env["course"], purpose, attempt, status, stamp(NOW - seconds)))


def units(env, task="task", revision="a", titles=("A", "A", "B")):
    revision_id = "rev_" + revision * 64
    document = "doc-" + task
    with connect(env["url"]) as db:
        db.execute("INSERT INTO material_revisions(revision_id,course_id,material_id,content_hash,parser_version)"
                   " VALUES(?,?,?,?,'fixture+chunk/1')", (revision_id, env["course"], document, "sha256:" + revision * 64))
        db.execute("INSERT INTO task_revisions(task_id,revision_id,course_id,material_id) VALUES(?,?,?,?)",
                   (task, revision_id, env["course"], document))
        for ordinal, title in enumerate(titles):
            db.execute("INSERT INTO chunks(chunk_id,revision_id,course_id,material_id,ordinal,text,text_sha256,section_titles,sources)"
                       " VALUES(?,?,?,?,?,'private source',?,?,?)", (f"{revision_id}-{ordinal}", revision_id,
                       env["course"], document, ordinal, "sha256:" + "c" * 64, json.dumps([title]), '[{}]'))
    return revision_id


def checkpoint(env, kind, unit_id, *, failed=False):
    with connect(env["url"]) as db:
        db.execute("BEGIN IMMEDIATE")
        write_checkpoint(db, task_id="task", course_id=env["course"], unit_kind=kind, unit_id=unit_id,
                         status="failed" if failed else "done", attempts=1,
                         error_code="EXTRACTION_INCOMPLETE" if failed else None,
                         result=None if failed else {})
        db.execute("COMMIT")


def test_waiting_relation_reports_durable_counts_and_actual_request_start(activity_env):
    env = activity_env
    revision = units(env)
    checkpoint(env, "chunk", revision + "-0")
    checkpoint(env, "chunk", revision + "-1")
    checkpoint(env, "chunk", revision + "-2", failed=True)
    section = "sec_" + hashlib.sha256(json.dumps([revision, ["A"]], ensure_ascii=False).encode()).hexdigest()
    checkpoint(env, "section", section)
    checkpoint(env, "chunk", "unknown-old-chunk")
    checkpoint(env, "section", "unknown-old-section")
    with connect(env["url"]) as db:
        decision = json.dumps(dict(left_id="a", right_id="b", status="complete", verdict="DIFFERENT"))
        db.execute("INSERT INTO task_section_decisions(task_id,course_id,section_id,input_digest,left_id,right_id,decision)"
                   " VALUES('task',?,'section','digest','a','b',?)", (env["course"], decision))
    # Same course, other task's chunks must never inflate this task's denominator.
    insert_queued_task(env["url"], env["course"], "other-task")
    units(env, task="other-task", revision="b", titles=("C", "D", "E"))
    call(env, "relations", "extract_normalized_relations", seconds=134)
    call(env, "semantic", "resolve_duplicate", seconds=5)
    call(env, "old-attempt", "extract_entities", attempt=1)
    call(env, "foreign-course", "extract_entities", course="foreign")
    response = get_activity(env)
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "relations"
    assert body["chunks"] == {"completed": 2, "failed": 1, "total": 3}
    assert body["sections"] == {"completed": 1, "failed": 0, "total": 2}
    assert body["disambiguation"] == {"completed": 1}
    assert body["active_requests"] == [
        {"purpose": "extract_normalized_relations", "count": 1, "started_at": stamp(NOW - 134)},
        {"purpose": "resolve_duplicate", "count": 1, "started_at": stamp(NOW - 5)},
    ]
    assert body["observed_at"] == stamp(NOW)
    assert body["worker_active"] is True
    assert body["attempt"] == 2
    assert body["progress"] == 0
    assert body["retry_at"] is None
    assert body["resumable"] is False
    assert "private" not in response.text
    assert "lease" not in response.text


@pytest.mark.parametrize("stage,flag,lease,phase", [
    ("extracting", 0, NOW - 1, "waiting"),
    ("extracting", 1, NOW + 30, "cancelling"),
    ("cancelled", 1, NOW + 30, "cancelled"),
    ("completed", 0, NOW + 30, "completed"),
])
def test_stale_or_finished_calls_are_not_presented_as_live(activity_env, stage, flag, lease, phase):
    env = activity_env
    call(env, "hung-old-call", "extract_normalized_relations")
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET stage=?,cancel_requested=?,lease_expires_at=? WHERE id='task'",
                   (stage, flag, lease))
    response = get_activity(env)
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == phase
    if stage in ("cancelled", "completed") or lease < NOW:
        assert body["active_requests"] == []
        assert body["worker_active"] is False
    else:
        assert body["active_requests"][0]["purpose"] == "extract_normalized_relations"


def test_retry_wait_is_distinct_from_an_active_request(activity_env):
    env = activity_env
    call(env, "previous", "extract_normalized_relations")
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,not_before=? WHERE id='task'", (NOW + 30,))
    body = get_activity(env).json()
    assert body["phase"] == "retrying"
    assert body["retry_at"] == stamp(NOW + 30)
    assert body["active_requests"] == []


def test_unknown_purpose_is_never_exposed(activity_env):
    call(activity_env, "secret-purpose", "private arbitrary request payload")
    response = get_activity(activity_env)
    assert response.status_code == 200
    assert response.json()["active_requests"] == []
    assert "private" not in response.text


@pytest.mark.parametrize("condition,value", [("cleanup_pending", 1), ("t6_seq", 1), ("lease_token", "b" * 32)])
def test_cancelled_task_is_not_resumable_until_technically_safe(activity_env, condition, value):
    env = activity_env
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id='task'")
    assert get_activity(env).json()["resumable"] is True
    with connect(env["url"]) as db:
        if condition == "lease_token":
            db.execute("UPDATE processing_tasks SET lease_token=?,lease_owner='worker',lease_expires_at=? WHERE id='task'", (value, NOW + 30))
        else:
            db.execute(f"UPDATE processing_tasks SET {condition}=? WHERE id='task'", (value,))
    assert get_activity(env).json()["resumable"] is False


def test_personal_resume_indicator_is_only_for_task_creator(activity_env):
    env = activity_env
    env["app"].state.settings = env["app"].state.settings.model_copy(update={"LLM_MODE": "personal"})
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id='task'")
    assert get_activity(env, "owner").json()["resumable"] is True
    assert get_activity(env, "cohost").json()["resumable"] is False


@pytest.mark.parametrize("who,status", [(None, 401), ("student", 403), ("outsider", 404)])
def test_activity_preserves_task_access_boundary(activity_env, who, status):
    response = get_activity(activity_env, who)
    assert response.status_code == status
    assert "active_requests" not in response.text


def test_completed_count_does_not_depend_on_new_model_calls(activity_env):
    env = activity_env
    call(env, "first", "resolve_duplicate", status="ok")
    before = get_activity(env)
    assert before.status_code == 200
    with connect(env["url"]) as db:
        decision = json.dumps(dict(left_id="a", right_id="b", status="complete", verdict="SAME"))
        db.execute("INSERT INTO task_section_decisions(task_id,course_id,section_id,input_digest,left_id,right_id,decision)"
                   " VALUES('task',?,'section','digest','a','b',?)", (env["course"], decision))
    assert get_activity(env).json()["disambiguation"]["completed"] == 1
    with connect(env["url"]) as db:
        assert db.execute("SELECT count(*) FROM model_calls WHERE task_id='task'").fetchone()[0] == 1


def test_empty_queued_task_has_a_real_activity_timestamp(activity_env):
    env = activity_env
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET stage='queued',attempt=0,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id='task'")
    response = get_activity(env)
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "queued"
    assert body["last_activity_at"] == stamp(NOW - 200)
    assert body["active_requests"] == []


def test_cancelled_extraction_requires_its_retained_revision(activity_env):
    env = activity_env
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET stage='cancelled',progress=0.58,cancel_requested=1,"
                   "lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id='task'")
    assert get_activity(env).json()["resumable"] is False
    units(env)
    assert get_activity(env).json()["resumable"] is True
