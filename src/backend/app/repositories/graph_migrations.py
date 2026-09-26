"""F03 repeatable Neo4j DDL and explicit vector-space write boundaries.

DDL is not an all-or-nothing batch. A failure leaves earlier schema objects in
place; repair the duplicate data or service and rerun ``apply_migrations``.
No migration path drops an index, property, node, or relationship.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol, Sequence


MIGRATION = Path(__file__).resolve().parents[2] / 'migrations' / 'neo4j' / '001_constraints.cypher'
SPACE_RE = re.compile(r'^(?:fake|real/.+)/([1-9][0-9]*)$')


class GraphMigrationError(RuntimeError):
    """A schema or vector write did not complete; driver details are redacted."""


class VectorSpaceError(ValueError):
    """A vector cannot be written in the selected embedding space."""


class Driver(Protocol):
    def execute_query(self, query: str, *, parameters_: dict, routing_: str, database_: str): ...


class Vector(Protocol):
    values: Sequence[float]
    space: str


def _execute(driver: Driver, query: str, params: dict | None = None):
    return driver.execute_query(query, parameters_=params or {}, routing_='w', database_='neo4j')


def apply_migrations(driver: Driver, path: Path = MIGRATION) -> int:
    """Apply each checked-in, idempotent DDL statement in source order."""
    raw = path.read_text(encoding='utf-8')
    statements = [part.strip() for part in re.sub(r'(?m)^\s*//.*$', '', raw).split(';') if part.strip()]
    for number, statement in enumerate(statements, 1):
        if not statement.startswith(('CREATE CONSTRAINT ', 'CREATE INDEX ')) or ' IF NOT EXISTS ' not in statement:
            raise GraphMigrationError(f'invalid migration statement {number}')
        try:
            _execute(driver, statement)
        except Exception:
            raise GraphMigrationError(f'Neo4j migration statement {number} failed; repair and rerun') from None
    return len(statements)


def run_from_settings(settings: Any, *, driver_factory: Callable | None = None) -> int:
    """Connect, migrate, and close; credentials and driver exceptions stay redacted."""
    if driver_factory is None:
        from neo4j import GraphDatabase
        driver_factory = GraphDatabase.driver
    try:
        driver = driver_factory(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value()),
        )
    except Exception:
        raise GraphMigrationError('Neo4j migration connection failed') from None
    try:
        driver.verify_connectivity()
        return apply_migrations(driver)
    except GraphMigrationError:
        raise
    except Exception:
        raise GraphMigrationError('Neo4j migration connection failed') from None
    finally:
        try:
            driver.close()
        except Exception:
            raise GraphMigrationError('Neo4j migration connection close failed') from None


def _dimensions(space: str) -> int:
    match = SPACE_RE.fullmatch(space) if isinstance(space, str) else None
    if match is None:
        raise VectorSpaceError('invalid embedding space')
    return int(match.group(1))


def vector_property(space: str) -> str:
    """Stable Cypher identifier, partitioned by full space rather than dimension."""
    _dimensions(space)
    return 'embedding_' + hashlib.sha256(space.encode('utf-8')).hexdigest()[:16]


def sqlite_current_space(sqlite_url: str) -> Callable[[], str]:
    """Return a fresh-reader for the persisted current space (not the config)."""
    if not sqlite_url.startswith('sqlite:///') or not sqlite_url[10:]:
        raise ValueError('a file SQLite URL is required')
    path = sqlite_url.removeprefix('sqlite:///')

    def read() -> str:
        try:
            with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro',
                                 timeout=5, uri=True) as database:
                row = database.execute(
                    'SELECT model, dimensions, is_fake FROM embedding_space_state WHERE singleton = 1'
                ).fetchone()
        except sqlite3.DatabaseError:
            raise VectorSpaceError('current embedding space is unavailable') from None
        if row is None:
            raise VectorSpaceError('current embedding space is not initialized')
        model, dimensions, is_fake = row
        space = f'fake/{dimensions}' if is_fake else f'real/{model}/{dimensions}'
        _dimensions(space)
        return space

    return read


def _validate_vector(vector: Vector, expected_space: str) -> list[float]:
    if vector.space != expected_space:
        raise VectorSpaceError('vector space differs from write context')
    values = vector.values
    if isinstance(values, (str, bytes)) or len(values) != _dimensions(expected_space):
        raise VectorSpaceError('vector dimensions differ from write context')
    if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in values):
        raise VectorSpaceError('vector values must be finite numbers')
    return [float(x) for x in values]


class GraphVectorWriter:
    """F03 write gate; current_space must freshly read SQLite for every operation."""

    def __init__(self, driver: Driver, current_space: Callable[[], str]) -> None:
        self._driver = driver
        self._current_space = current_space

    def ensure_vector_indexes(self, space: str) -> None:
        """Build independent indexes for a space; never alter another space."""
        prop = vector_property(space)
        dimensions = _dimensions(space)
        suffix = prop.removeprefix('embedding_')
        for name, label in ((f'chunk_embedding_{suffix}', 'Chunk'),
                            (f'kp_embedding_{suffix}', 'KnowledgePoint')):
            statement = (f'CREATE VECTOR INDEX {name} IF NOT EXISTS '
                         f'FOR (n:{label}) ON (n.{prop}) '
                         "OPTIONS {indexConfig: {`vector.dimensions`: "
                         f"{dimensions}, `vector.similarity_function`: 'cosine'}}}}")
            try:
                _execute(self._driver, statement)
            except Exception:
                raise GraphMigrationError('vector index creation failed; repair and rerun') from None

    def write_runtime(self, kind: str, course_id: str, version_id: str | None,
                      entity_id: str, vector: Vector) -> None:
        current = self._current_space()
        self._write(kind, course_id, version_id, entity_id, vector, current)

    @contextmanager
    def migration(self, target_space: str, *, prerequisite_check: Callable[[], None]) -> Iterator['_MigrationContext']:
        """F14-only process-local context, after its external stop/lease/backup checks."""
        _dimensions(target_space)
        prerequisite_check()
        source_space = self._current_space()
        if source_space == target_space:
            raise VectorSpaceError('migration target is already current')
        context = _MigrationContext(self, source_space, target_space)
        try:
            yield context
        finally:
            context.close()

    def _write(self, kind: str, course_id: str, version_id: str | None,
               entity_id: str, vector: Vector, space: str) -> None:
        values = _validate_vector(vector, space)
        if not isinstance(course_id, str) or not course_id.strip() or not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError('course_id and entity_id are required')
        if kind == 'KnowledgePoint':
            if not isinstance(version_id, str) or not version_id.strip():
                raise ValueError('version_id is required for KnowledgePoint')
            selector = 'n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: $entity_id}'
        elif kind == 'Chunk':
            if version_id is not None:
                raise ValueError('Chunk is shared across versions')
            selector = 'n:Chunk {course_id: $course_id, chunk_id: $entity_id}'
        else:
            raise ValueError('unsupported vector entity kind')
        prop = vector_property(space)
        query = f'MATCH ({selector}) SET n.{prop} = $values RETURN count(n) AS matched'
        try:
            result = _execute(self._driver, query, {'course_id': course_id, 'version_id': version_id,
                                                   'entity_id': entity_id, 'values': values})
        except Exception:
            raise GraphMigrationError('vector write failed') from None
        if not result.records or result.records[0]['matched'] != 1:
            raise GraphMigrationError('vector target not found or ambiguous')


class _MigrationContext:
    def __init__(self, writer: GraphVectorWriter, source_space: str, target_space: str) -> None:
        self._writer = writer
        self.source_space = source_space
        self.target_space = target_space
        self._active = True

    def write(self, kind: str, course_id: str, version_id: str | None,
              entity_id: str, vector: Vector) -> None:
        if not self._active or self._writer._current_space() != self.source_space:
            raise VectorSpaceError('migration context expired')
        self._writer._write(kind, course_id, version_id, entity_id, vector, self.target_space)

    def close(self) -> None:
        self._active = False


def main() -> None:
    from app.config import load_settings

    count = run_from_settings(load_settings())
    print(f'Applied {count} repeatable Neo4j schema statements')


if __name__ == '__main__':
    main()
