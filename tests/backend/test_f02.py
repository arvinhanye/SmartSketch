"""F02: scoped graph boundary; no test contacts a Neo4j server."""

import importlib
import importlib.util
import traceback
from types import SimpleNamespace

import pytest

from app.config import Settings

QUERY = "MATCH (n {course_id: $course_id, version_id: $version_id}) RETURN n"
DRAFT_QUERY = (
    "MATCH (n {course_id: $course_id, version_id: $version_id}) "
    "WHERE n.contrib_manual OR any(t IN n.contrib_tasks WHERE t IN $effective_task_ids) "
    "RETURN n"
)


@pytest.fixture
def api():
    # An assertion (rather than a collection error) records the missing F02 feature in RED.
    assert importlib.util.find_spec("app.repositories.neo4j"), "F02 scoped repository is missing"
    return importlib.import_module("app.repositories.neo4j")


class FakeDriver:
    """Capture the official execute_query boundary without opening a network connection."""

    def __init__(self, *, failure=None, fail_at="execute"):
        self.calls = []
        self.failure = failure
        self.fail_at = fail_at
        self.closed = False
        self.verified = False

    def verify_connectivity(self):
        self.verified = True
        if self.fail_at == "verify" and self.failure:
            raise self.failure

    def execute_query(self, query, *, parameters_, routing_, database_):
        self.calls.append((query, parameters_, routing_, database_))
        if self.fail_at == "execute" and self.failure:
            raise self.failure
        return SimpleNamespace(records=[{"id": "node-1"}])

    def close(self):
        self.closed = True
        if self.fail_at == "close" and self.failure:
            raise self.failure


@pytest.mark.parametrize("field", ["course_id", "version_id"])
@pytest.mark.parametrize("value", [None, "", "  ", 123])
def test_invalid_scope_rejected_before_execution(api, field, value):
    values = {"course_id": "course-1", "version_id": "version-1", field: value}
    with pytest.raises(api.GraphScopeError):
        api.GraphScope(**values)


@pytest.mark.parametrize("method", ["read", "write"])
@pytest.mark.parametrize("query", [
    "MATCH (n) RETURN n",
    "MATCH (n {course_id: $course_id}) RETURN n",
    "MATCH (n {version_id: $version_id}) RETURN n",
    "RETURN $course_id_suffix, $version_id_suffix",
    'RETURN "$course_id", \'$version_id\'',
    "RETURN 1 // $course_id $version_id",
    "RETURN 1 /* $course_id $version_id */",
    "RETURN `$course_id`, `$version_id`",
])
def test_scope_tokens_must_be_executable_parameters(api, method, query):
    driver = FakeDriver()
    repo = api.Neo4jRepository(driver)
    kwargs = {"reader": "student"} if method == "read" else {}
    with pytest.raises(api.GraphScopeError):
        getattr(repo, method)(query, api.GraphScope("course-1", "version-1"), **kwargs)
    assert driver.calls == []


def test_parameterized_read_preserves_query_and_authoritative_scope(api):
    driver = FakeDriver()
    repo = api.Neo4jRepository(driver)
    course = "course' // data, not Cypher"
    params = {"course_id": "other", "version_id": "draft", "name": "O'Reilly"}
    query = QUERY + " LIMIT $limit"
    result = repo.read(query, api.GraphScope(course, "version-1"), reader="student",
                       parameters={**params, "limit": 10})
    assert result == [{"id": "node-1"}]
    assert driver.calls == [(query, {"course_id": course, "version_id": "version-1",
                                    "name": "O'Reilly", "limit": 10}, "r", "neo4j")]
    assert params["course_id"] == "other"


@pytest.mark.parametrize("reader", ["teacher", "student"])
def test_published_reads_need_no_effective_task_set(api, reader):
    driver = FakeDriver()
    assert api.Neo4jRepository(driver).read(
        QUERY, api.GraphScope("c", "v1"), reader=reader
    ) == [{"id": "node-1"}]


def test_student_draft_is_rejected_even_with_effective_tasks(api):
    driver = FakeDriver()
    with pytest.raises(api.GraphScopeError):
        api.Neo4jRepository(driver).read(
            DRAFT_QUERY, api.GraphScope("c", "draft", ("task-1",)), reader="student"
        )
    assert driver.calls == []


@pytest.mark.parametrize("reader", [None, "admin", "", "Teacher"])
def test_unknown_read_intent_is_rejected(api, reader):
    driver = FakeDriver()
    with pytest.raises(api.GraphScopeError):
        api.Neo4jRepository(driver).read(QUERY, api.GraphScope("c", "v"), reader=reader)
    assert driver.calls == []


@pytest.mark.parametrize("method", ["read", "write"])
def test_draft_without_sqlite_effective_task_set_is_rejected(api, method):
    driver = FakeDriver()
    kwargs = {"reader": "teacher"} if method == "read" else {}
    with pytest.raises(api.GraphScopeError):
        getattr(api.Neo4jRepository(driver), method)(
            DRAFT_QUERY, api.GraphScope("c", "draft"),
            parameters={"effective_task_ids": ["caller-cannot-supply-V"]}, **kwargs
        )
    assert driver.calls == []


@pytest.mark.parametrize("suffix", ["", " // $effective_task_ids", " /* $effective_task_ids */",
                                     " + '$effective_task_ids'"])
def test_draft_query_must_reference_effective_task_parameter(api, suffix):
    driver = FakeDriver()
    with pytest.raises(api.GraphScopeError):
        api.Neo4jRepository(driver).read(
            QUERY + suffix, api.GraphScope("c", "draft", ()), reader="teacher"
        )
    assert driver.calls == []


@pytest.mark.parametrize("tasks", [(), ("task-a", "task-b")])
def test_draft_accepts_empty_V_and_binds_authoritative_snapshot(api, tasks):
    driver = FakeDriver()
    task_snapshot = list(tasks)
    scope = api.GraphScope("c", "draft", task_snapshot)
    task_snapshot.append("later-task")
    api.Neo4jRepository(driver).read(
        DRAFT_QUERY, scope, reader="teacher",
        parameters={"effective_task_ids": ["failed-task"]},
    )
    assert driver.calls[0][1] == {"course_id": "c", "version_id": "draft",
                                  "effective_task_ids": list(tasks)}


@pytest.mark.parametrize("tasks", ["task-a", [None], [""], ["  "], [4]])
def test_effective_task_set_rejects_malformed_ids(api, tasks):
    with pytest.raises(api.GraphScopeError):
        api.GraphScope("c", "draft", tasks)


def test_write_is_parameterized_and_uses_write_routing(api):
    driver = FakeDriver()
    query = "MERGE (n {course_id: $course_id, version_id: $version_id, kp_id: $kp_id}) RETURN n"
    assert api.Neo4jRepository(driver).write(
        query, api.GraphScope("c", "v1"), parameters={"kp_id": "k1", "course_id": "bad"}
    ) == [{"id": "node-1"}]
    assert driver.calls == [(query, {"kp_id": "k1", "course_id": "c", "version_id": "v1"},
                              "w", "neo4j")]


def test_factory_uses_settings_verifies_connectivity_and_closes(api, monkeypatch):
    driver = FakeDriver()
    calls = []
    def factory(uri, *, auth):
        calls.append((uri, auth))
        return driver
    monkeypatch.setattr(api.GraphDatabase, "driver", factory)
    repo = api.Neo4jRepository.from_settings(Settings(
        NEO4J_URI="bolt://fixture.invalid:7687", NEO4J_USER="fixture-user",
        NEO4J_PASSWORD="fixture-password",
    ))
    assert calls == [("bolt://fixture.invalid:7687", ("fixture-user", "fixture-password"))]
    assert driver.verified
    repo.close()
    assert driver.closed


@pytest.mark.parametrize("error_type", ["ServiceUnavailable", "SessionExpired", "AuthError", "OSError"])
@pytest.mark.parametrize("stage", ["factory", "verify", "execute", "close"])
def test_connection_failures_are_stable_and_redacted(api, monkeypatch, caplog, error_type, stage):
    from neo4j import exceptions

    error_type = OSError if error_type == "OSError" else getattr(exceptions, error_type)
    secret = "synthetic-password-do-not-surface"
    driver = FakeDriver(failure=error_type(secret), fail_at=stage)
    def factory(uri, *, auth):
        if stage == "factory":
            raise error_type(secret)
        return driver
    monkeypatch.setattr(api.GraphDatabase, "driver", factory)
    with pytest.raises(api.RepositoryConnectionError) as caught:
        if stage in {"factory", "verify"}:
            api.Neo4jRepository.from_settings(Settings(NEO4J_PASSWORD=secret))
        elif stage == "close":
            api.Neo4jRepository(driver).close()
        else:
            api.Neo4jRepository(driver).read(QUERY, api.GraphScope("c", "v"), reader="student")
    assert caught.value.code == "NEO4J_CONNECTION_FAILED"
    assert secret not in str(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert secret not in caplog.text
    if stage == "verify":
        assert driver.closed


def test_query_error_does_not_leak_driver_text(api, caplog):
    from neo4j.exceptions import Neo4jError

    driver = FakeDriver(failure=Neo4jError("sensitive query content"))
    with pytest.raises(api.RepositoryError) as caught:
        api.Neo4jRepository(driver).write(QUERY, api.GraphScope("c", "v"))
    assert caught.value.code == "NEO4J_QUERY_FAILED"
    assert "sensitive query content" not in "".join(traceback.format_exception(caught.value))
    assert "sensitive query content" not in caplog.text
