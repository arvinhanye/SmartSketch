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


def _deletion_plan(url, cid, task_id='task', *, state='prepared', applied=False, audit=False):
    from app.repositories.fusion import put_plan, read_draft_head
    with connect(url) as db:
        db.execute('BEGIN IMMEDIATE')
        plan = put_plan(db, course_id=cid, task_id=task_id, head=read_draft_head(db, cid),
                        input_digest=task_id, payload=dict(groups=[], before={}, after={}))
        db.execute('UPDATE fusion_plans SET state=?,applied=? WHERE plan_id=?',
                   (state, int(applied), plan.plan_id))
        if audit:
            actor = db.execute('SELECT teacher_id FROM courses WHERE id=?', (cid,)).fetchone()[0]
            db.execute('INSERT INTO fusion_undos(undo_id,course_id,plan_id,group_id,actor_id,payload) '
                       'VALUES(?,?,?,?,?,?)', ('undo-'+task_id, cid, plan.plan_id, 'group', actor, '{}'))
        db.execute('COMMIT')
    return plan


@pytest.mark.parametrize('stage,plan_state', [('cancelled', 'prepared'), ('failed', 'prepared'),
                                             ('failed', 'skipped')])
def test_deleting_uncontributed_material_cleans_only_its_unapplied_plans(state, stage, plan_state):
    from app.repositories.materials import delete_material, MaterialDeleted
    url, cid = state
    plan = _deletion_plan(url, cid, state=plan_state)
    insert_queued_task(url, cid, 'other-material')
    other = _deletion_plan(url, cid, 'other-material')
    with connect(url) as db:
        actor = db.execute('SELECT teacher_id FROM courses WHERE id=?', (cid,)).fetchone()[0]
    another_course = create_course(url, name='other', description=None, creator_id=actor)
    insert_queued_task(url, another_course.id, 'other-course')
    foreign = _deletion_plan(url, another_course.id, 'other-course')
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage=?,cancel_requested=?,cleanup_pending=0,"
                   "error_code=?,error_message=? WHERE id='task'",
                   (stage, int(stage == 'cancelled'), 'INTERNAL_ERROR' if stage == 'failed' else None,
                    'fixture failure' if stage == 'failed' else None))
    assert isinstance(delete_material(url, 'doc-task', course_id=cid), MaterialDeleted)
    with connect(url) as db:
        assert {r[0] for r in db.execute('SELECT plan_id FROM fusion_plans')} == {other.plan_id, foreign.plan_id}
        assert db.execute("SELECT id FROM processing_tasks WHERE id='task'").fetchall() == []
        assert db.execute("SELECT id FROM materials WHERE id='doc-task'").fetchall() == []


@pytest.mark.parametrize('stage,cleanup,reason', [('merging', 0, 'processing'),
    ('failed', 1, 'cleanup_pending'), ('awaiting_review', 0, 'contributed'), ('completed', 0, 'contributed')])
def test_material_deletion_guards_preserve_fusion_plans(state, stage, cleanup, reason):
    from app.repositories.materials import delete_material, MaterialNotDeletable
    url, cid = state
    plan = _deletion_plan(url, cid)
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage=?,cleanup_pending=?,error_code=?,error_message=? WHERE id='task'",
                   (stage, cleanup, 'INTERNAL_ERROR' if stage == 'failed' else None,
                    'fixture failure' if stage == 'failed' else None))
    result = delete_material(url, 'doc-task', course_id=cid)
    assert isinstance(result, MaterialNotDeletable) and result.reason == reason
    with connect(url) as db:
        assert db.execute('SELECT plan_id FROM fusion_plans').fetchall() == [(plan.plan_id,)]


@pytest.mark.parametrize('plan_state,applied,audit', [('committed', False, False),
    ('prepared', True, False), ('prepared', False, True)])
def test_material_deletion_refuses_plan_history_even_if_task_is_marked_failed(state, plan_state, applied, audit):
    from app.repositories.fusion import put_plan, read_draft_head
    from app.repositories.materials import delete_material, MaterialNotDeletable
    url, cid = state
    plan = _deletion_plan(url, cid, state=plan_state, applied=applied, audit=audit)
    with connect(url) as db:
        db.execute('BEGIN IMMEDIATE')
        safe = put_plan(db, course_id=cid, task_id='task', head=read_draft_head(db, cid),
                        input_digest='other-attempt', payload={})
        db.execute("UPDATE processing_tasks SET stage='failed',error_code='INTERNAL_ERROR',"
                   "error_message='fixture failure' WHERE id='task'")
        db.execute('COMMIT')
    result = delete_material(url, 'doc-task', course_id=cid)
    assert isinstance(result, MaterialNotDeletable) and result.reason == 'contributed'
    with connect(url) as db:
        assert {r[0] for r in db.execute('SELECT plan_id FROM fusion_plans')} == {plan.plan_id, safe.plan_id}
        assert db.execute('SELECT count(*) FROM fusion_undos').fetchone()[0] == int(audit)


def test_other_course_material_lookup_never_removes_a_fusion_plan(state):
    from app.repositories.materials import delete_material
    url, cid = state
    plan = _deletion_plan(url, cid)
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage='failed',error_code='INTERNAL_ERROR',"
                   "error_message='fixture failure' WHERE id='task'")
    assert delete_material(url, 'doc-task', course_id='another-course') is None
    with connect(url) as db:
        assert db.execute('SELECT plan_id FROM fusion_plans').fetchall() == [(plan.plan_id,)]
