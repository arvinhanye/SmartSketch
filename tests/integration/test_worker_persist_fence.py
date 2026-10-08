"""ADR-091: actual Neo4j rollback/commit and injected commit-boundary faults.

Only SMARTSKETCH_TEST_NEO4J_* fixtures; never use the application's database.
Faults are injected around the public transaction boundary, not a claim of a
hard network deadline. Each course is unique and cleaned by the graph fixture.
"""

from contextlib import contextmanager
import sqlite3
import threading
import time
import uuid

import pytest

from app.repositories.neo4j import GraphScope, ScopedTransaction, RepositoryConnectionError
from app.repositories.graph_relations import lock_draft
from app.repositories.sqlite import connect
from app.repositories import task_leases
from app.workers import persist_graph
from test_f13 import (db_url, storage, graph, live, _persisting, _persist, _counts,
                      _visible_to_teacher, _row)


def course(url, cid):
    uid = uuid.uuid4().hex
    with connect(url) as db:
        db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, 'teacher')",
                   (uid, uid, '$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA'))
        db.execute("INSERT INTO courses (id, name, teacher_id) VALUES (?, 'test', ?)", (cid, uid))


class BoundaryRepo:
    def __init__(self, repo, *, before_run=lambda: None, commit=lambda tx: tx.commit()):
        self.repo = repo
        self.before_run = before_run
        self.commit_action = commit

    def wrap(self, tx):
        owner = self

        class Boundary:
            def __init__(self):
                self.scope = tx.scope

            def run(self, query, parameters=None):
                if 'DraftWriteGuard' in query:
                    owner.before_run()
                return tx.run(query, parameters)

            def commit(self):
                return owner.commit_action(tx)

        return Boundary()

    @contextmanager
    def explicit_write_transaction(self, scope, **kwargs):
        with self.repo.explicit_write_transaction(scope, **kwargs) as tx:
            yield self.wrap(tx)

    def read(self, *args, **kwargs):
        return self.repo.read(*args, **kwargs)

    def write_transaction(self, *args, **kwargs):
        scope, work = args
        return self.repo.write_transaction(scope, lambda tx: work(self.wrap(tx)))


@live
def test_live_guard_wait_old_worker_rolls_back_after_takeover(db_url, storage, graph):
    course(db_url, graph.course)
    lease = _persisting(db_url, storage, graph, [], ['概念11'])
    dispatched = threading.Event()
    results, failures = [], []
    repo = BoundaryRepo(graph.repo, before_run=dispatched.set)

    def worker():
        try:
            results.append(_persist(db_url, lease, repo))
        except BaseException as exc:
            failures.append(exc)

    with graph.repo._driver.session(database='neo4j') as session:
        blocker = session.begin_transaction(timeout=30)
        try:
            lock_draft(ScopedTransaction(blocker, GraphScope(graph.course, 'draft', ())))
            blocker.run("CREATE (:KnowledgePoint {course_id:$c, version_id:'draft', kp_id:'sentinel', "
                        "name:'new-owner', status:'confirmed', contrib_manual:true, contrib_tasks:[]})",
                        c=graph.course).consume()
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            assert dispatched.wait(10), 'worker never reached graph guard'
            with connect(db_url) as db:
                db.execute('UPDATE processing_tasks SET lease_token=? WHERE id=?', ('b' * 32, lease.task_id))
                db.execute('UPDATE course_locks SET token=? WHERE course_id=?', ('b' * 32, graph.course))
            blocker.commit()
        finally:
            blocker.close()
    thread.join(15)
    assert not thread.is_alive() and not failures
    assert results[0].status is persist_graph.PersistStatus.LOST
    assert graph.q("MATCH (n:KnowledgePoint {course_id:$c}) RETURN collect(n.kp_id) AS ids",
                   c=graph.course) == [{'ids': ['sentinel']}]
    assert _row(db_url, lease.task_id)['t6_seq'] is None


@live
def test_live_lost_ack_after_actual_commit_recovers_once(db_url, storage, graph):
    course(db_url, graph.course)
    lease = _persisting(db_url, storage, graph, [], ['概念11'])
    calls = []

    def lost_ack(tx):
        tx.commit()  # Actual database COMMIT succeeds, the injected caller loses its ack.
        calls.append('commit')
        raise RepositoryConnectionError()

    result = _persist(db_url, lease, BoundaryRepo(graph.repo, commit=lost_ack))
    assert result.status is persist_graph.PersistStatus.RELEASED
    assert calls == ['commit'] and _counts(graph)['nodes'] == 1
    assert _visible_to_teacher(graph, db_url) == []
    with connect(db_url) as db:
        db.execute('UPDATE processing_tasks SET not_before=unixepoch() WHERE id=?', (lease.task_id,))
    again = task_leases.claim_next(db_url, owner='new', lease_seconds=60, max_attempts=3)
    assert again is not None and again.task_id == lease.task_id
    assert _persist(db_url, again, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    assert _counts(graph)['nodes'] == 1 and _row(db_url, lease.task_id)['t6_seq'] == 1
    with connect(db_url) as db:
        assert db.execute('SELECT draft_revision FROM courses WHERE id=?', (graph.course,)).fetchone() == (1,)


@live
@pytest.mark.parametrize('fault', ['resume', 'disconnect'])
def test_live_commit_stall_fences_writers_then_releases(db_url, storage, graph, fault):
    course(db_url, graph.course)
    lease = _persisting(db_url, storage, graph, [], ['概念11'])
    entered, resume = threading.Event(), threading.Event()
    outcomes, failures, waited = [], [], []

    def commit(tx):
        started = time.monotonic()
        entered.set()
        if not resume.wait(10):
            raise RepositoryConnectionError()
        waited.append(time.monotonic() - started)
        if fault == 'disconnect':
            raise RepositoryConnectionError()
        tx.commit()

    def worker():
        try:
            outcomes.append(_persist(db_url, lease, BoundaryRepo(graph.repo, commit=commit)))
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert entered.wait(10)
        with connect(db_url) as db:
            db.execute('PRAGMA busy_timeout=0')
            # The fence covers all writers, not only this course/task's row.
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?', (graph.course,))
    finally:
        resume.set()
        thread.join(15)
    assert not thread.is_alive() and not failures
    assert waited and 0 < waited[0] < 10
    expected = persist_graph.PersistStatus.ADVANCED if fault == 'resume' else persist_graph.PersistStatus.RELEASED
    assert outcomes[0].status is expected
    with connect(db_url) as db:
        db.execute('BEGIN IMMEDIATE')  # Writer released after the injected boundary fault.
        assert db.execute('SELECT count(*) FROM course_locks').fetchone() == (0,)
        db.execute('ROLLBACK')
    assert _counts(graph)['nodes'] == (1 if fault == 'resume' else 0)
