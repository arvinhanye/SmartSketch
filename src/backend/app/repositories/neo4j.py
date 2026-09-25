"""Parameterized graph access (F02, LEASE-23, PUB-27).

Cypher is trusted repository code, never user input. Parameter-token validation
catches omitted scope; it is not a Cypher parser or proof that every matched
entity has a scope/visibility predicate. Domain repositories must implement those
predicates, including relationship endpoints and evidence visibility (§8.4).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.config import Settings


class GraphScopeError(ValueError):
    """Invalid or missing scope; rejected before contacting the driver."""


class RepositoryError(RuntimeError):
    """Stable, redacted graph repository failure."""

    code = "NEO4J_QUERY_FAILED"

    def __init__(self) -> None:
        super().__init__(self.code)


class RepositoryConnectionError(RepositoryError):
    """Connection establishment, authentication, or connectivity failed."""

    code = "NEO4J_CONNECTION_FAILED"


_CONNECTION_ERRORS = (ServiceUnavailable, SessionExpired, AuthError, OSError)


@dataclass(frozen=True)
class GraphScope:
    """Request-bound scope, with V read once from SQLite by the caller.

    V contains this course's awaiting_review/completed task IDs. None means
    missing; an empty sequence is a valid snapshot (manual contributions only).
    Draft writes require V too: a write may read for MERGE or cycle checking.
    """

    course_id: str
    version_id: str
    effective_task_ids: Sequence[str] | None = None

    def __post_init__(self) -> None:
        for name in ("course_id", "version_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise GraphScopeError(f"{name} is required")
        tasks = self.effective_task_ids
        if tasks is not None:
            if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Sequence):
                raise GraphScopeError("effective_task_ids must be a sequence of task IDs")
            if any(not isinstance(task, str) or not task.strip() for task in tasks):
                raise GraphScopeError("effective_task_ids must contain nonempty task IDs")
            object.__setattr__(self, "effective_task_ids", tuple(tasks))


class QueryResult(Protocol):
    records: Sequence[Mapping[str, Any]]


class GraphDriver(Protocol):
    """The official synchronous driver subset; injectable without network access."""

    def verify_connectivity(self) -> None: ...

    def execute_query(
        self, query: str, *, parameters_: dict[str, Any], routing_: str, database_: str
    ) -> QueryResult: ...

    def close(self) -> None: ...


# Consume quoted strings/identifiers and comments BEFORE considering parameters.
# Only unquoted ASCII parameter names are part of this internal query contract.
_CYPHER_TOKEN = re.compile(
    r"//[^\r\n]*|/\*[\s\S]*?\*/"
    r"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:``|[^`])*`"
    r"|\$([A-Za-z_][\w]*)"
)


def _parameters(
    query: str, scope: GraphScope, extra: Mapping[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise GraphScopeError("A scoped Cypher query is required")
    names = {match.group(1) for match in _CYPHER_TOKEN.finditer(query) if match.group(1)}
    required = {"course_id", "version_id"}
    if scope.version_id == "draft":
        if scope.effective_task_ids is None:
            raise GraphScopeError("Draft queries require effective_task_ids from SQLite")
        required.add("effective_task_ids")
    if not required <= names:
        raise GraphScopeError("Cypher is missing required scope parameters")
    params = dict(extra or {})
    params.update(course_id=scope.course_id, version_id=scope.version_id)
    # Reserved even for published queries; caller extras never supply scope or V.
    params.pop("effective_task_ids", None)
    if scope.effective_task_ids is not None:
        params["effective_task_ids"] = list(scope.effective_task_ids)
    return params


class Neo4jRepository:
    """Own a synchronous driver and return eager plain-dict records.

    Reads require explicit caller intent; the upstream service authenticates
    course membership and resolves the published version. Internal workers use
    worker intent for V-scoped merging candidates and persisting cycle checks.
    Writes are internal teacher/worker operations, not a student-facing escape
    hatch. Each method is one managed transaction; multi-query atomic operations
    belong to later work.
    """

    def __init__(self, driver: GraphDriver) -> None:
        self._driver = driver

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jRepository":
        """Construct and verify the official driver; never log settings/errors."""
        driver = None
        try:
            driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value()),
            )
            driver.verify_connectivity()
        except Exception:
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass  # Preserve the original stable connection failure.
            raise RepositoryConnectionError() from None
        return cls(driver)

    def read(
        self,
        query: str,
        scope: GraphScope,
        *,
        reader: Literal["teacher", "student", "worker"],
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if reader not in {"teacher", "student", "worker"}:
            raise GraphScopeError("Read intent must be teacher, student or worker")
        if reader == "student" and scope.version_id == "draft":
            raise GraphScopeError("Student reads require a published version")
        return self._execute(query, scope, parameters, "r")

    def write(
        self,
        query: str,
        scope: GraphScope,
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._execute(query, scope, parameters, "w")

    def _execute(
        self,
        query: str,
        scope: GraphScope,
        parameters: Mapping[str, Any] | None,
        routing: str,
    ) -> list[dict[str, Any]]:
        bound = _parameters(query, scope, parameters)
        try:
            result = self._driver.execute_query(
                query, parameters_=bound, routing_=routing, database_="neo4j"
            )
            return [dict(record) for record in result.records]
        except _CONNECTION_ERRORS:
            raise RepositoryConnectionError() from None
        except Exception:
            raise RepositoryError() from None

    def close(self) -> None:
        """Release the owned connection pool (also for injected drivers)."""
        try:
            self._driver.close()
        except Exception:
            raise RepositoryConnectionError() from None
