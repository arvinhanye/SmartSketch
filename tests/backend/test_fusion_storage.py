"""Atomic draft-head selection and immutable analysis plans."""
from dataclasses import replace
import sqlite3
import pytest
from app.repositories.neo4j import GraphScope, GraphScopeError, _parameters
from app.repositories.sqlite import connect
from app.repositories.courses import create_course
from tests.backend.helpers.accounts import make_account
from tests.backend.helpers.sqlite import migrated_database
from tests.backend.helpers.tasks import insert_queued_task


@pytest.fixture
def state(tmp_path):
    url = migrated_database(f"sqlite:///{tmp_path / 'fusion.sqlite3'}")
    user = make_account(url, "teacher", "teacher")
    course = create_course(url, name="test", description=None, creator_id=user.id)
    insert_queued_task(url, course.id, "task")
    return url, course.id


def test_draft_storage_binding_preserves_logical_visibility_and_reserved_parameters():
    scope = GraphScope("c", "draft", ("t",), storage_version_id="draftgen_one")
    params = _parameters("RETURN $course_id, $version_id, $effective_task_ids", scope,
                         dict(version_id="attacker", effective_task_ids=["other"]))
    assert scope.version_id == "draft" and params["version_id"] == "draftgen_one"
    assert params["effective_task_ids"] == ["t"]


@pytest.mark.parametrize("kwargs", [dict(version_id="draftgen_one"),
    dict(version_id="published", storage_version_id="draftgen_one"),
    dict(version_id="draft", storage_version_id="published")])
def test_physical_draft_cannot_be_used_as_a_published_scope(kwargs):
    with pytest.raises(GraphScopeError): GraphScope("c", **kwargs)


def test_new_course_uses_legacy_scope_and_records_current_revision(state):
    from app.repositories.fusion import read_draft_head, read_draft_scope
    url, cid = state
    with connect(url) as db:
        assert read_draft_scope(db, cid) == GraphScope(cid, "draft", ())
        head = read_draft_head(db, cid)
    assert head.storage_version_id == "draft" and head.draft_revision == 0


def test_legacy_scope_without_course_row_keeps_old_read_but_cannot_prepare_projection(state):
    from app.repositories.fusion import read_draft_head, read_draft_scope
    url, _ = state
    with connect(url) as db:
        assert read_draft_scope(db, "legacy-course") == GraphScope("legacy-course", "draft", ())
        with pytest.raises(LookupError): read_draft_head(db, "legacy-course")


def test_plan_payload_is_immutable_scoped_and_not_visible_before_activation(state):
    from app.repositories.fusion import put_plan, get_plan, read_draft_head, activate_plan
    url, cid = state
    with connect(url) as db:
        head = read_draft_head(db, cid)
        db.execute("BEGIN IMMEDIATE")
        plan = put_plan(db, course_id=cid, task_id="task", head=head, input_digest="hash",
                        payload=dict(groups=[["a", "b"]], before={}, after={}))
        db.execute("COMMIT")
        assert get_plan(db, "other", plan.plan_id) is None
        assert read_draft_head(db, cid) == head
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE fusion_plans SET payload='{}' WHERE plan_id=?", (plan.plan_id,))
        db.execute("BEGIN IMMEDIATE")
        activate_plan(db, plan, applied=True)
        assert read_draft_head(db, cid).storage_version_id == plan.storage_version_id
        db.execute("ROLLBACK")
        assert read_draft_head(db, cid) == head  # simulated SQLite/T6 failure


def test_stale_plan_cannot_switch_draft_head(state):
    from app.repositories.fusion import put_plan, read_draft_head, activate_plan, StaleFusionPlan
    url, cid = state
    with connect(url) as db:
        head = read_draft_head(db, cid)
        db.execute("BEGIN IMMEDIATE")
        plan = put_plan(db, course_id=cid, task_id="task", head=head, input_digest="hash", payload={})
        db.execute("UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?", (cid,))
        with pytest.raises(StaleFusionPlan): activate_plan(db, plan, applied=True)
        db.execute("COMMIT")
        assert read_draft_head(db, cid).storage_version_id == "draft"
