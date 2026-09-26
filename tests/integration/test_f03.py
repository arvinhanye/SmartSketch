"""F03 schema and vector-space boundary; fake driver works without Docker."""
from types import SimpleNamespace
import os
import re
import uuid

import pytest

from app.repositories.graph_migrations import (
    GraphMigrationError, GraphVectorWriter, VectorSpaceError,
    apply_migrations, run_from_settings, sqlite_current_space, vector_property,
)
from app.services.ai.embeddings import EmbeddedVector


class Driver:
    def __init__(self, fail_at=None, matched=1, schema_override=None):
        self.calls = []
        self.fail_at = fail_at
        self.matched = matched
        self.schema = {}
        self.schema_override = schema_override or {}

    def verify_connectivity(self):
        pass

    def execute_query(self, query, *, parameters_, routing_, database_):
        self.calls.append((query, parameters_, routing_, database_))
        if len(self.calls) == self.fail_at:
            raise RuntimeError('driver detail must not leak')
        if query.startswith('CREATE CONSTRAINT ') or query.startswith('CREATE INDEX '):
            name = query.split()[2]
            relation = '[r:' in query
            label = re.search(r'\[r:(\w+)\]' if relation else r'\(n:(\w+)\)', query).group(1)
            variable = 'r' if relation else 'n'
            row = {
                'name': name,
                'type': ('RELATIONSHIP_UNIQUENESS' if relation else 'UNIQUENESS')
                        if query.startswith('CREATE CONSTRAINT ') else 'RANGE',
                'entityType': 'RELATIONSHIP' if relation else 'NODE',
                'labelsOrTypes': [label],
                'properties': re.findall(rf'{variable}\.(\w+)', query),
            }
            self.schema.setdefault(name, self.schema_override.get(name, row))
            return SimpleNamespace(records=[])
        if query.startswith('SHOW CONSTRAINTS '):
            return SimpleNamespace(records=[row for row in self.schema.values()
                                            if row['type'] != 'RANGE'])
        if query.startswith('SHOW INDEXES '):
            # Neo4j exposes uniqueness-backed RANGE indexes with the same names
            # as their owning constraints; they must not replace SHOW CONSTRAINTS.
            return SimpleNamespace(records=[
                dict(row, type='RANGE') for row in self.schema.values()
                if row['type'] != 'RANGE'
            ] + [row for row in self.schema.values() if row['type'] == 'RANGE'])
        return SimpleNamespace(records=[{'matched': self.matched}])


def vector(space, values=(0.1, 0.2)):
    return EmbeddedVector(tuple(values), 'model', len(values), space, 'text-hash')


def test_migration_is_repeatable_and_scoped():
    driver = Driver()
    count = apply_migrations(driver)
    assert count >= 8
    queries = [call[0] for call in driver.calls if call[0].startswith('CREATE ')]
    assert all('IF NOT EXISTS' in q for q in queries)
    assert any('KnowledgePoint' in q and 'course_id' in q and 'version_id' in q and 'kp_id' in q for q in queries)
    assert any('Chapter' in q and 'chapter_id' in q for q in queries)
    assert any('Chunk' in q and 'chunk_id' in q and 'version_id' not in q for q in queries)
    assert any('RelationIdentity' in q and 'rel_id' in q for q in queries)
    assert any('contrib_manual' in q for q in queries)
    assert apply_migrations(driver) == count
    assert len([call for call in driver.calls if call[0].startswith('CREATE ')]) == 2 * count


def test_migration_replay_rejects_same_name_with_wrong_schema():
    wrong = {
        'name': 'kp_scope_id', 'type': 'UNIQUENESS', 'entityType': 'NODE',
        'labelsOrTypes': ['KnowledgePoint'], 'properties': ['kp_id'],
    }
    driver = Driver(schema_override={'kp_scope_id': wrong})
    with pytest.raises(GraphMigrationError, match='kp_scope_id'):
        apply_migrations(driver)


def test_migration_failure_identifies_statement_and_is_rerunnable():
    driver = Driver(fail_at=2)
    with pytest.raises(GraphMigrationError, match='statement 2') as error:
        apply_migrations(driver)
    assert 'driver detail' not in str(error.value)
    driver.fail_at = None
    assert apply_migrations(driver) > 0


def test_vector_property_is_stable_and_space_specific():
    old = vector_property('real/model-a/2')
    assert old.startswith('embedding_')
    assert old == vector_property('real/model-a/2')
    assert old != vector_property('real/model-b/2')


def test_runtime_writer_accepts_current_space_only_and_checks_dimension():
    driver = Driver()
    writer = GraphVectorWriter(driver, current_space=lambda: 'real/model-a/2')
    writer.write_runtime('KnowledgePoint', 'c', 'v1', 'kp', vector('real/model-a/2'))
    query, params, routing, _ = driver.calls[-1]
    assert 'course_id: $course_id' in query and 'version_id: $version_id' in query
    assert params['values'] == [0.1, 0.2] and routing == 'w'
    with pytest.raises(VectorSpaceError, match='real/model-b/2.*real/model-a/2'):
        writer.write_runtime('KnowledgePoint', 'c', 'v1', 'kp', vector('real/model-b/2'))
    with pytest.raises(VectorSpaceError):
        writer.write_runtime('KnowledgePoint', 'c', 'v1', 'kp', vector('real/model-a/2', (0.1,)))
    assert len(driver.calls) == 1


def test_chunk_is_course_scoped_and_shared_across_versions():
    driver = Driver()
    GraphVectorWriter(driver, lambda: 'fake/2').write_runtime('Chunk', 'c', None, 'chunk', vector('fake/2'))
    query = driver.calls[0][0]
    assert 'course_id: $course_id' in query and 'chunk_id: $entity_id' in query
    assert 'version_id' not in query


def test_migration_context_only_writes_target_and_expires_after_switch():
    current = ['real/model-a/2']
    driver = Driver()
    writer = GraphVectorWriter(driver, lambda: current[0])
    with writer.migration('real/model-b/2', prerequisite_check=lambda: None) as context:
        context.write('Chunk', 'c', None, 'chunk', vector('real/model-b/2'))
        with pytest.raises(VectorSpaceError):
            context.write('Chunk', 'c', None, 'chunk', vector('real/model-a/2'))
        with pytest.raises(VectorSpaceError):
            writer.write_runtime('Chunk', 'c', None, 'chunk', vector('real/model-b/2'))
        current[0] = 'real/model-b/2'
        with pytest.raises(VectorSpaceError):
            context.write('Chunk', 'c', None, 'chunk', vector('real/model-b/2'))
    with pytest.raises(VectorSpaceError):
        context.write('Chunk', 'c', None, 'chunk', vector('real/model-b/2'))
    assert len(driver.calls) == 1


def test_failed_prerequisite_does_not_open_migration_context():
    writer = GraphVectorWriter(Driver(), lambda: 'fake/2')
    with pytest.raises(RuntimeError, match='lease'):
        with writer.migration('real/model/2', prerequisite_check=lambda: (_ for _ in ()).throw(RuntimeError('lease'))):
            pass


def test_missing_node_and_driver_error_do_not_claim_success():
    missing = GraphVectorWriter(Driver(matched=0), lambda: 'fake/2')
    with pytest.raises(GraphMigrationError, match='target not found'):
        missing.write_runtime('Chunk', 'c', None, 'chunk', vector('fake/2'))
    broken = GraphVectorWriter(Driver(fail_at=1), lambda: 'fake/2')
    with pytest.raises(GraphMigrationError, match='vector write failed') as error:
        broken.write_runtime('Chunk', 'c', None, 'chunk', vector('fake/2'))
    assert 'driver detail' not in str(error.value)


def test_space_indexes_coexist_without_dropping_old():
    driver = Driver()
    writer = GraphVectorWriter(driver, lambda: 'real/old/2')
    writer.ensure_vector_indexes('real/old/2')
    writer.ensure_vector_indexes('real/new/2')
    queries = [call[0] for call in driver.calls]
    assert len(queries) == 4
    assert all('CREATE VECTOR INDEX' in q and 'IF NOT EXISTS' in q for q in queries)
    assert all(q.count('{') == q.count('}') for q in queries)
    assert all('DROP' not in q for q in queries)
    assert queries[0] != queries[2]


def test_sqlite_space_reader_observes_switch_without_cached_state(tmp_path):
    import sqlite3

    path = tmp_path / 'space.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE embedding_space_state (singleton INTEGER PRIMARY KEY, model TEXT, dimensions INTEGER, is_fake INTEGER)')
    db.execute("INSERT INTO embedding_space_state VALUES (1, 'old', 2, 0)")
    db.commit()
    read = sqlite_current_space(f'sqlite:///{path}')
    assert read() == 'real/old/2'
    db.execute("UPDATE embedding_space_state SET model = 'new'")
    db.commit()
    assert read() == 'real/new/2'
    db.close()


def test_sqlite_space_reader_does_not_create_missing_database(tmp_path):
    path = tmp_path / 'missing.sqlite'
    read = sqlite_current_space(f'sqlite:///{path}')
    with pytest.raises(VectorSpaceError, match='current embedding space'):
        read()
    assert not path.exists()


def test_migration_entrypoint_closes_driver_and_never_exposes_password():
    from pydantic import SecretStr

    driver = Driver()
    driver.close = lambda: setattr(driver, 'closed', True)
    settings = SimpleNamespace(NEO4J_URI='bolt://localhost:7687', NEO4J_USER='neo4j',
                               NEO4J_PASSWORD=SecretStr('SECRET-TEST-PASSWORD'))
    def factory(uri, *, auth):
        assert auth == ('neo4j', 'SECRET-TEST-PASSWORD')
        return driver
    assert run_from_settings(settings, driver_factory=factory) > 0
    assert driver.closed
    def failed_factory(uri, *, auth):
        raise RuntimeError('SECRET-TEST-PASSWORD')
    with pytest.raises(GraphMigrationError) as error:
        run_from_settings(settings, driver_factory=failed_factory)
    assert 'SECRET-TEST-PASSWORD' not in str(error.value)


def test_migration_driver_close_failure_is_redacted():
    from pydantic import SecretStr

    driver = Driver()
    def fail_close():
        raise RuntimeError('SECRET-TEST-PASSWORD')
    driver.close = fail_close
    settings = SimpleNamespace(NEO4J_URI='bolt://localhost:7687', NEO4J_USER='neo4j',
                               NEO4J_PASSWORD=SecretStr('SECRET-TEST-PASSWORD'))
    with pytest.raises(GraphMigrationError) as error:
        run_from_settings(settings, driver_factory=lambda uri, *, auth: driver)
    assert 'SECRET-TEST-PASSWORD' not in str(error.value)


@pytest.mark.skipif(
    not all(os.environ.get(name) for name in (
        'SMARTSKETCH_F03_URI', 'SMARTSKETCH_F03_USER', 'SMARTSKETCH_F03_PASSWORD'
    )),
    reason='isolated Neo4j fixture not configured',
)
def test_live_neo4j_constraint_enforces_scope_and_version_coexistence():
    neo4j = pytest.importorskip('neo4j')
    token = uuid.uuid4().hex
    with neo4j.GraphDatabase.driver(
        os.environ['SMARTSKETCH_F03_URI'],
        auth=(os.environ['SMARTSKETCH_F03_USER'], os.environ['SMARTSKETCH_F03_PASSWORD']),
    ) as driver:
        apply_migrations(driver)
        create = ('CREATE (:KnowledgePoint {course_id: $course_id, '
                  'version_id: $version_id, kp_id: $kp_id, f03_test_token: $token})')
        def write(course, version):
            driver.execute_query(create, parameters_={
                'course_id': course, 'version_id': version, 'kp_id': token, 'token': token,
            }, routing_='w', database_='neo4j')
        try:
            write(token, 'v1')
            write(token, 'v2')
            write(token + '-other', 'v1')
            with pytest.raises(neo4j.exceptions.ClientError, match='ConstraintValidationFailed'):
                write(token, 'v1')
            current = ['fake/2']
            writer = GraphVectorWriter(driver, lambda: current[0])
            writer.ensure_vector_indexes('fake/2')
            writer.write_runtime('KnowledgePoint', token, 'v1', token, vector('fake/2'))
            old_property = vector_property('fake/2')
            with writer.migration('real/next/2', prerequisite_check=lambda: None) as context:
                writer.ensure_vector_indexes('real/next/2')
                context.write('KnowledgePoint', token, 'v1', token, vector('real/next/2'))
                properties = driver.execute_query(
                    'MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: $kp_id}) RETURN properties(n) AS properties',
                    parameters_={'course_id': token, 'version_id': 'v1', 'kp_id': token},
                    routing_='r', database_='neo4j',
                ).records[0]['properties']
                assert properties[old_property] == [0.1, 0.2]
                assert properties[vector_property('real/next/2')] == [0.1, 0.2]
                with pytest.raises(VectorSpaceError):
                    writer.write_runtime('KnowledgePoint', token, 'v1', token, vector('real/next/2'))
                current[0] = 'real/next/2'
                with pytest.raises(VectorSpaceError):
                    context.write('KnowledgePoint', token, 'v1', token, vector('real/next/2'))
        finally:
            driver.execute_query(
                'MATCH (n:KnowledgePoint {f03_test_token: $token}) DETACH DELETE n',
                parameters_={'token': token}, routing_='w', database_='neo4j',
            )
