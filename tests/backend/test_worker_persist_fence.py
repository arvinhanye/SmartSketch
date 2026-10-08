"""R1: deterministic lease cutoff and cross-store commit fencing (ADR-091)."""

from dataclasses import replace
import sqlite3
from types import SimpleNamespace
import uuid
from contextlib import contextmanager

import pytest

from app.repositories import course_locks, task_leases
from app.repositories.sqlite import connect, migrate
from app.repositories.neo4j import Neo4jRepository
from app.workers import persist_graph


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


def test_guard_cutoff_is_terminal():
    from app.repositories.lease_guard import LeaseGuard
    now = [0.0]
    guard = LeaseGuard(60, last_success=0, clock=lambda: now[0])
    assert guard.remaining() == 40
    now[0] = 39.9
    guard.check()
    now[0] = 40
    with pytest.raises(task_leases.LeaseLost):
        guard.check()
    guard.renewed(40)
    assert guard.lost.is_set()
    with pytest.raises(task_leases.LeaseLost):
        guard.check()


def test_delayed_renewal_uses_start_time():
    from app.repositories.lease_guard import LeaseGuard
    now = [30.0]
    guard = LeaseGuard(60, last_success=0, clock=lambda: now[0])
    guard.renewed(20)
    assert guard.remaining() == 30
    now[0] = 60
    guard.renewed(55)  # Late reply must not revive the guard past its old cutoff.
    with pytest.raises(task_leases.LeaseLost):
        guard.check()


@pytest.mark.parametrize('fault', ['task', 'lock', 'task_expiry', 'lock_expiry', 'course', 'stage'])
def test_persist_fence_rejects_stale_task_or_course(task, fault):
    url, lease = task
    lock = course_locks.try_acquire(url, lease.course_id, holder='worker', lease_seconds=60)
    assert lock is not None
    with connect(url) as db:
        if fault == 'task':
            db.execute("UPDATE processing_tasks SET lease_token='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' WHERE id=?", (lease.task_id,))
        elif fault == 'lock':
            db.execute("UPDATE course_locks SET token='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' WHERE course_id=?", (lease.course_id,))
        elif fault == 'task_expiry':
            db.execute("UPDATE processing_tasks SET lease_expires_at=unixepoch() WHERE id=?", (lease.task_id,))
        elif fault == 'lock_expiry':
            db.execute("UPDATE course_locks SET expires_at=unixepoch() WHERE course_id=?", (lease.course_id,))
        elif fault == 'course':
            lease = replace(lease, course_id='wrong')
        else:
            db.execute("UPDATE processing_tasks SET stage='awaiting_review' WHERE id=?", (lease.task_id,))
    with pytest.raises(task_leases.LeaseLost):
        with task_leases.persist_transaction(url, lease, lock.token):
            pytest.fail('stale owner must not pass the fence')


def test_persist_fence_holds_writer_lock(task):
    url, lease = task
    lock = course_locks.try_acquire(url, lease.course_id, holder='worker', lease_seconds=60)
    with task_leases.persist_transaction(url, lease, lock.token) as db:
        assert db.in_transaction
        with connect(url) as other:
            other.execute('PRAGMA busy_timeout=0')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other.execute("UPDATE processing_tasks SET lease_token='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' WHERE id=?", (lease.task_id,))
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET lease_token='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' WHERE id=?", (lease.task_id,))


def test_strict_renewals_reject_expired_tokens(task):
    url, lease = task
    lock = course_locks.try_acquire(url, lease.course_id, holder='worker', lease_seconds=60)
    with connect(url) as db:
        db.execute("UPDATE processing_tasks SET lease_expires_at=unixepoch() WHERE id=?", (lease.task_id,))
        db.execute("UPDATE course_locks SET expires_at=unixepoch() WHERE course_id=?", (lease.course_id,))
    assert task_leases.renew_lease(url, lease.task_id, lease.token, lease_seconds=60, require_live=True) is None
    assert not course_locks.renew(url, lock, lease_seconds=60, require_live=True)


class GraphDriver:
    """Records transaction lifecycle; SQLite is real in every scheduling test."""
    def __init__(self):
        self.commits = self.rollbacks = self.runs = 0
        self.after_run = self.before_commit = self.after_commit = lambda: None
        self.committed = False
        self.closed = False

    @contextmanager
    def session(self, **kwargs):
        try:
            yield self
        finally:
            self.closed = True

    def begin_transaction(self, **kwargs):
        return self

    def execute_write(self, work):
        result = work(self)
        self.commit()
        return result

    def run(self, query, params):
        self.runs += 1
        self.after_run()
        return []

    def commit(self):
        self.before_commit()
        self.commits += 1
        self.committed = True
        self.after_commit()

    def close(self):
        if not self.committed:
            self.rollbacks += 1


@pytest.fixture
def worker_graph(monkeypatch):
    graph = GraphDriver()

    def write(tx, *args):
        tx.run('RETURN $course_id, $version_id, $effective_task_ids')
        return SimpleNamespace(nodes=(), relations=(), downgraded=())

    monkeypatch.setattr(persist_graph, '_write_draft', write)
    return graph, Neo4jRepository(graph)


def run_worker(task, repo, **kwargs):
    url, lease = task
    return persist_graph.run_persist_stage(url, lease, repo=repo, max_attempts=3,
                                          lock_seconds=60, lock_wait_seconds=0, **kwargs)


def task_state(task):
    url, lease = task
    with connect(url) as db:
        return db.execute('SELECT stage, lease_token, t6_seq FROM processing_tasks WHERE id=?',
                          (lease.task_id,)).fetchone()


@pytest.mark.parametrize('taken', ['completed', 'task', 'course'])
def test_old_worker_never_commits_after_takeover(task, worker_graph, taken):
    url, lease = task
    graph, repo = worker_graph

    def takeover():
        with connect(url) as db:
            if taken == 'completed':
                db.execute("UPDATE processing_tasks SET stage='awaiting_review', lease_token=NULL, "
                           "lease_owner=NULL, lease_expires_at=NULL, t6_seq=1 WHERE id=?", (lease.task_id,))
                db.execute('DELETE FROM course_locks WHERE course_id=?', (lease.course_id,))
            elif taken == 'task':
                db.execute("UPDATE processing_tasks SET lease_token=? WHERE id=?", ('b' * 32, lease.task_id))
            else:
                db.execute('UPDATE course_locks SET token=? WHERE course_id=?', ('b' * 32, lease.course_id))

    graph.after_run = takeover
    outcome = run_worker(task, repo)
    assert graph.commits == 0
    assert outcome.status is persist_graph.PersistStatus.LOST
    assert graph.rollbacks == 1 and graph.closed
    if taken == 'completed':
        assert task_state(task) == ('awaiting_review', None, 1)


def test_normal_commit_holds_fence_and_t6_is_once(task, worker_graph):
    url, lease = task
    graph, repo = worker_graph

    def contender():
        with connect(url) as db:
            db.execute('PRAGMA busy_timeout=0')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute('UPDATE processing_tasks SET lease_token=? WHERE id=?', ('b' * 32, lease.task_id))
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute('UPDATE course_locks SET token=? WHERE course_id=?', ('b' * 32, lease.course_id))

    graph.before_commit = contender
    outcome = run_worker(task, repo)
    assert outcome.status is persist_graph.PersistStatus.ADVANCED
    assert graph.commits == 1 and graph.rollbacks == 0
    assert task_state(task) == ('awaiting_review', None, 1)
    with connect(url) as db:
        assert db.execute('SELECT draft_revision FROM courses WHERE id=?', (lease.course_id,)).fetchone() == (1,)
        assert db.execute('SELECT count(*) FROM course_locks').fetchone() == (0,)


def test_t6_failure_leaves_graph_invisible_for_takeover(task, worker_graph, monkeypatch):
    graph, repo = worker_graph

    class Crash(BaseException):
        pass

    def crash(*args):
        raise Crash()

    monkeypatch.setattr(persist_graph, '_t6_in', crash, raising=False)
    with pytest.raises(Crash):
        run_worker(task, repo)
    assert graph.commits == 1
    assert task_state(task)[0] == 'persisting' and task_state(task)[2] is None


def test_lost_commit_ack_is_not_replayed(task, worker_graph):
    from neo4j.exceptions import ServiceUnavailable
    graph, repo = worker_graph

    def lost_ack():
        raise ServiceUnavailable('commit response lost')

    graph.after_commit = lost_ack
    outcome = run_worker(task, repo)
    assert graph.commits == graph.runs == 1
    assert outcome.status is persist_graph.PersistStatus.RELEASED
    assert task_state(task)[0] == 'persisting' and task_state(task)[2] is None


@pytest.mark.parametrize('error', [sqlite3.OperationalError('exit'), task_leases.LeaseLost('exit'), RuntimeError('exit')])
def test_release_failure_after_completed_t6_keeps_success(task, worker_graph, monkeypatch, error):
    graph, repo = worker_graph
    monkeypatch.setattr(course_locks, 'release', lambda *a: (_ for _ in ()).throw(error))
    outcome = run_worker(task, repo)
    assert outcome.status is persist_graph.PersistStatus.ADVANCED
    assert task_state(task) == ('awaiting_review', None, 1)


@pytest.mark.parametrize('readback_fails', [False, True])
def test_sqlite_commit_ack_loss_is_read_back_not_replayed(task, worker_graph, monkeypatch, readback_fails):
    graph, repo = worker_graph
    original = persist_graph.persist_transaction

    @contextmanager
    def lost_ack(*args):
        with original(*args) as db:
            yield db
        if readback_fails:
            monkeypatch.setattr(persist_graph, 'connect', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError()))
        raise sqlite3.OperationalError('sqlite ack lost after commit')

    monkeypatch.setattr(persist_graph, 'persist_transaction', lost_ack)
    monkeypatch.setattr(persist_graph, '_release', lambda *a, **kw: pytest.fail('must not release uncertain/completed T6'))
    outcome = run_worker(task, repo)
    expected = persist_graph.PersistStatus.LOST if readback_fails else persist_graph.PersistStatus.ADVANCED
    assert outcome.status is expected and graph.commits == 1
    assert task_state(task) == ('awaiting_review', None, 1)


def test_cutoff_during_graph_statement_rolls_back(task, worker_graph):
    from app.repositories.lease_guard import LeaseGuard
    now = [0.0]
    guard = LeaseGuard(60, last_success=0, clock=lambda: now[0])
    graph, repo = worker_graph
    graph.after_run = lambda: now.__setitem__(0, 40)
    outcome = run_worker(task, repo, task_guard=guard)
    assert outcome.status is persist_graph.PersistStatus.LOST
    assert graph.runs == 1 and graph.commits == 0 and graph.rollbacks == 1


def test_normal_t6_loss_signal_is_not_retroactive(task, worker_graph, monkeypatch):
    from app.repositories.lease_guard import LeaseGuard
    guard = LeaseGuard(60, last_success=0, clock=lambda: 0)
    original = persist_graph._t6_in

    def done(db, lease):
        seq = original(db, lease)
        guard.lose()  # Heartbeat notices the token cleared by our normal T6.
        return seq

    monkeypatch.setattr(persist_graph, '_t6_in', done)
    graph, repo = worker_graph
    assert run_worker(task, repo, task_guard=guard).status is persist_graph.PersistStatus.ADVANCED
    assert graph.commits == 1 and task_state(task) == ('awaiting_review', None, 1)


def test_cutoff_after_fence_validation_before_dispatch_rolls_back(task, worker_graph, monkeypatch):
    from app.repositories.lease_guard import LeaseGuard
    from app.repositories.neo4j import ExplicitTransaction
    now = [0.0]
    guard = LeaseGuard(60, last_success=0, clock=lambda: now[0])
    original_commit = ExplicitTransaction.commit

    def paused_before_dispatch(tx):
        # Both the DB fence and outer worker check passed, but the thread is
        # paused just before the transaction's own final dispatch check.
        now[0] = 40
        return original_commit(tx)

    monkeypatch.setattr(ExplicitTransaction, 'commit', paused_before_dispatch)
    graph, repo = worker_graph
    outcome = run_worker(task, repo, task_guard=guard)
    assert outcome.status is persist_graph.PersistStatus.LOST
    assert graph.commits == 0 and graph.rollbacks == 1
    assert task_state(task)[0] == 'persisting' and task_state(task)[2] is None


def test_cutoff_after_commit_dispatch_keeps_fence_and_finishes_t6(task, worker_graph):
    from app.repositories.lease_guard import LeaseGuard
    now = [0.0]
    guard = LeaseGuard(60, last_success=0, clock=lambda: now[0])
    url, lease = task
    graph, repo = worker_graph

    def paused_after_dispatch():
        # ExplicitTransaction has sent COMMIT; a lost heartbeat/cutoff now is
        # not proof of rollback. The fence still excludes both takeover writes.
        now[0] = 40
        guard.lose()
        with connect(url) as db:
            db.execute('PRAGMA busy_timeout=0')
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute('UPDATE processing_tasks SET lease_token=? WHERE id=?', ('b' * 32, lease.task_id))
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute('UPDATE course_locks SET token=? WHERE course_id=?', ('b' * 32, lease.course_id))

    graph.before_commit = paused_after_dispatch
    outcome = run_worker(task, repo, task_guard=guard)
    assert outcome.status is persist_graph.PersistStatus.ADVANCED
    assert graph.commits == 1 and graph.rollbacks == 0
    assert task_state(task) == ('awaiting_review', None, 1)
    with connect(url) as db:
        assert db.execute('SELECT draft_revision FROM courses WHERE id=?', (lease.course_id,)).fetchone() == (1,)


def test_fence_wait_uses_remaining_absolute_budget(task):
    import time
    url, lease = task
    lock = course_locks.try_acquire(url, lease.course_id, holder='worker', lease_seconds=60)
    with connect(url) as writer:
        writer.execute('BEGIN IMMEDIATE')
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError):
            with task_leases.persist_transaction(url, lease, lock.token, deadline=started + .1):
                pytest.fail('lock must not be acquired')
        assert time.monotonic() - started < 1
        writer.execute('ROLLBACK')
    with connect(url) as db:
        assert db.execute('SELECT lease_token, stage FROM processing_tasks WHERE id=?',
                          (lease.task_id,)).fetchone() == (lease.token, 'persisting')


def test_expired_fence_deadline_sends_no_begin(task, monkeypatch):
    import time
    from app.repositories.sqlite import SQLiteDeadlineExceeded
    url, lease = task
    statements = []
    original = sqlite3.connect
    class Recording(sqlite3.Connection):
        def execute(self, query, *args):
            statements.append(query)
            return super().execute(query, *args)
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: original(*a, **kw, factory=Recording))
    with pytest.raises(SQLiteDeadlineExceeded):
        with task_leases.persist_transaction(url, lease, 'token', deadline=time.monotonic() - 1):
            pass
    assert 'BEGIN IMMEDIATE' not in statements


def test_fence_acquired_clock_precedes_validation_and_callback_error_rolls_back(task, monkeypatch):
    url, lease = task
    lock = course_locks.try_acquire(url, lease.course_id, holder='worker', lease_seconds=60)
    events = []
    original = sqlite3.connect
    class Recording(sqlite3.Connection):
        def execute(self, query, *args):
            events.append(query)
            return super().execute(query, *args)
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: original(*a, **kw, factory=Recording))
    def acquired(timestamp):
        assert isinstance(timestamp, float)
        events.append('acquired')
    with task_leases.persist_transaction(url, lease, lock.token, on_acquired=acquired):
        pass
    validation = next(i for i, q in enumerate(events) if 'SELECT 1 FROM processing_tasks AS t' in q)
    assert events.index('BEGIN IMMEDIATE') < events.index('acquired') < validation
    def bad_callback(timestamp):
        raise ValueError('callback error')
    with pytest.raises(ValueError, match='callback error'):
        with task_leases.persist_transaction(url, lease, lock.token, on_acquired=bad_callback):
            pass
    assert 'ROLLBACK' in events
    with connect(url) as db:
        db.execute('PRAGMA busy_timeout=0')
        db.execute('BEGIN IMMEDIATE')
        db.execute('ROLLBACK')
