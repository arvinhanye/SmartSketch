"""Cancelled tasks resume in place without discarding completed work or billing history."""
import base64
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.model_configs import bind_task, save_config, scrub_terminal_bindings
from app.repositories.sqlite import connect
from app.repositories import task_leases
from app.services.auth import issue_access_token
from app.services.credentials import CredentialCipher
from app.services.task_state import Applied, Rejected, TaskState, TransitionEvent, apply_event
from tests.backend.helpers.tasks import insert_queued_task
from tests.backend.test_e12 import storage

SECRET = 'resume-tests-auth-key-01234567890123456789'
OWNER = 'owner'.ljust(32, '0')
ROOT_KEY = b'r' * 32
ROOT_KEY_TEXT = base64.urlsafe_b64encode(ROOT_KEY).decode()


@pytest.fixture
def env(db_url, app_factory):
    users = {}
    for name, role in [('owner', 'teacher'), ('teacher', 'teacher'), ('student', 'student'), ('outsider', 'teacher')]:
        users[name] = insert_account(db_url, account_id=name.ljust(32, '0'), username=name,
                                     password_hash='$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA', role=role)
    course = create_course(db_url, name='A', description=None, creator_id=OWNER)
    for name in ('teacher', 'student'):
        add_member(db_url, course_id=course.id, user_id=users[name].id, role=users[name].role, added_by=OWNER)
    insert_queued_task(db_url, course.id, 'task')
    with connect(db_url) as db:
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1,created_by=? WHERE id='task'", (OWNER,))
    app = app_factory(SQLITE_URL=db_url, AUTH_JWT_SECRET=SECRET, LLM_MODE='fake')
    app.state.auth_clock = lambda: 1_900_000_000
    with TestClient(app) as client:
        yield dict(url=db_url, client=client, app=app, course=course.id, users=users)


def post(env, user='owner'):
    headers = {}
    if user is not None:
        token = issue_access_token(user_id=env['users'][user].id, role=env['users'][user].role,
            secret=SECRET.encode(), issued_at=1_900_000_000, ttl_seconds=3600)
        headers['Authorization'] = 'Bearer ' + token
    return env['client'].post('/api/v1/tasks/task/resume', headers=headers)


def row(env):
    with connect(env['url']) as db:
        db.row_factory = sqlite3.Row
        return dict(db.execute("SELECT * FROM processing_tasks WHERE id='task'").fetchone())


def seed_extraction(env, *, progress=.58, attempt=2):
    revision = 'rev_' + 'a' * 64
    with connect(env['url']) as db:
        db.execute("UPDATE processing_tasks SET progress=?,attempt=? WHERE id='task'", (progress, attempt))
        db.execute("INSERT INTO material_revisions(revision_id,course_id,material_id,content_hash,parser_version) VALUES(?,?,?,'sha256:' || ?, 'p+chunk/c@1500-0')",
                   (revision, env['course'], 'doc-task', 'a'*64))
        db.execute('INSERT INTO task_revisions(task_id,revision_id,course_id,material_id) VALUES(?,?,?,?)',
                   ('task', revision, env['course'], 'doc-task'))
        db.execute("INSERT INTO task_chunk_checkpoints(task_id,course_id,unit_kind,unit_id,status,attempts,result) VALUES('task',?,'chunk','chunk','done',1,?)",
                   (env['course'], json.dumps({'entities': []})))
        decision = dict(left_id='a', right_id='b', status='complete', verdict='DIFFERENT')
        db.execute("INSERT INTO task_section_decisions(task_id,course_id,section_id,input_digest,left_id,right_id,decision) VALUES('task',?,'s','d','a','b',?)",
                   (env['course'], json.dumps(decision)))


@pytest.mark.parametrize('progress,stage', [(0, 'queued'), (.05, 'parsing'), (.1, 'extracting'), (.58, 'extracting'), (.6, 'merging'), (.8, 'merging')])
def test_explicit_resume_event_preserves_progress_and_clears_cancel(progress, stage):
    out = apply_event(TaskState('cancelled', progress, True), TransitionEvent('resume'))
    assert isinstance(out, Applied)
    assert out.state == TaskState(stage, progress, False)


@pytest.mark.parametrize('stage,progress', [('queued', 0), ('extracting', .4), ('persisting', .8), ('awaiting_review', .95), ('completed', 1)])
def test_resume_event_cannot_rewind_other_stages(stage, progress):
    assert isinstance(apply_event(TaskState(stage, progress), TransitionEvent('resume')), Rejected)


def test_resume_queued_cancel_keeps_material_and_same_task(env):
    response = post(env)
    assert response.status_code == 200, response.text
    assert response.json()['id'] == 'task'
    assert response.json()['stage'] == 'queued'
    assert response.json()['cancel_requested'] is False
    assert row(env)['resume_count'] == 1
    with connect(env['url']) as db:
        assert db.execute('SELECT count(*) FROM processing_tasks').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM materials').fetchone()[0] == 1


def test_resume_preserves_completed_artifacts_and_renews_automatic_attempt_budget(env):
    seed_extraction(env, attempt=3)
    response = post(env)
    assert response.status_code == 200, response.text
    current = row(env)
    assert (current['stage'], current['progress'], current['attempt'], current['resume_attempt_base']) == ('extracting', .58, 3, 3)
    with connect(env['url']) as db:
        assert db.execute('SELECT count(*) FROM task_chunk_checkpoints').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM task_section_decisions').fetchone()[0] == 1
    lease = task_leases.claim_next(env['url'], owner='new', lease_seconds=60, max_attempts=3)
    assert lease and lease.attempt == 4 and lease.stage == 'extracting'
    released = task_leases.release_after_transient_failure(env['url'], 'task', lease.token,
                                                         code='LLM_UNAVAILABLE', max_attempts=3)
    assert released.status == 'released'
    with connect(env['url']) as db:
        wait = db.execute("SELECT not_before-unixepoch() FROM processing_tasks WHERE id='task'").fetchone()[0]
    assert 29 <= wait <= 30


def test_resumed_attempt_budget_is_still_bounded(env):
    seed_extraction(env, attempt=9)
    assert post(env).status_code == 200
    for attempt in (10, 11, 12):
        with connect(env['url']) as db:
            db.execute("UPDATE processing_tasks SET not_before=0 WHERE id='task'")
        lease = task_leases.claim_next(env['url'], owner='w', lease_seconds=60, max_attempts=3)
        assert lease and lease.attempt == attempt
        result = task_leases.release_after_transient_failure(env['url'], 'task', lease.token,
                                                           code='LLM_UNAVAILABLE', max_attempts=3)
        assert result.status == ('failed' if attempt == 12 else 'released')
    assert row(env)['stage'] == 'failed'


def test_expired_resumed_lease_uses_current_run_attempt_budget(env):
    seed_extraction(env, attempt=5)
    assert post(env).status_code == 200
    lease = task_leases.claim_next(env['url'], owner='w', lease_seconds=60, max_attempts=3)
    with connect(env['url']) as db:
        db.execute("UPDATE processing_tasks SET lease_expires_at=0 WHERE id='task'")
    result = task_leases.reclaim_expired(env['url'], max_attempts=3)
    assert not result.failed
    next_lease = task_leases.claim_next(env['url'], owner='w2', lease_seconds=60, max_attempts=3)
    assert next_lease and next_lease.attempt == 7 and next_lease.token != lease.token
    with pytest.raises(task_leases.LeaseLost):
        with task_leases.leased_transaction(env['url'], 'task', lease.token):
            pass


@pytest.mark.parametrize('change,reason', [
    ("stage='extracting',cancel_requested=1,progress=.4", 'not_cancelled'),
    ("lease_token='00000000000000000000000000000000',lease_owner='old',lease_expires_at=0", 'worker_active'),
    ("cleanup_pending=1", 'artifacts_missing'),
    ("t6_seq=1", 'artifacts_missing'),
    ("progress=.58", 'artifacts_missing'),
])
def test_unready_resume_is_rejected_without_any_write(env, change, reason):
    with connect(env['url']) as db:
        db.execute('UPDATE processing_tasks SET ' + change + " WHERE id='task'")
    before = row(env)
    response = post(env)
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'TASK_NOT_RESUMABLE'
    assert response.json()['details']['reason'] == reason
    assert row(env) == before


def test_double_resume_cannot_start_twice(env):
    assert post(env).status_code == 200
    before = row(env)
    again = post(env)
    assert again.status_code == 409
    assert again.json()['details']['reason'] == 'not_cancelled'
    assert row(env) == before


def test_resume_responses_use_generated_contract_models(env):
    from app.schemas.contracts import _module
    response = post(env)
    assert response.status_code == 200
    assert _module.Task.model_validate(response.json()).root.stage == 'queued'
    rejected = post(env)
    assert rejected.status_code == 409
    assert _module.TaskNotResumableError.model_validate(rejected.json()).details.reason.value == 'not_cancelled'
    schema = env['app'].openapi()
    operation = schema['paths']['/api/v1/tasks/{tid}/resume']['post']
    assert operation['operationId'] == 'resumeTask'
    assert 'TaskNotResumableError' in schema['components']['schemas']
    assert 'ModelConfigRequiredError' in schema['components']['schemas']


@pytest.mark.parametrize('user,status', [(None, 401), ('student', 403), ('outsider', 404)])
def test_resume_authorization_matrix(env, user, status):
    before = row(env)
    assert post(env, user).status_code == status
    assert row(env) == before


def personal(env):
    env['app'].state.settings = env['app'].state.settings.model_copy(update={
        'LLM_MODE': 'personal', 'MODEL_CREDENTIAL_KEY': __import__('pydantic').SecretStr(ROOT_KEY_TEXT)})
    cipher = CredentialCipher(ROOT_KEY)
    save_config(env['url'], user_id=OWNER, base_url='https://provider.example/v1', model='m',
                sealed=cipher.seal(OWNER, 'first-key'), key_hint='key')
    with connect(env['url']) as db:
        assert bind_task(db, task_id='task', user_id=OWNER)
    scrub_terminal_bindings(env['url'])
    return cipher


def test_personal_resume_rehydrates_scrubbed_key_and_accepts_key_rotation(env):
    cipher = personal(env)
    save_config(env['url'], user_id=OWNER, base_url='https://provider.example/v1', model='m',
                sealed=cipher.seal(OWNER, 'rotated-key'), key_hint='key')
    assert post(env).status_code == 200
    from app.repositories.model_configs import get_binding
    binding = get_binding(env['url'], 'task')
    assert cipher.open(OWNER, binding.sealed) == 'rotated-key'
    assert binding.scrub_reason is None
    assert scrub_terminal_bindings(env['url']) == 0


@pytest.mark.parametrize('field,value', [('model', 'different'), ('base_url', 'https://other.example/v1'), ('disable_thinking', True)])
def test_personal_resume_refuses_changed_semantic_configuration(env, field, value):
    cipher = personal(env)
    args = dict(user_id=OWNER, base_url='https://provider.example/v1', model='m',
                sealed=cipher.seal(OWNER, 'key'), key_hint='key', disable_thinking=False)
    args[field] = value
    save_config(env['url'], **args)
    before = row(env)
    result = post(env)
    assert result.status_code == 409
    assert result.json()['details']['reason'] == 'model_config_changed'
    assert row(env) == before


def test_personal_resume_requires_original_creator_and_current_configuration(env):
    personal(env)
    assert post(env, 'teacher').status_code == 403
    with connect(env['url']) as db:
        db.execute("DELETE FROM user_model_configs WHERE user_id=?", (OWNER,))
    before = row(env)
    response = post(env)
    assert response.status_code == 409
    assert response.json()['code'] == 'MODEL_CONFIG_REQUIRED'
    assert row(env) == before


def test_personal_resume_never_rehydrates_unreadable_credentials(env):
    personal(env)
    with connect(env['url']) as db:
        db.execute("UPDATE user_model_configs SET key_ciphertext=? WHERE user_id=?", (b'broken', OWNER))
    before = row(env)
    response = post(env)
    assert response.status_code == 409
    assert response.json()['code'] == 'MODEL_CONFIG_REQUIRED'
    assert row(env) == before


def test_resume_migration_rollback_preserves_task_and_caches(env):
    seed_extraction(env)
    assert post(env).status_code == 200
    with connect(env['url']) as db:
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1 WHERE id='task'")
    migration = Path(__file__).resolve().parents[2] / 'src/backend/migrations/025_task_resume.sql'
    statements = [line.removeprefix('-- ROLLBACK: ') for line in migration.read_text().splitlines() if line.startswith('-- ROLLBACK: ')]
    with connect(env['url']) as db:
        db.execute('BEGIN IMMEDIATE')
        for statement in statements:
            db.execute(statement)
        db.commit()
        columns = {r[1] for r in db.execute('PRAGMA table_info(processing_tasks)')}
        assert 'resume_attempt_base' not in columns and 'resume_count' not in columns
        assert db.execute('SELECT count(*) FROM task_section_decisions').fetchone()[0] == 1


def test_resume_migration_refuses_rollback_while_resumed_task_waits_without_lease(env):
    assert post(env).status_code == 200
    migration = Path(__file__).resolve().parents[2] / 'src/backend/migrations/025_task_resume.sql'
    statements = [line.removeprefix('-- ROLLBACK: ') for line in migration.read_text().splitlines() if line.startswith('-- ROLLBACK: ')]
    with connect(env['url']) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            with pytest.raises(sqlite3.IntegrityError):
                for statement in statements:
                    db.execute(statement)
        finally:
            db.rollback()
        assert db.execute("SELECT resume_count FROM processing_tasks WHERE id='task'").fetchone() == (1,)


@pytest.mark.parametrize('cancel_during', ['extract_normalized_relations', 'resolve_duplicate'])
def test_cancel_resume_real_pipeline_reuses_every_completed_result(db_url, storage, cancel_during):
    from app.config import Settings
    from app.services.ai.fake import FakeModelClient
    from app.services.task_cancel import cancel_task
    from app.services.task_resume import resume_task
    from app.workers.extract_task import ExtractLimits, ExtractStatus, run_extract_stage
    from tests.backend.test_e12 import _extracting
    from tests.backend.test_section_decision_worker import kit, response

    lease, _ = _extracting(db_url, storage, '原文说明三个不同概念。'.encode())
    cancelled = False
    def first_response(request):
        nonlocal cancelled
        if request.purpose == cancel_during and not cancelled:
            cancel_task(db_url, lease.task_id, course_id=lease.course_id)
            cancelled = True
        return response(request)
    first = FakeModelClient(responder=first_response)
    outcome = run_extract_stage(db_url, lease, toolkit=kit(db_url, first), limits=ExtractLimits(max_attempts=3))
    assert outcome.status == ExtractStatus.CANCELLED
    with connect(db_url) as db:
        assert db.execute('SELECT count(*) FROM task_section_decisions').fetchone()[0] == (3 if cancel_during == 'extract_normalized_relations' else 1)

    snapshot = resume_task(Settings(SQLITE_URL=db_url), lease.task_id, course_id=lease.course_id, user_id='teacher')
    assert snapshot.id == lease.task_id and snapshot.stage == 'extracting'
    next_lease = task_leases.claim_next(db_url, owner='resume-worker', lease_seconds=60, max_attempts=3)
    assert next_lease and next_lease.attempt == 2
    second = FakeModelClient(responder=response)
    outcome = run_extract_stage(db_url, next_lease, toolkit=kit(db_url, second), limits=ExtractLimits(max_attempts=3))
    assert outcome.status == ExtractStatus.ADVANCED and outcome.stage == 'merging'
    purposes = [call.request.purpose for call in second.calls]
    if cancel_during == 'extract_normalized_relations':
        assert purposes == []
    else:
        assert purposes == ['resolve_duplicate', 'resolve_duplicate', 'extract_normalized_relations']
