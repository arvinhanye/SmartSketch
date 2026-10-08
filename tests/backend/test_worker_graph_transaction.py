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
