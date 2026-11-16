"""Global pair progress is durable, scoped, and distinct from request counts."""

import pytest

from app.repositories import fusion_decisions
from app.repositories.sqlite import connect
from tests.backend.test_task_activity import NOW, activity_env, call, get_activity


def test_old_task_without_global_plan_reports_unknown_not_zero(activity_env):
    response = get_activity(activity_env)
    assert response.status_code == 200
    assert "global_disambiguation" in response.json()
    assert response.json()["global_disambiguation"] is None


def test_merging_semantic_request_reports_disambiguation_phase(activity_env):
    env = activity_env
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET stage='merging',progress=0.6 WHERE id='task'")
    call(env, "global-call", "resolve_duplicate")
    response = get_activity(env)
    assert response.status_code == 200
    assert response.json()["phase"] == "disambiguating"
    assert response.json()["global_disambiguation"] is None


def saved_global_work(env):
    pairs = [dict(left_id=a, right_id=b, code=None) for a, b in
             (("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d"))]
    scope = dict(course_id=env["course"], task_id="task", input_digest="private-input-digest")
    with connect(env["url"]) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE processing_tasks SET stage='merging',progress=0.6,attempt=1 WHERE id='task'")
        fusion_decisions.initialize_plan(db, **scope, pairs=pairs, total_possible=10, attempt=1)

        def result(index, status, attempt):
            a, b = pairs[index]["left_id"], pairs[index]["right_id"]
            fusion_decisions.mark_running(db, **scope, left_id=a, right_id=b, attempt=attempt)
            decision = dict(left_id=a, right_id=b, status=status)
            if status == "complete":
                decision["verdict"] = "UNCERTAIN"
            fusion_decisions.put_result(db, **scope, decision=decision, attempt=attempt)

        result(0, "complete", 1)
        db.execute("UPDATE processing_tasks SET attempt=2 WHERE id='task'")
        fusion_decisions.initialize_plan(db, **scope, pairs=pairs, total_possible=10, attempt=2)
        result(1, "complete", 2)
        result(2, "failed", 2)
        result(3, "deferred", 2)
        fusion_decisions.mark_running(db, **scope, left_id="b", right_id="d", attempt=2)
        db.execute("COMMIT")


def test_global_counts_distinguish_complete_reused_failed_and_unselected(activity_env):
    env = activity_env
    saved_global_work(env)
    call(env, "first-request", "resolve_duplicate")
    call(env, "second-request", "resolve_duplicate")
    body = get_activity(env).json()
    progress = body["global_disambiguation"]
    assert progress is not None
    assert {key: value for key, value in progress.items() if key != "updated_at"} == dict(
        total=6, total_possible=10, completed=2, failed=1, deferred=1,
        reused=1, inflight=1, pending=1, phase="running",
    )
    assert body["active_requests"][0]["count"] == 2  # Physical requests are not pair progress.
    assert "private-input-digest" not in str(body)
    assert body["last_activity_at"] >= progress["updated_at"]


@pytest.mark.parametrize("stop", ["cancelled", "expired", "cancelling"])
def test_stopped_global_work_preserves_results_without_false_inflight(activity_env, stop):
    env = activity_env
    saved_global_work(env)
    with connect(env["url"]) as db:
        if stop == "expired":
            db.execute("UPDATE processing_tasks SET lease_expires_at=? WHERE id='task'", (NOW - 1,))
        elif stop == "cancelled":
            db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1,"
                       "lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL WHERE id='task'")
        else:
            db.execute("UPDATE processing_tasks SET cancel_requested=1 WHERE id='task'")
    body = get_activity(env).json()
    progress = body["global_disambiguation"]
    assert progress is not None
    assert (progress["completed"], progress["reused"], progress["inflight"], progress["pending"]) == (2, 1, 0, 2)


def test_old_attempt_plan_is_not_reported_as_current_progress(activity_env):
    env = activity_env
    saved_global_work(env)
    with connect(env["url"]) as db:
        db.execute("UPDATE processing_tasks SET attempt=3 WHERE id='task'")
    assert get_activity(env).json()["global_disambiguation"] is None


def test_new_digest_plan_does_not_inherit_completed_old_counts(activity_env):
    env = activity_env
    saved_global_work(env)
    with connect(env["url"]) as db:
        db.execute("BEGIN IMMEDIATE")
        fusion_decisions.initialize_plan(db, course_id=env["course"], task_id="task",
            input_digest="new-input", pairs=[dict(left_id="x", right_id="y", code=None)],
            total_possible=3, attempt=2)
        db.execute("COMMIT")
    progress = get_activity(env).json()["global_disambiguation"]
    assert progress is not None
    assert (progress["total"], progress["completed"], progress["pending"], progress["reused"]) == (1, 0, 1, 0)
