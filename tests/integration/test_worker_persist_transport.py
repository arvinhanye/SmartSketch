"""Real Bolt faults; no commit replacements, and a fixture-owned database only."""
from dataclasses import replace
from contextlib import contextmanager
import sqlite3
import threading
import time
import uuid
import json
import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from neo4j import AsyncGraphDatabase, GraphDatabase
from app.repositories import course_locks, task_leases
from app.repositories.lease_guard import LeaseGuard
from app.repositories.neo4j import Neo4jRepository, GraphScope, RepositoryTransportTimeout
from app.repositories.graph_relations import lock_draft, revoke_task
from app.repositories.sqlite import connect, migrate
from app.workers import persist_graph
from bolt_fault_proxy import BoltFaultProxy, owned_neo4j

@pytest.fixture
def task(tmp_path):
    url = f"sqlite:///{tmp_path / 'state.sqlite3'}"
    migrate(url)
    cid, tid, uid = [uuid.uuid4().hex for _ in range(3)]
    with connect(url) as db:
        db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, '$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA', 'teacher')",
                   (uid, uid))
        db.execute("INSERT INTO courses (id, name, teacher_id) VALUES (?, 'test', ?)", (cid, uid))
        db.execute("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
                   "VALUES ('doc', ?, 'a.txt', 'txt', 1, ?, 'stored')", (cid, 'sha256:' + '0' * 64))
        db.execute("INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key, stage, progress) "
                   "VALUES (?, ?, 'doc', ?, 'queued', 0)", (tid, cid, tid))
    lease = task_leases.claim_next(url, owner='worker', lease_seconds=60, max_attempts=3)
    assert lease is not None
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage='persisting', progress=0.8 WHERE id=?", (tid,))
    return url, replace(lease, stage='persisting', progress=0.8)


EVIDENCE = Path('/private/tmp/smartsketch-r1-network-evidence.jsonl')
QUERY = 'MERGE (n:KnowledgePoint {course_id:$course_id, version_id:$version_id, kp_id:$id}) SET n.contrib_tasks=[$task], n.fixture=true RETURN $effective_task_ids'


def record_evidence(fixture, **record):
    root = Path(__file__).resolve().parents[2]
    files = ['src/backend/app/config.py', 'src/backend/app/repositories/persist_transport.py',
             'src/backend/app/repositories/neo4j.py', 'src/backend/app/repositories/sqlite.py',
             'src/backend/app/repositories/task_leases.py', 'src/backend/app/workers/persist_graph.py']
    record.update(run_id=fixture['id'],
                  product_sha256=hashlib.sha256(b''.join((root / p).read_bytes() for p in files)).hexdigest(),
                  test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with EVIDENCE.open('a') as stream:
        stream.write(json.dumps(record) + '\n')


@pytest.mark.parametrize('repeat', range(5))
@pytest.mark.parametrize('mode', ['healthy', 'commit_blackhole', 'commit_noop', 'commit_fragment',
                                  'disconnect_before', 'disconnect_after', 'begin_blackhole', 'pull_blackhole'])
def test_worker_fault_fence_and_physical_connection_exit(task, owned_neo4j, monkeypatch, mode, repeat, cap=2.0):
    fixture = owned_neo4j
    url, lease = task
    sqlite_events = []
    main_thread = threading.get_ident()
    original_connect = sqlite3.connect
    class Recording(sqlite3.Connection):
        def execute(self, query, *args):
            result = super().execute(query, *args)
            if threading.get_ident() == main_thread and query in ('BEGIN IMMEDIATE', 'COMMIT', 'ROLLBACK'):
                sqlite_events.append((query, time.monotonic()))
            return result
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: original_connect(*a, **kw, factory=Recording))
    def write(tx, *args):
        lock_draft(tx)
        revoke_task(tx, lease.task_id)
        tx.run(QUERY, {'id': lease.task_id, 'task': lease.task_id})
        return SimpleNamespace(nodes=(), relations=(), downgraded=())
    monkeypatch.setattr(persist_graph, '_write_draft', write)
    guard = None if mode not in ('begin_blackhole', 'pull_blackhole') else LeaseGuard(1, last_success=time.monotonic())
    writer_wait = []
    writer_errors = []
    stop = threading.Event()
    with GraphDatabase.driver(fixture['uri'], auth=fixture['auth']) as direct:
        with BoltFaultProxy(fixture['host'], fixture['port'], mode=mode) as proxy:
            repo = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(proxy.uri, auth=fixture['auth']), persist_commit_timeout=cap)
            def writer():
                while not proxy.commit_seen.wait(.05):
                    if stop.is_set():
                        return
                started = time.monotonic()
                try:
                    with connect(url) as db:
                        db.execute('PRAGMA busy_timeout=5000' if repeat % 2 else 'PRAGMA busy_timeout=0')
                        while not stop.is_set():
                            try:
                                db.execute('BEGIN IMMEDIATE')
                                db.execute('UPDATE courses SET name=name WHERE id=?', (lease.course_id,))
                                db.execute('COMMIT')
                                writer_wait.append(time.monotonic() - started)
                                return
                            except sqlite3.OperationalError:
                                time.sleep(.005)
                except BaseException as exc:
                    writer_errors.append(type(exc).__name__)
            thread = threading.Thread(target=writer)
            thread.start()
            started = time.monotonic()
            try:
                outcome = persist_graph.run_persist_stage(url, lease, repo=repo, max_attempts=3,
                    lock_seconds=60, lock_wait_seconds=0, task_guard=guard)
                returned = time.monotonic()
                if mode not in ('healthy', 'disconnect_before', 'disconnect_after'):
                    assert proxy.client_disconnected.wait(2), 'cancelled connection did not reach physical FIN/reset'
            finally:
                if not proxy.commit_seen.is_set():
                    stop.set()
                thread.join(timeout=6)
                stop.set()
            assert not thread.is_alive() and not writer_errors
            if mode.startswith('commit_'):
                assert outcome.status is persist_graph.PersistStatus.LOST
                assert proxy.forwarded_commits == 1
                assert writer_wait and max(writer_wait) <= cap + 1
            if mode == 'healthy':
                assert outcome.status is persist_graph.PersistStatus.ADVANCED
            if mode == 'disconnect_before':
                assert proxy.forwarded_commits == 0
            if proxy.timestamps['commit_seen']:
                seen = proxy.timestamps['commit_seen'][0]
                acquired = max(t for event, t in sqlite_events if event == 'BEGIN IMMEDIATE' and t < seen)
                released = min(t for event, t in sqlite_events if event in ('ROLLBACK', 'COMMIT') and t >= seen)
                assert released - acquired <= cap + 1
                assert returned - released <= 2
            else:
                acquired = released = None
                assert returned - started <= 2
            with connect(url) as db:
                stage, seq = db.execute('SELECT stage,t6_seq FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone()
            rows = direct.execute_query('MATCH (n {course_id:$course,fixture:true}) RETURN count(n) AS n',
                                        course=lease.course_id).records
            actual_graph_count = rows[0]['n']
            if mode == 'healthy':
                assert stage == 'awaiting_review' and seq == 1 and actual_graph_count == 1
            else:
                assert seq is None
            record_evidence(fixture, **{'mode':mode,'repeat':repeat,'commit_timeout':cap,'fence_acquired':acquired,
                    'fence_released':released,'returned':returned,'writer_wait':writer_wait,
                    'forwarded_commits':proxy.forwarded_commits,'timestamps':dict(proxy.timestamps),
                    'graph_count':actual_graph_count,'stage':stage,'seq':seq})
        assert proxy.closed
        if mode != 'healthy':
            with connect(url) as db:
                db.execute('UPDATE processing_tasks SET lease_expires_at=CASE WHEN lease_token IS NULL THEN NULL ELSE unixepoch()-1 END, not_before=0 WHERE id=? AND (lease_token=? OR lease_token IS NULL)',
                           (lease.task_id, lease.token))
            next_lease = task_leases.claim_next(url, owner='next-worker', lease_seconds=60, max_attempts=3)
            assert next_lease and next_lease.token != lease.token
            recovery = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(fixture['uri'], auth=fixture['auth']))
            assert persist_graph.run_persist_stage(url, next_lease, repo=recovery, max_attempts=3,
                lock_seconds=60, lock_wait_seconds=0).status is persist_graph.PersistStatus.ADVANCED
            with connect(url) as db:
                assert db.execute('SELECT t6_seq FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone() == (1,)
                assert db.execute('SELECT draft_revision FROM courses WHERE id=?', (lease.course_id,)).fetchone() == (1,)
            assert direct.execute_query('MATCH (n {course_id:$course,fixture:true}) RETURN count(n) AS n',
                                        course=lease.course_id).records[0]['n'] == 1


@pytest.mark.parametrize('repeat', range(5))
def test_real_rollback_blackhole_uses_shared_exit_budget(owned_neo4j, repeat, cleanup_timeout=.1):
    f = owned_neo4j
    with GraphDatabase.driver(f['uri'], auth=f['auth']) as direct:
        with BoltFaultProxy(f['host'], f['port'], mode='rollback_blackhole') as proxy:
            repo = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(proxy.uri, auth=f['auth']),
                                   persist_cleanup_timeout=cleanup_timeout)
            started = time.monotonic()
            with pytest.raises(RepositoryTransportTimeout) as caught:
                with repo.persist_write_transaction(GraphScope(uuid.uuid4().hex, 'draft', ()),
                        check=lambda: None, remaining=lambda: 2) as tx:
                    tx.run('RETURN $course_id, $version_id, $effective_task_ids')
            assert caught.value.phase == 'exit'
            elapsed = time.monotonic() - started
            assert elapsed <= cleanup_timeout + 1
            assert proxy.client_disconnected.wait(1)
            record_evidence(f, mode='rollback_blackhole', repeat=repeat, cleanup_timeout=cleanup_timeout,
                            elapsed=elapsed, timestamps=dict(proxy.timestamps))
        assert proxy.closed


@pytest.mark.parametrize('repeat', range(5))
def test_cap_configuration_bounds_fence(task, owned_neo4j, monkeypatch, repeat):
    test_worker_fault_fence_and_physical_connection_exit(task, owned_neo4j, monkeypatch,
        'commit_blackhole', repeat, cap=3.0)


@pytest.mark.parametrize('recovery_mode', ['takeover', 'failed_cleanup'])
def test_actual_server_commit_after_client_cancellation(task, owned_neo4j, monkeypatch, recovery_mode):
    """Pause only our owned server, forward before cancellation, then inspect."""
    f = owned_neo4j
    url, lease = task
    lock = course_locks.try_acquire(url, lease.course_id, holder='late-test', lease_seconds=60)
    observed = 0
    with GraphDatabase.driver(f['uri'], auth=f['auth']) as direct:
        for attempt in range(5):
            key = uuid.uuid4().hex
            with BoltFaultProxy(f['host'], f['port'], mode='commit_blackhole') as proxy:
                paused = threading.Event()
                def pause():
                    subprocess.run([f['docker'], 'pause', f['id']], check=True,
                                   capture_output=True, timeout=10)
                    paused.set()
                proxy.before_forward_commit = pause
                repo = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(proxy.uri, auth=f['auth']),
                                       persist_commit_timeout=2)
                try:
                    with pytest.raises(RepositoryTransportTimeout) as caught:
                        with repo.persist_write_transaction(GraphScope(lease.course_id, 'draft', ()),
                                check=lambda: None, remaining=lambda: 40) as tx:
                            lock_draft(tx)
                            tx.run(QUERY, {'id': key, 'task': lease.task_id})
                            acquired = []
                            with task_leases.persist_transaction(url, lease, lock.token,
                                    deadline=tx.deadline, on_acquired=acquired.append):
                                tx.commit(started_at=acquired[0])
                    assert caught.value.phase == 'commit', 'late experiment did not reach COMMIT'
                    assert proxy.client_disconnected.wait(2)
                    assert proxy.timestamps['commit_forwarded'], 'request not forwarded before client cancellation'
                    assert proxy.timestamps['commit_forwarded'][0] < proxy.timestamps['client_disconnected'][0]
                finally:
                    if paused.is_set():
                        subprocess.run([f['docker'], 'unpause', f['id']], check=True,
                                       capture_output=True, timeout=10)
            # This independent query, not proxy byte counters, proves the server outcome.
            count = direct.execute_query('MATCH (n {course_id:$course,kp_id:$key}) RETURN count(n) AS n',
                                         course=lease.course_id, key=key).records[0]['n']
            observed += count
            record_evidence(f, mode='late_server_outcome', recovery_mode=recovery_mode, repeat=attempt,
                            actual_commit_after_cancel=bool(count), timestamps=dict(proxy.timestamps))
    course_locks.release(url, lock)
    assert observed >= 1, 'OPEN: no actual late server commit observed; coverage incomplete'
    if recovery_mode == 'takeover':
        with connect(url) as db:
            db.execute('UPDATE processing_tasks SET lease_expires_at=unixepoch()-1 WHERE id=? AND lease_token=?',
                       (lease.task_id, lease.token))
        successor = task_leases.claim_next(url, owner='late-successor', lease_seconds=60, max_attempts=3)
        assert successor is not None and successor.attempt == lease.attempt + 1
        def rebuild(tx, *args):
            lock_draft(tx)
            revoke_task(tx, lease.task_id)
            tx.run(QUERY, {'id': lease.task_id, 'task': lease.task_id})
            return SimpleNamespace(nodes=(), relations=(), downgraded=())
        monkeypatch.setattr(persist_graph, '_write_draft', rebuild)
        with GraphDatabase.driver(f['uri'], auth=f['auth']) as direct:
            good = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(f['uri'], auth=f['auth']))
            outcome = persist_graph.run_persist_stage(url, successor, repo=good, max_attempts=3,
                lock_seconds=60, lock_wait_seconds=0)
            assert outcome.status is persist_graph.PersistStatus.ADVANCED
            assert direct.execute_query('MATCH (n {course_id:$course,fixture:true}) RETURN collect(n.kp_id) AS ids',
                                        course=lease.course_id).records[0]['ids'] == [lease.task_id]
        with connect(url) as db:
            assert db.execute('SELECT stage,t6_seq,lease_token,attempt FROM processing_tasks WHERE id=?',
                              (lease.task_id,)).fetchone() == ('awaiting_review', 1, None, successor.attempt)
            assert db.execute('SELECT draft_revision FROM courses WHERE id=?', (lease.course_id,)).fetchone() == (1,)
        record_evidence(f, mode='late_recovery', recovery_mode=recovery_mode, status='advanced', t6_seq=1)
        return
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage='failed',error_code='INTERNAL_ERROR',error_message='fixture failure',cleanup_pending=1,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL WHERE id=?", (lease.task_id,))
    with GraphDatabase.driver(f['uri'], auth=f['auth']) as direct:
        good = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(f['uri'], auth=f['auth']))
        assert persist_graph.cleanup_failed_task(url, good, course_id=lease.course_id, task_id=lease.task_id,
            holder='late-cleanup', lock_seconds=60, lock_wait_seconds=0)
        assert direct.execute_query('MATCH (n {course_id:$course,fixture:true}) RETURN count(n) AS n',
                                    course=lease.course_id).records[0]['n'] == 0
    record_evidence(f, mode='late_recovery', recovery_mode=recovery_mode, status='cleaned', graph_count=0)


def test_real_empty_cleanup_waits_for_old_draft_guard(task, owned_neo4j, monkeypatch):
    from app.repositories.neo4j import ScopedTransaction
    f = owned_neo4j
    url, lease = task
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage='failed', error_code='INTERNAL_ERROR', error_message='fixture failure', cleanup_pending=1, lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL WHERE id=?", (lease.task_id,))
    with GraphDatabase.driver(f['uri'], auth=f['auth']) as direct:
        repo = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(f['uri'], auth=f['auth']))
        entered = threading.Event()
        results, errors = [], []
        real_lock = persist_graph.lock_draft
        def observed_lock(tx):
            entered.set()
            return real_lock(tx)
        with direct.session(database='neo4j') as session:
            old = session.begin_transaction(timeout=20)
            old_scoped = ScopedTransaction(old, GraphScope(lease.course_id, 'draft', ()))
            lock_draft(old_scoped)
            old_scoped.run(QUERY, {'id': lease.task_id, 'task': lease.task_id})
            monkeypatch.setattr(persist_graph, 'lock_draft', observed_lock)
            def cleanup():
                try:
                    results.append(persist_graph.cleanup_failed_task(url, repo, course_id=lease.course_id,
                        task_id=lease.task_id, holder='cleanup', lock_seconds=60, lock_wait_seconds=0))
                except BaseException as exc:
                    errors.append(type(exc).__name__)
            thread = threading.Thread(target=cleanup)
            thread.start()
            try:
                assert entered.wait(5)
                with connect(url) as db:
                    assert db.execute('SELECT cleanup_pending FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone() == (1,)
                assert direct.execute_query('MATCH (n {course_id:$course,fixture:true}) RETURN count(n) AS n',
                                            course=lease.course_id).records[0]['n'] == 0
                old.commit()
            finally:
                old.close()
                thread.join(timeout=10)
            assert not thread.is_alive() and not errors and results == [True]
        with connect(url) as db:
            assert db.execute('SELECT cleanup_pending FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone() == (0,)
        assert direct.execute_query('MATCH (n {course_id:$course,fixture:true}) RETURN count(n) AS n',
                                    course=lease.course_id).records[0]['n'] == 0


def test_real_cleanup_unknown_ack_preserves_other_and_manual(task, owned_neo4j):
    f = owned_neo4j
    url, lease = task
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET stage='failed',error_code='INTERNAL_ERROR',error_message='fixture failure',cleanup_pending=1,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL WHERE id=?", (lease.task_id,))
    with GraphDatabase.driver(f['uri'], auth=f['auth']) as direct:
        direct.execute_query("CREATE (n:KnowledgePoint {course_id:$course,version_id:'draft',kp_id:$id,contrib_tasks:[$task,'other-task'],contrib_manual:true})",
                             course=lease.course_id, id=lease.task_id, task=lease.task_id)
        with BoltFaultProxy(f['host'], f['port'], mode='commit_blackhole') as proxy:
            repo = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(proxy.uri, auth=f['auth']))
            assert not persist_graph.cleanup_failed_task(url, repo, course_id=lease.course_id,
                task_id=lease.task_id, holder='cleanup', lock_seconds=60, lock_wait_seconds=0)
            assert proxy.client_disconnected.wait(2)
        with connect(url) as db:
            assert db.execute('SELECT cleanup_pending FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone() == (1,)
        row = direct.execute_query('MATCH (n {course_id:$course,kp_id:$id}) RETURN n.contrib_tasks AS tasks,n.contrib_manual AS manual',
                                   course=lease.course_id, id=lease.task_id).records[0]
        assert row['tasks'] == ['other-task'] and row['manual'] is True
        good = Neo4jRepository(direct, persist_driver_factory=lambda: AsyncGraphDatabase.driver(f['uri'], auth=f['auth']))
        assert persist_graph.cleanup_failed_task(url, good, course_id=lease.course_id,
            task_id=lease.task_id, holder='cleanup', lock_seconds=60, lock_wait_seconds=0)
        with connect(url) as db:
            assert db.execute('SELECT cleanup_pending FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone() == (0,)


def test_original_worker_blackhole_requires_external_watchdog(task, owned_neo4j, tmp_path):
    """Run the unmodified core baseline in a child; kill only this test child."""
    import os
    import sys
    import tarfile
    import io
    f = owned_neo4j
    root = Path(__file__).resolve().parents[2]
    archive = subprocess.run(['git', 'archive', 'e111315', 'src/backend'], cwd=root,
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(tmp_path)
    script = '''import json,sys,sqlite3,time
from types import SimpleNamespace
from dataclasses import replace
from neo4j import GraphDatabase
from app.repositories.neo4j import Neo4jRepository
from app.repositories.task_leases import Lease
from app.repositories.graph_relations import lock_draft
from app.workers import persist_graph
p=json.loads(sys.stdin.readline())
l=Lease(**p['lease'])
d=GraphDatabase.driver(p['uri'],auth=tuple(p['auth']))
def write(tx,*args):
 lock_draft(tx)
 tx.run('MERGE (n:KnowledgePoint {course_id:$course_id,version_id:$version_id,kp_id:$id}) RETURN $effective_task_ids',{'id':l.task_id})
 return SimpleNamespace(nodes=(),relations=(),downgraded=())
persist_graph._write_draft=write
persist_graph.run_persist_stage(p['url'],l,repo=Neo4jRepository(d),max_attempts=3,lock_seconds=60,lock_wait_seconds=0)
print('BASELINE_RETURNED',flush=True)
'''
    url, lease = task
    from dataclasses import asdict
    with BoltFaultProxy(f['host'], f['port'], mode='commit_blackhole') as proxy:
        env = dict(os.environ, PYTHONPATH=str(tmp_path / 'src/backend'))
        process = subprocess.Popen([sys.executable, '-c', script], env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            process.stdin.write(json.dumps({'lease':asdict(lease),'url':url,'uri':proxy.uri,'auth':f['auth']})+'\n')
            process.stdin.flush()
            assert proxy.commit_seen.wait(20), 'baseline did not reach COMMIT'
            with connect(url) as db:
                db.execute('PRAGMA busy_timeout=0')
                with pytest.raises(sqlite3.OperationalError):
                    db.execute('BEGIN IMMEDIATE')
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=10)
            record_evidence(f, mode='baseline_RED', watchdog_seconds=10, fence_still_held=True,
                            forwarded_commits=proxy.forwarded_commits)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        with connect(url) as db:
            db.execute('PRAGMA busy_timeout=0')
            db.execute('BEGIN IMMEDIATE')
            db.execute('ROLLBACK')


@pytest.mark.parametrize('repeat', range(5))
@pytest.mark.parametrize('cleanup_timeout', [1.0, 5.0])
def test_default_and_upper_exit_budgets(owned_neo4j, repeat, cleanup_timeout):
    test_real_rollback_blackhole_uses_shared_exit_budget(owned_neo4j, repeat, cleanup_timeout)
