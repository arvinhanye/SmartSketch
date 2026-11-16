"""Global semantic work is bounded, durable per pair, and safe to resume."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
import threading

import pytest

from app.config import Settings
from app.repositories import task_leases
from app.repositories.sqlite import connect
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import CallAttribution
from app.services.credentials import CredentialUnavailable
from app.services.fusion.judge import FusionEntity, FusionEvidence
from app.services.fusion.resolution import SemanticDecision, SemanticResolver
from app.services.task_cancel import cancel_task
from app.services.task_resume import resume_task
from app.workers.extraction.units import _AttemptClient
from tests.backend.helpers.tasks import insert_queued_task
from tests.backend.test_c10 import _sql
from tests.backend.test_disambiguation_generation import different
from tests.backend.test_e12 import _policy


@pytest.fixture
def state(db_url):
    insert_queued_task(db_url, 'course', 'task')
    lease = task_leases.claim_next(db_url, owner='first', lease_seconds=600, max_attempts=3)
    _sql(db_url, "UPDATE processing_tasks SET stage='merging',progress=.65 WHERE id='task'")
    # Resume requires the immutable parsed revision link.
    revision = 'rev_' + 'a'*64
    with connect(db_url) as db:
        db.execute("INSERT INTO material_revisions(revision_id,course_id,material_id,content_hash,parser_version) VALUES(?, 'course','doc-task',?,'p+chunk/c@60-0')", (revision, 'sha256:'+'a'*64))
        db.execute("INSERT INTO task_revisions(task_id,revision_id,course_id,material_id) VALUES('task',?,'course','doc-task')", (revision,))
    return db_url, replace(lease, stage='merging', progress=.65)


def work(count=6):
    from app.workers.fusion_decisions import DecisionWork
    def entity(key):
        return FusionEntity(key, 'course', key, 'concept', '定义', (
            FusionEvidence('source-'+key, 'course', 'doc-task', 'revision', 'chunk', '原文'),))
    return [DecisionWork('a', f'b{i}', entity('a'), entity(f'b{i}')) for i in range(count)]


def run(url, lease, client, *, digest='digest', concurrency=2, guard=None, items=None):
    from app.workers.fusion_decisions import FusionDecisionCache, run_decisions
    cache = FusionDecisionCache(url, lease, credential_guard=guard)
    bound = _AttemptClient(_policy(url, client), CallAttribution(course_id='course', task_id='task', task_attempt=lease.attempt), guard=cache.request_guard)
    resolver = SemanticResolver(bound, model='m')
    return run_decisions(cache, digest, work() if items is None else items, resolver=resolver,
                         total_possible=15, max_concurrency=concurrency)


def progress(url):
    from app.repositories.fusion_decisions import read_progress
    with connect(url) as db:
        return read_progress(db, course_id='course', task_id='task')


def test_global_progress_is_unknown_until_the_plan_has_been_saved(state):
    assert progress(state[0]) is None


def test_bounded_physical_calls_report_pair_progress_and_return_stable_order(state):
    url, lease = state
    release, started = threading.Event(), threading.Event()
    lock = threading.Lock()
    active = peak = count = 0
    def respond(request):
        nonlocal active, peak, count
        with lock:
            active += 1; count += 1; peak = max(peak, active)
            if count == 3: started.set()
        assert release.wait(5)
        with lock: active -= 1
        return different(request)
    client = FakeModelClient(responder=respond)
    with ThreadPoolExecutor(max_workers=1) as driver:
        pending = driver.submit(run, url, lease, client, concurrency=3)
        try:
            assert started.wait(5)
            report = progress(url)
            assert (report['total'], report['inflight'], report['pending']) == (6, 3, 3)
            assert report['completed'] == 0
        finally:
            release.set()
        result = pending.result(5)
    assert peak == 3 and len(client.calls) == 6
    assert [d.right_id for d in result] == ['b0','b1','b2','b3','b4','b5']
    assert progress(url)['completed'] == 6
    assert progress(url)['phase'] == 'complete'
    with connect(url) as db:
        assert db.execute("SELECT count(DISTINCT call_seq) FROM model_calls WHERE purpose='resolve_duplicate'").fetchone()[0] == 6


def test_cancel_keeps_inflight_complete_pairs_then_real_resume_calls_only_unfinished(state):
    from app.workers.fusion_decisions import FusionCancelled
    from app.workers.persist_graph import run_merge_stage
    url, lease = state
    release, started = threading.Event(), threading.Event()
    calls = 0
    lock = threading.Lock()
    def respond(request):
        nonlocal calls
        with lock:
            calls += 1
            if calls == 2: started.set()
        assert release.wait(5)
        return different(request)
    first = FakeModelClient(responder=respond)
    with ThreadPoolExecutor(max_workers=1) as driver:
        pending = driver.submit(run, url, lease, first)
        try:
            assert started.wait(5)
            cancel_task(url, 'task', course_id='course')
        finally:
            release.set()
        with pytest.raises(FusionCancelled): pending.result(5)
    assert len(first.calls) == 2
    assert progress(url)['completed'] == 2 and progress(url)['inflight'] == 0
    assert progress(url)['pending'] == 4
    assert run_merge_stage(url, lease).stage == 'cancelled'
    assert resume_task(Settings(SQLITE_URL=url), 'task', course_id='course', user_id='teacher').stage == 'merging'
    next_lease = task_leases.claim_next(url, owner='resumed', lease_seconds=600, max_attempts=3)
    assert progress(url) is None  # no stale attempt shown while the new plan is being prepared
    second = FakeModelClient(responder=different)
    result = run(url, next_lease, second)
    assert len(second.calls) == 4 and all(d.status == 'complete' for d in result)
    assert progress(url)['reused'] == 2


def test_failed_and_deferred_are_visible_but_are_not_complete_cache_hits(state):
    from app.workers.fusion_decisions import DecisionWork
    url, lease = state
    items = work(2)
    broken = FakeModelClient(responder=lambda _: 'invalid json')
    run(url, lease, broken, items=[items[0], DecisionWork('a','b1',None,None,'ambiguous_evidence')])
    report = progress(url)
    assert (report['completed'], report['failed'], report['deferred'], report['pending']) == (0,1,1,0)
    assert report['phase'] == 'complete'
    good = FakeModelClient(responder=different)
    run(url, lease, good, items=[items[0], DecisionWork('a','b1',None,None,'ambiguous_evidence')])
    assert len(good.calls) == 1 and progress(url)['completed'] == 1


@pytest.mark.parametrize('condition', ['token','expired','terminal','credential'])
def test_late_results_cannot_bypass_original_lease_scope_or_credentials(state, condition):
    from app.workers.fusion_decisions import FusionDecisionCache
    url, lease = state
    revoked = False
    def credential():
        if revoked: raise CredentialUnavailable('credential_revoked')
    def respond(request):
        nonlocal revoked
        if condition == 'credential': revoked = True
        else:
            with connect(url) as db:
                if condition == 'token': db.execute("UPDATE processing_tasks SET lease_token=? WHERE id='task'", ('x'*32,))
                elif condition == 'expired': db.execute("UPDATE processing_tasks SET lease_expires_at=0 WHERE id='task'")
                else: db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1 WHERE id='task'")
        return different(request)
    with pytest.raises((task_leases.LeaseLost, CredentialUnavailable)):
        run(url, lease, FakeModelClient(responder=respond), items=work(1), concurrency=1, guard=credential)
    with connect(url) as db:
        assert db.execute("SELECT count(*) FROM task_fusion_decisions WHERE status='complete'").fetchone()[0] == 0


def test_changed_digest_never_reuses_other_plan_and_current_pointer_can_return_to_old_digest(state):
    url, lease = state
    first = FakeModelClient(responder=different)
    run(url, lease, first, digest='a', items=work(1))
    second = FakeModelClient(responder=different)
    run(url, lease, second, digest='b', items=work(2))
    assert len(second.calls) == 2 and progress(url)['input_digest'] == 'b'
    last = FakeModelClient(responder=different)
    run(url, lease, last, digest='a', items=work(1))
    assert not last.calls and progress(url)['input_digest'] == 'a' and progress(url)['total'] == 1


def test_complete_decisions_and_plan_scope_are_immutable_in_sqlite(state):
    url, lease = state
    run(url, lease, FakeModelClient(responder=different), items=work(1))
    with connect(url) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE task_fusion_decisions SET status='failed' WHERE task_id='task'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE task_fusion_analysis SET course_id='other' WHERE task_id='task'")


@pytest.fixture
def preparation(db_url, tmp_path, monkeypatch):
    """Real parser/extractor/SQLite; only the empty external graph is replaced."""
    from app.services.file_storage import FileStorage
    from app.workers import fusion_task
    from app.workers.extraction.types import ExtractLimits
    from tests.backend.helpers.accounts import make_account
    from tests.integration import test_f13 as pipeline
    user = make_account(db_url, 'teacher', 'teacher')
    course = 'c'*32
    with connect(db_url) as db:
        db.execute("INSERT INTO courses(id,name,teacher_id) VALUES(?,'test',?)", (course,user.id))
    toolkit = replace(pipeline._toolkit(db_url), preserve_mentions=True)
    monkeypatch.setattr(pipeline, '_toolkit', lambda _: toolkit)
    lease = pipeline._to_merging(db_url, FileStorage(tmp_path/'files', 1024*1024),
        pipeline._material([], ['概念11','概念12','概念13']), course)
    monkeypatch.setattr(fusion_task, 'read_snapshot', lambda *_: dict(course_id=course,nodes=[],edges=[],evidence=[]))
    def prepare(client, *, context=None, current_lease=lease, embedding=None):
        kit = replace(toolkit, policy=_policy(db_url,client),
            resolver=lambda c: SemanticResolver(c,model='m'), analysis_context=context)
        return fusion_task.prepare_fusion(db_url,current_lease,repo=None,toolkit=kit,
            max_pairs=16,top_k=8,lock_seconds=60,lock_wait_seconds=0,embedding=embedding,
            extract_limits=ExtractLimits(max_attempts=3,max_concurrency=1))
    prepare.toolkit = toolkit
    return db_url,lease,prepare


def test_full_preparation_retries_failed_pairs_instead_of_reusing_partial_plan(preparation):
    url,lease,prepare = preparation
    first = prepare(FakeModelClient(responder=lambda _: 'invalid json'))
    assert first.payload['decisions'] and all(d['status']=='failed' for d in first.payload['decisions'])
    good = FakeModelClient(responder=different)
    second = prepare(good)
    assert len(good.calls) == len(first.payload['decisions'])
    assert second.plan_id != first.plan_id
    assert all(d['status']=='complete' for d in second.payload['decisions'])


def test_provider_thinking_context_invalidates_complete_global_plan(preparation):
    url,lease,prepare = preparation
    first = prepare(FakeModelClient(responder=different),context={'provider':'first','thinking':True})
    next_client = FakeModelClient(responder=different)
    second = prepare(next_client,context={'provider':'second','thinking':False})
    assert next_client.calls and first.plan_id != second.plan_id
    assert first.payload['analysis_input_digest'] != second.payload['analysis_input_digest']


def test_reactivating_old_input_selects_its_exact_output_plan_for_persistence(preparation):
    from app.repositories import fusion
    url,lease,prepare = preparation
    first = prepare(FakeModelClient(responder=different),context={'provider':'first'})
    other = prepare(FakeModelClient(responder=different),context={'provider':'other'})
    assert first.plan_id != other.plan_id
    client = FakeModelClient(responder=different)
    again = prepare(client,context={'provider':'first'})
    assert again.plan_id == first.plan_id and not client.calls
    with connect(url) as db:
        assert fusion.task_plan(db,lease.course_id,lease.task_id).plan_id == first.plan_id
    from app.workers.persist_graph import run_merge_stage
    assert run_merge_stage(url,lease).stage == 'persisting'
    with connect(url) as db:
        db.execute('UPDATE processing_tasks SET lease_expires_at=0 WHERE id=?',(lease.task_id,))
    claimed = task_leases.claim_next(url,owner='persist-retry',lease_seconds=60,max_attempts=3)
    assert claimed.stage == 'persisting' and claimed.attempt == lease.attempt+1
    with connect(url) as db:
        assert fusion.task_plan(db,lease.course_id,lease.task_id).plan_id == first.plan_id


def test_unfinished_current_analysis_never_falls_back_to_older_selected_output(preparation):
    from app.repositories import fusion,fusion_decisions
    from app.workers.fusion_decisions import FusionDecisionCache
    url,lease,prepare = preparation
    saved = prepare(FakeModelClient(responder=different))
    cache = FusionDecisionCache(url,lease)
    with cache.transaction() as db:
        fusion_decisions.initialize_plan(db,**cache.scope('unfinished'),pairs=[],
            total_possible=3,attempt=lease.attempt)
        assert fusion.task_plan(db,lease.course_id,lease.task_id) is None
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE task_fusion_analysis SET selected_plan_id=? WHERE input_digest='unfinished'",(saved.plan_id,))
        assert fusion.task_plan(db,lease.course_id,lease.task_id) is None


def test_cancelled_material_deletion_cascades_selected_analysis_and_prepared_plan(preparation):
    from app.repositories.materials import MaterialDeleted,delete_material
    from app.workers.persist_graph import run_merge_stage
    url,lease,prepare = preparation
    prepare(FakeModelClient(responder=different))
    cancel_task(url,lease.task_id,course_id=lease.course_id)
    assert run_merge_stage(url,lease).stage == 'cancelled'
    with connect(url) as db:
        document_id = db.execute('SELECT document_id FROM processing_tasks WHERE id=?',(lease.task_id,)).fetchone()[0]
    assert isinstance(delete_material(url,document_id,course_id=lease.course_id),MaterialDeleted)
    with connect(url) as db:
        for table in ('fusion_plans','task_fusion_analysis','task_fusion_decisions','processing_tasks'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_auto_merge_disabled_after_resume_replaces_old_same_plan_before_persistence(preparation,tmp_path,monkeypatch):
    from app.repositories import fusion
    from app.workers import persist_graph
    url,lease,prepare = preparation
    def same(request):
        value = json.loads(different(request))
        value.update(verdict='SAME',differences=[])
        return json.dumps(value)
    first = prepare(FakeModelClient(responder=same))
    assert first.payload['groups']
    cancel_task(url,lease.task_id,course_id=lease.course_id)
    assert persist_graph.run_merge_stage(url,lease).stage == 'cancelled'
    resume_task(Settings(SQLITE_URL=url),lease.task_id,course_id=lease.course_id,user_id='teacher')
    selected = []
    def persist(sqlite_url,claimed,**_):
        with connect(sqlite_url) as db:
            selected.append(fusion.task_plan(db,claimed.course_id,claimed.task_id))
        return persist_graph.PersistOutcome(persist_graph.PersistStatus.ADVANCED,claimed.task_id,'awaiting_review')
    monkeypatch.setattr(persist_graph,'run_persist_stage',persist)
    settings = Settings(SQLITE_URL=url,STORAGE_DIR=str(tmp_path/'files'),DISAMBIGUATION_AUTO_MERGE_ENABLED=False)
    result = persist_graph.run_pipeline_once(settings,toolkit=prepare.toolkit,repo=None)
    assert result.stages == (('merging','advanced'),('persisting','advanced'))
    assert selected[0].plan_id != first.plan_id and not selected[0].payload['groups']
    assert selected[0].payload['reason'] == 'auto_merge_disabled'


def test_full_preparation_real_resume_reuses_completed_global_pairs(preparation):
    from app.workers.fusion_task import FusionCancelled
    from app.workers.persist_graph import run_merge_stage
    from app.repositories.fusion_decisions import read_progress
    url,lease,prepare = preparation
    calls = 0
    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            cancel_task(url,lease.task_id,course_id=lease.course_id)
        return different(request)
    with pytest.raises(FusionCancelled):
        prepare(FakeModelClient(responder=respond))
    with connect(url) as db:
        assert read_progress(db,course_id=lease.course_id,task_id=lease.task_id)['completed'] == 2
    assert run_merge_stage(url,lease).stage == 'cancelled'
    resume_task(Settings(SQLITE_URL=url),lease.task_id,course_id=lease.course_id,user_id='teacher')
    next_lease = task_leases.claim_next(url,owner='resume',lease_seconds=600,max_attempts=3)
    client = FakeModelClient(responder=different)
    plan = prepare(client,current_lease=next_lease)
    assert len(client.calls) == 1 and len(plan.payload['decisions']) == 3
    with connect(url) as db:
        report = read_progress(db,course_id=lease.course_id,task_id=lease.task_id)
    assert report['completed'] == 3 and report['reused'] == 2


class CountingEmbedding:
    space = 'real/test/3'

    def __init__(self):
        self.calls = 0

    def embed(self, texts, *, before_attempt):
        from app.services.ai.embeddings import EmbeddedVector
        before_attempt()
        self.calls += 1
        return [EmbeddedVector((1.,1.,1.),'test',3,self.space,str(i)) for i,_ in enumerate(texts)]


def test_complete_fusion_plan_fast_path_does_not_repeat_embedding(preparation):
    _,_,prepare = preparation
    embedding = CountingEmbedding()
    first = prepare(FakeModelClient(responder=different),embedding=embedding)
    client = FakeModelClient(responder=different)
    again = prepare(client,embedding=embedding)
    assert again.plan_id == first.plan_id and not client.calls
    assert embedding.calls == 1


def test_partial_global_plan_reuses_persisted_recall_without_repeating_embedding(preparation):
    from app.services.ai.client import ModelAuthError
    url,lease,prepare = preparation
    embedding = CountingEmbedding()
    calls = 0
    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ModelAuthError('m')
        return different(request)
    with pytest.raises(ModelAuthError):
        prepare(FakeModelClient(responder=respond),embedding=embedding)
    client = FakeModelClient(responder=different)
    result = prepare(client,embedding=embedding)
    assert len(client.calls) == 2 and result.payload['completed_pairs'] == 3
    assert embedding.calls == 1


def test_complete_write_rechecks_credentials_after_acquiring_transaction(state, monkeypatch):
    """Revocation commits after the first credential read, before the writer lock."""
    from contextlib import contextmanager
    from app.workers import fusion_decisions as worker
    url,lease = state
    with connect(url) as db:
        db.execute('CREATE TABLE fixture_credentials(active INTEGER NOT NULL)')
        db.execute('INSERT INTO fixture_credentials VALUES(1)')
    returned = False
    def credential():
        with connect(url) as db:
            if not db.execute('SELECT active FROM fixture_credentials').fetchone()[0]:
                raise CredentialUnavailable('credential_revoked')
    original = worker.leased_transaction
    @contextmanager
    def revoke_then_lock(*args):
        if returned:
            with connect(url) as db:
                db.execute('UPDATE fixture_credentials SET active=0')
        with original(*args) as db:
            yield db
    monkeypatch.setattr(worker, 'leased_transaction', revoke_then_lock)
    def respond(request):
        nonlocal returned
        returned = True
        return different(request)
    with pytest.raises(CredentialUnavailable):
        run(url,lease,FakeModelClient(responder=respond),guard=credential,items=work(1),concurrency=1)
    assert progress(url)['completed'] == 0


def test_request_guard_observes_revocation_committed_before_its_writer_lock(state,monkeypatch):
    from contextlib import contextmanager
    from app.workers import fusion_decisions as worker
    url,lease = state
    revoked = False
    def credential():
        if revoked:
            raise CredentialUnavailable('credential_revoked')
    original = worker.leased_transaction
    @contextmanager
    def revoke_then_lock(*args):
        nonlocal revoked
        revoked = True
        with original(*args) as db:
            yield db
    monkeypatch.setattr(worker,'leased_transaction',revoke_then_lock)
    with pytest.raises(CredentialUnavailable):
        worker.FusionDecisionCache(url,lease,credential_guard=credential).request_guard()


def test_request_guard_rechecks_stop_after_waiting_for_database_writer(state,monkeypatch):
    from contextlib import contextmanager
    from app.workers import fusion_decisions as worker
    url,lease = state
    cache = worker.FusionDecisionCache(url,lease)
    original = worker.leased_transaction
    @contextmanager
    def stop_while_locked(*args):
        with original(*args) as db:
            cache.abort(RuntimeError('other pair stopped'))
            yield db
    monkeypatch.setattr(worker,'leased_transaction',stop_while_locked)
    with pytest.raises(worker.FusionInterrupted):
        cache.request_guard()


@pytest.mark.parametrize('cancel_on_call,completed', [(1,0),(2,1)])
def test_same_requires_both_judgments_but_keeps_complete_late_second_response(state,cancel_on_call,completed):
    from app.workers.fusion_decisions import FusionCancelled
    url,lease = state
    calls = 0
    def respond(request):
        nonlocal calls
        calls += 1
        if calls == cancel_on_call:
            cancel_task(url,'task',course_id='course')
        value = json.loads(different(request))
        value.update(verdict='SAME',differences=[])
        return json.dumps(value)
    with pytest.raises(FusionCancelled):
        run(url,lease,FakeModelClient(responder=respond),items=work(1),concurrency=1)
    assert calls == cancel_on_call and progress(url)['completed'] == completed
    with connect(url) as db:
        assert db.execute("SELECT progress FROM processing_tasks WHERE id='task'").fetchone()[0] == .65


def test_wrong_course_cache_lease_is_rejected_before_reuse_or_model_call(state):
    from app.workers.fusion_decisions import FusionDecisionCache
    url,lease = state
    run(url,lease,FakeModelClient(responder=different),items=work(1))
    client = FakeModelClient(responder=different)
    with pytest.raises(task_leases.LeaseLost):
        run(url,replace(lease,course_id='other'),client,items=work(1))
    assert not client.calls


def test_026_rollback_refuses_unleased_active_task_and_preserves_business_data(state):
    from app.repositories.sqlite import MIGRATIONS_DIR,migrate
    url,lease = state
    run(url,lease,FakeModelClient(responder=different),items=work(1))
    commands = [line.removeprefix('-- ROLLBACK: ') for line in
        (MIGRATIONS_DIR/'026_fusion_decisions.sql').read_text().splitlines()
        if line.startswith('-- ROLLBACK: ')]
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL WHERE id='task'")
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.IntegrityError):
            for statement in commands: db.execute(statement)
        db.execute('ROLLBACK')
        assert db.execute('SELECT count(*) FROM task_fusion_decisions').fetchone()[0] == 1
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1 WHERE id='task'")
        db.execute('BEGIN IMMEDIATE')
        for statement in commands: db.execute(statement)
        db.execute('COMMIT')
        assert db.execute('SELECT count(*) FROM materials').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM task_revisions').fetchone()[0] == 1
    assert migrate(url) == ['026']
    assert progress(url) is None


def test_embedding_endpoint_change_invalidates_global_plan_with_same_vector_space(preparation):
    from app.services.ai.embeddings import EmbeddingAdapter
    from app.services.ai.fake import FakeEmbeddingClient
    _,_,prepare = preparation
    def adapter(host):
        settings = Settings(EMBEDDING_MODE='online', EMBEDDING_MODEL='embed-test',
            EMBEDDING_DIMENSIONS=3, EMBEDDING_BASE_URL=host)
        return EmbeddingAdapter(settings,FakeEmbeddingClient())
    first_embedding, second_embedding = adapter('https://one.invalid/v1'),adapter('https://two.invalid/v1')
    assert first_embedding.space == second_embedding.space
    first = prepare(FakeModelClient(responder=different),embedding=first_embedding)
    client = FakeModelClient(responder=different)
    second = prepare(client,embedding=second_embedding)
    assert len(client.calls) == 3 and first.plan_id != second.plan_id
    assert first.payload['analysis_input_digest'] != second.payload['analysis_input_digest']


def test_failed_embedding_recall_is_retried_instead_of_becoming_a_permanent_fallback(preparation):
    from app.services.ai.embeddings import EmbeddingBatchError
    _,_,prepare = preparation
    class TemporarilyBrokenEmbedding(CountingEmbedding):
        def embed(self,texts,*,before_attempt):
            if self.calls == 0:
                before_attempt()
                self.calls += 1
                raise EmbeddingBatchError('temporary',0,0)
            return super().embed(texts,before_attempt=before_attempt)
    embedding = TemporarilyBrokenEmbedding()
    first = prepare(FakeModelClient(responder=different),embedding=embedding)
    assert first.payload['vector_error'] == 'embedding_failed'
    second = prepare(FakeModelClient(responder=different),embedding=embedding)
    assert embedding.calls == 2 and second.payload['vector_error'] is None
    assert first.plan_id != second.plan_id


def test_recovered_embedding_only_calls_new_pairs_and_inherits_exact_input_completions(preparation,monkeypatch):
    from app.services.ai.embeddings import EmbeddingBatchError
    from app.workers import fusion_task
    from app.repositories.fusion_decisions import read_progress
    url,lease,prepare = preparation
    real_recall = fusion_task.recall_candidates
    def sparse_without_vectors(*args,**kwargs):
        found = real_recall(*args,**kwargs)
        return replace(found,pairs=found.pairs[:1]) if kwargs['vectors'] is None else found
    monkeypatch.setattr(fusion_task,'recall_candidates',sparse_without_vectors)
    class TemporarilyBrokenEmbedding(CountingEmbedding):
        def embed(self,texts,*,before_attempt):
            if self.calls == 0:
                self.calls += 1
                raise EmbeddingBatchError('temporary',0,0)
            return super().embed(texts,before_attempt=before_attempt)
    embedding = TemporarilyBrokenEmbedding()
    first = prepare(FakeModelClient(responder=different),embedding=embedding)
    assert first.payload['completed_pairs'] == 1
    task_leases.release_after_transient_failure(url,lease.task_id,lease.token,code='STORAGE_UNAVAILABLE',max_attempts=3)
    with connect(url) as db:
        original = db.execute("SELECT left_id,right_id,attempt,updated_at FROM task_fusion_decisions WHERE status='complete'").fetchone()
        db.execute('UPDATE processing_tasks SET not_before=0 WHERE id=?',(lease.task_id,))
    claimed = task_leases.claim_next(url,owner='retry',lease_seconds=60,max_attempts=3)
    client = FakeModelClient(responder=different)
    second = prepare(client,embedding=embedding,current_lease=claimed)
    assert len(client.calls) == 2 and second.payload['completed_pairs'] == 3
    with connect(url) as db:
        report = read_progress(db,course_id=lease.course_id,task_id=lease.task_id)
        inherited = db.execute('SELECT attempt,updated_at FROM task_fusion_decisions WHERE input_digest=? AND left_id=? AND right_id=?',
            (second.payload['analysis_input_digest'],*original[:2])).fetchone()
    assert inherited == original[2:] and report['reused'] == 1


def test_fatal_pair_stops_sibling_verification_without_hiding_original_error(state):
    from app.services.ai.client import ModelAuthError
    from app.workers.fusion_decisions import FusionDecisionCache,run_decisions
    from tests.waiting import wait_until
    url,lease = state
    cache = FusionDecisionCache(url,lease)
    both_started = threading.Barrier(2,timeout=5)
    def respond(request):
        payload = json.loads(request.messages[0].content.splitlines()[-1])
        both_started.wait()
        if payload['right']['id'] == 'b0':
            raise ModelAuthError('m')
        wait_until(cache.stop.is_set,timeout=5)
        value = json.loads(different(request))
        value.update(verdict='SAME',differences=[])
        return json.dumps(value)
    client = FakeModelClient(responder=respond)
    bound = _AttemptClient(_policy(url,client),CallAttribution(course_id='course',task_id='task',task_attempt=lease.attempt),guard=cache.request_guard)
    with pytest.raises(ModelAuthError):
        run_decisions(cache,'fatal',work(4),resolver=SemanticResolver(bound,model='m'),
            total_possible=15,max_concurrency=2)
    assert len(client.calls) == 2 and progress(url)['completed'] == 0
    assert progress(url)['pending'] + progress(url)['inflight'] == 4
