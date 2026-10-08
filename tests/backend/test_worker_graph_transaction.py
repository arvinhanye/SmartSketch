"""Explicit worker transactions: scope, guard checks, no callback retries."""

from types import SimpleNamespace
import pytest
from neo4j.exceptions import ServiceUnavailable

from app.repositories.neo4j import GraphScope, Neo4jRepository, RepositoryConnectionError
from app.repositories.task_leases import LeaseLost

SCOPE = GraphScope('course', 'draft', ())
QUERY = 'RETURN $course_id, $version_id, $effective_task_ids'


class RawTransaction:
    def __init__(self):
        self.runs = self.commits = self.rollbacks = self.closes = 0
        self.after_run = lambda: None
        self.fail_commit = False
        self.committed = False

    def run(self, query, params):
        self.runs += 1
        self.after_run()
        return [{'value': 1}]

    def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise ServiceUnavailable('private host/token')
        self.committed = True

    def close(self):
        self.closes += 1
        if not self.committed:
            self.rollbacks += 1


class Session:
    def __init__(self, raw):
        self.raw = raw
        self.closed = False
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def begin_transaction(self, *, timeout):
        self.timeout = timeout
        return self.raw


@pytest.fixture
def graph():
    raw = RawTransaction()
    session = Session(raw)
    repo = Neo4jRepository(SimpleNamespace(session=lambda **kw: session))
    return repo, raw, session


def test_no_implicit_commit(graph):
    repo, raw, session = graph
    with repo.explicit_write_transaction(SCOPE, check=lambda: None, timeout=10) as tx:
        assert tx.run(QUERY) == [{'value': 1}]
    assert raw.commits == 0 and raw.rollbacks == 1 and raw.closes == 1
    assert session.closed and session.timeout == 10


def test_explicit_commit_once(graph):
    repo, raw, _ = graph
    with repo.explicit_write_transaction(SCOPE, check=lambda: None, timeout=10) as tx:
        tx.run(QUERY)
        tx.commit()
        with pytest.raises(RuntimeError):
            tx.commit()
    assert raw.commits == 1 and raw.rollbacks == 0


@pytest.mark.parametrize('when', ['before', 'after'])
def test_lost_guard_stops_statements_and_commit(graph, when):
    repo, raw, session = graph
    lost = [when == 'before']
    raw.after_run = lambda: lost.__setitem__(0, True)

    def check():
        if lost[0]:
            raise LeaseLost('expired')

    with pytest.raises(LeaseLost):
        with repo.explicit_write_transaction(SCOPE, check=check, timeout=10) as tx:
            tx.run(QUERY)
            tx.commit()
    assert raw.runs == (0 if when == 'before' else 1)
    assert raw.commits == 0 and session.closed == (when == 'after')


def test_commit_failure_is_redacted_and_never_replayed(graph):
    repo, raw, session = graph
    raw.fail_commit = True
    with pytest.raises(RepositoryConnectionError) as error:
        with repo.explicit_write_transaction(SCOPE, check=lambda: None, timeout=10) as tx:
            tx.run(QUERY)
            tx.commit()
    assert str(error.value) == 'NEO4J_CONNECTION_FAILED'
    assert raw.runs == 1 and raw.commits == 1 and raw.closes == 1 and session.closed


def test_scope_validation_precedes_graph_statement(graph):
    from app.repositories.neo4j import GraphScopeError
    repo, raw, _ = graph
    with pytest.raises(GraphScopeError):
        with repo.explicit_write_transaction(SCOPE, check=lambda: None, timeout=10) as tx:
            tx.run('RETURN 1')
    assert raw.runs == 0 and raw.commits == 0


def test_persist_factory_missing_never_falls_back():
    calls = []
    repo = Neo4jRepository(SimpleNamespace(session=lambda **kw: calls.append(kw)))
    from app.repositories.neo4j import RepositoryError
    with pytest.raises(RepositoryError):
        with repo.persist_write_transaction(SCOPE, check=lambda: None, remaining=lambda: 1):
            pass
    assert calls == []


def _async_repo(fake, **kwargs):
    return Neo4jRepository(SimpleNamespace(), persist_driver_factory=fake.factory, **kwargs)


def test_persist_scope_and_reserved_parameters():
    from test_worker_persist_transport import FakeDriver
    from app.repositories.neo4j import GraphScopeError
    fake = FakeDriver()
    repo = _async_repo(fake)
    with repo.persist_write_transaction(SCOPE, check=lambda: None, remaining=lambda: 1) as tx:
        with pytest.raises(GraphScopeError):
            tx.run('RETURN 1')
        assert not any(name == 'run' for name, _ in fake.calls)
        tx.run(QUERY, {'course_id': 'foreign', 'version_id': 'foreign',
                       'effective_task_ids': ['foreign']})
        assert fake.parameters == {'course_id': 'course', 'version_id': 'draft',
                                   'effective_task_ids': []}


def test_persist_repeat_commit_after_uncertain_result_is_rejected():
    from test_worker_persist_transport import FakeDriver
    from app.repositories.neo4j import RepositoryTransportTimeout
    import time
    fake = FakeDriver(commit_delay=10)
    repo = _async_repo(fake, persist_commit_timeout=.02)
    with repo.persist_write_transaction(SCOPE, check=lambda: None, remaining=lambda: 1) as tx:
        with pytest.raises(RepositoryTransportTimeout):
            tx.commit(started_at=time.monotonic())
        assert tx.commit_started and not tx.committed
        with pytest.raises(RuntimeError):
            tx.commit(started_at=time.monotonic())
    assert fake.commit_calls == 1
    assert not fake.open_resources


def test_persist_partial_start_error_is_redacted():
    from test_worker_persist_transport import FakeDriver
    fake = FakeDriver(begin_error=True)
    repo = _async_repo(fake)
    with pytest.raises(RepositoryConnectionError) as caught:
        with repo.persist_write_transaction(SCOPE, check=lambda: None, remaining=lambda: 1):
            pass
    assert 'private-host' not in str(caught.value)
    assert 'private-token' not in str(caught.value)
    assert not fake.open_resources


def test_exit_error_preserves_primary_lease_loss():
    from test_worker_persist_transport import FakeDriver
    fake = FakeDriver(tx_close_delay=10)
    repo = _async_repo(fake, persist_cleanup_timeout=.02)
    with pytest.raises(LeaseLost):
        with repo.persist_write_transaction(SCOPE, check=lambda: None, remaining=lambda: 1):
            raise LeaseLost('lost')
    assert not fake.open_resources


def test_real_driver_dns_start_failure_is_redacted(monkeypatch):
    import socket
    from neo4j import AsyncGraphDatabase
    def fail_dns(*args, **kwargs):
        raise socket.gaierror(socket.EAI_NONAME, 'fixture lookup failed')
    monkeypatch.setattr(socket, 'getaddrinfo', fail_dns)
    repo = Neo4jRepository(SimpleNamespace(), persist_driver_factory=lambda: AsyncGraphDatabase.driver(
        'bolt://private-host-fixture.invalid:7687', auth=('fixture-user', 'private-token')))
    with pytest.raises(RepositoryConnectionError) as caught:
        with repo.persist_write_transaction(SCOPE, check=lambda: None, remaining=lambda: 1):
            pass
    assert str(caught.value) == 'NEO4J_CONNECTION_FAILED'
    assert 'private-host' not in str(caught.value) and 'private-token' not in str(caught.value)
