"""Parameterized graph access (F02, LEASE-23, PUB-27).

Cypher is trusted repository code, never user input. Parameter-token validation
catches omitted scope; it is not a Cypher parser or proof that every matched
entity has a scope/visibility predicate. Domain repositories must implement those
predicates, including relationship endpoints and evidence visibility (§8.4).
"""

import re
import time
import math
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

from neo4j import AsyncGraphDatabase, GraphDatabase, Query
from neo4j.exceptions import AuthError, DriverError, Neo4jError, ServiceUnavailable, SessionExpired

from app.config import Settings
from app.repositories.persist_transport import AsyncDriverFactory, PersistTransport, TransportTimeout


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


class RepositoryTransportTimeout(RepositoryError):
    code = 'NEO4J_TRANSPORT_TIMEOUT'

    def __init__(self, phase: str, commit_started: bool) -> None:
        self.phase = phase
        self.commit_started = commit_started
        super().__init__()


class PersistTransaction:
    """Scoped facade for one bounded transport attempt."""
    def __init__(self, transport: PersistTransport, scope: 'GraphScope') -> None:
        self._transport = transport
        self.scope = scope

    @property
    def deadline(self) -> float:
        return self._transport.deadline

    @property
    def commit_started(self) -> bool:
        return self._transport.commit_started

    @property
    def committed(self) -> bool:
        return self._transport.committed

    def run(self, query: str, parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        bound = _parameters(query, self.scope, parameters)
        try:
            return self._transport.run(query, bound)
        except TransportTimeout as exc:
            raise RepositoryTransportTimeout(exc.phase, exc.commit_started) from None
        except _CONNECTION_ERRORS:
            raise RepositoryConnectionError() from None
        except (Neo4jError, DriverError):
            raise RepositoryError() from None

    def commit(self, *, started_at: float) -> None:
        try:
            self._transport.commit(started_at=started_at)
        except TransportTimeout as exc:
            raise RepositoryTransportTimeout(exc.phase, exc.commit_started) from None
        except _CONNECTION_ERRORS:
            raise RepositoryConnectionError() from None
        except (Neo4jError, DriverError):
            raise RepositoryError() from None


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

    def session(self, *, database: str) -> Any: ...

    def close(self) -> None: ...


T = TypeVar("T")


class ScopedTransaction:
    """One statement runner inside an explicit write transaction (F06).

    Every statement passes the same scope-token validation as ``Neo4jRepository``
    reads and writes, and receives the scope's course, version and V.
    """

    def __init__(self, tx: Any, scope: GraphScope) -> None:
        self._tx = tx
        self.scope = scope

    def run(self, query: str, parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        bound = _parameters(query, self.scope, parameters)
        return [dict(record) for record in self._tx.run(query, bound)]


class ExplicitTransaction(ScopedTransaction):
    """Worker-only transaction: guarded statements and an explicit commit.

    A dispatched commit can have an uncertain outcome. Neither a lost heartbeat
    nor cleanup may then be interpreted as proof that the graph rolled back.
    """

    def __init__(self, tx: Any, scope: GraphScope, check: Callable[[], None]) -> None:
        super().__init__(tx, scope)
        self._check = check
        self.commit_started = False
        self.committed = False

    def run(self, query: str, parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        self._check()
        rows = super().run(query, parameters)
        self._check()
        return rows

    def commit(self) -> None:
        if self.commit_started:
            raise RuntimeError('explicit transaction commit already dispatched')
        self._check()
        self.commit_started = True
        self._tx.commit()
        self.committed = True


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


class RepositoryDeadlineExceeded(RepositoryError):
    """The caller's deadline had passed; no query was sent."""

    code = "NEO4J_DEADLINE_EXCEEDED"


_READ_DEADLINE: ContextVar[float | None] = ContextVar("graph_read_deadline", default=None)


@contextmanager
def read_deadline(deadline: float) -> Iterator[None]:
    """Bound every graph query in this context by ``deadline`` (``time.monotonic()`` axis).

    QA preparation uses it (ADR-082 决定 3): each query carries the remaining time as the
    server-side transaction timeout, and none is sent once the deadline has passed.
    """
    token = _READ_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _READ_DEADLINE.reset(token)


class Neo4jRepository:
    """Own a synchronous driver and return eager plain-dict records.

    Reads require explicit caller intent; the upstream service authenticates
    course membership and resolves the published version. Internal workers use
    worker intent for V-scoped merging candidates and persisting cycle checks.
    Writes are internal teacher/worker operations, not a student-facing escape
    hatch. ``read``/``write`` are one managed transaction each;
    ``write_transaction`` runs several scoped statements atomically (F06).
    """

    def __init__(self, driver: GraphDriver, *,
                 persist_driver_factory: AsyncDriverFactory | None = None,
                 persist_commit_timeout: float = 2.0,
                 persist_cleanup_timeout: float = 1.0) -> None:
        self._driver = driver
        self._persist_factory = persist_driver_factory
        self._persist_commit_timeout = persist_commit_timeout
        self._persist_cleanup_timeout = persist_cleanup_timeout

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
        return cls(driver, persist_driver_factory=lambda: AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value()),
        ), persist_commit_timeout=settings.TASK_PERSIST_COMMIT_TIMEOUT_SECONDS,
            persist_cleanup_timeout=settings.TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS)

    @contextmanager
    def persist_write_transaction(self, scope: GraphScope, *, check: Callable[[], None],
                                  remaining: Callable[[], float]) -> Iterator[PersistTransaction]:
        if not isinstance(scope, GraphScope):
            raise GraphScopeError('A GraphScope is required')
        if self._persist_factory is None:
            raise RepositoryConnectionError()
        check()
        budget = remaining()
        if not math.isfinite(budget) or budget <= 0:
            raise RepositoryTransportTimeout('open', False)
        transport = PersistTransport(self._persist_factory, deadline=time.monotonic() + budget,
            remaining=remaining, check=check, commit_timeout=self._persist_commit_timeout,
            cleanup_timeout=self._persist_cleanup_timeout)
        primary = False
        try:
            transport.open()
            yield PersistTransaction(transport, scope)
        except BaseException as exc:
            primary = True
            if isinstance(exc, TransportTimeout):
                raise RepositoryTransportTimeout(exc.phase, exc.commit_started) from None
            if isinstance(exc, _CONNECTION_ERRORS):
                raise RepositoryConnectionError() from None
            if isinstance(exc, (Neo4jError, DriverError)):
                raise RepositoryError() from None
            raise
        finally:
            try:
                transport.close()
            except BaseException as exc:
                if primary:
                    logging.getLogger(__name__).warning('persist transport exit failed: NEO4J_QUERY_FAILED')
                elif isinstance(exc, TransportTimeout):
                    raise RepositoryTransportTimeout(exc.phase, exc.commit_started) from None
                else:
                    raise RepositoryError() from None

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

    def write_transaction(self, scope: GraphScope, work: Callable[[ScopedTransaction], T]) -> T:
        """Run ``work`` in one explicit write transaction and commit if it returns.

        The driver may re-run ``work`` after a transient failure (deadlock, leader
        switch), so ``work`` must derive everything from what it reads inside the
        transaction. Exceptions raised by ``work`` itself roll back and propagate
        unchanged; driver failures are redacted like ``read``/``write``.
        """
        if not isinstance(scope, GraphScope):
            raise GraphScopeError("A GraphScope is required")
        try:
            with self._driver.session(database="neo4j") as session:
                return session.execute_write(lambda tx: work(ScopedTransaction(tx, scope)))
        except _CONNECTION_ERRORS:
            raise RepositoryConnectionError() from None
        except (Neo4jError, DriverError):
            raise RepositoryError() from None

    @contextmanager
    def explicit_write_transaction(
        self, scope: GraphScope, *, check: Callable[[], None], timeout: float,
    ) -> Iterator[ExplicitTransaction]:
        """One attempt, never auto-commit/replay the worker's callback.

        ``timeout`` is a server transaction timeout, NOT a client commit-reply
        deadline. All Session/Transaction operations stay on the caller thread.
        """
        if not isinstance(scope, GraphScope):
            raise GraphScopeError('A GraphScope is required')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('transaction timeout must be positive and finite')
        check()
        try:
            with self._driver.session(database='neo4j') as session:
                raw = session.begin_transaction(timeout=timeout)
                try:
                    yield ExplicitTransaction(raw, scope, check)
                finally:
                    # close() rolls back an open uncommitted transaction. Unlike
                    # Transaction.__exit__, it never commits on a normal return.
                    raw.close()
        except _CONNECTION_ERRORS:
            raise RepositoryConnectionError() from None
        except (Neo4jError, DriverError):
            raise RepositoryError() from None

    def _execute(
        self,
        query: str,
        scope: GraphScope,
        parameters: Mapping[str, Any] | None,
        routing: str,
    ) -> list[dict[str, Any]]:
        bound = _parameters(query, scope, parameters)
        statement: str | Query = query
        deadline = _READ_DEADLINE.get()
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RepositoryDeadlineExceeded()
            statement = Query(query, timeout=remaining)
        try:
            result = self._driver.execute_query(
                statement, parameters_=bound, routing_=routing, database_="neo4j"
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
