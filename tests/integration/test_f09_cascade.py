"""ADR-097 real Neo4j traversal, identity cleanup, concurrency and rollback.

Uses only the isolated test fixture credentials and per-test synthetic courses.
"""
from __future__ import annotations

import threading

import pytest

from app.repositories import graph_edit
from app.repositories.neo4j import RepositoryConnectionError
from app.services.access import AccessDenied
from app.services.graph.delete_node_cascade import DeletionPreviewStale, delete_node_cascade, preview_deletion
from test_f09 import (  # noqa: F401 - shared isolated graph + SQLite fixture
    FAILED, VERSION_ID, _draft_revision, _publish_v1, _published_state, env, live,
)

pytestmark = live


def seed(env):
    for kid in ('root', 'child', 'shared', 'outside', 'after'):
        env.g.node(kid)
    env.g.edge('CONTAINS', 'root', 'child')
    env.g.edge('CONTAINS', 'child', 'shared')
    env.g.edge('CONTAINS', 'outside', 'shared')
    env.g.edge('PREREQUISITE', 'root', 'after')


def test_cascade_real_cleanup_keeps_published_shared_chunks_and_other_course(env):
    seed(env)
    for kid in ('root', 'child'):
        env.g.node(kid, version=VERSION_ID)
    env.g.edge('CONTAINS', 'root', 'child', version=VERSION_ID)
    env.g.evidence('root', 'shared-chunk')
    env.g.evidence('outside', 'shared-chunk')
    env.og.node('root', tasks=('t-done-o',))
    env.g.node('hidden', tasks=(FAILED,))
    env.g.edge('CONTAINS', 'root', 'hidden', tasks=(FAILED,))
    _publish_v1(env)
    published = env.g.dump(VERSION_ID), _published_state(env)
    other = env.og.dump()
    before_revision = _draft_revision(env)
    plan = preview_deletion(env.ctx, env.course, 'root')
    assert [node.id for node in plan.nodes] == ['root', 'child']
    assert plan.root_revision == env.g.props('root')['revision'] == 1
    assert plan.relation_count == 4
    assert _draft_revision(env) == before_revision
    result = delete_node_cascade(env.ctx, env.course, 'root', plan.preview_token)
    assert result.deleted_count == 2
    assert env.g.props('root') is None and env.g.props('child') is None
    assert env.g.props('hidden') is not None and env.g.props('shared') is not None
    assert env.g.edges() == {('CONTAINS', 'outside', 'shared')}
    assert len(env.g.identities()) == 1
    assert (env.g.dump(VERSION_ID), _published_state(env)) == published
    assert env.og.dump() == other
    assert env.q('MATCH (c:Chunk {course_id:$c, chunk_id:"shared-chunk"}) RETURN count(c) AS n', c=env.course)[0]['n'] == 1
    assert _draft_revision(env) == before_revision + 1


@pytest.mark.parametrize('mutation', ['add', 'remove', 'rewire', 'node'])
def test_real_graph_changes_reject_stale_preview_before_revision_or_deletion(env, mutation):
    seed(env)
    plan = preview_deletion(env.ctx, env.course, 'root')
    if mutation == 'add':
        env.g.edge('CONTAINS', 'root', 'after')
    elif mutation == 'remove':
        env.q('MATCH (:KnowledgePoint {course_id:$c, version_id:"draft", kp_id:"root"})-[r:CONTAINS]->() DELETE r', c=env.course)
    elif mutation == 'rewire':
        env.q('MATCH (:KnowledgePoint {course_id:$c, version_id:"draft", kp_id:"outside"})-[r:CONTAINS]->() DELETE r', c=env.course)
        env.g.edge('CONTAINS', 'root', 'shared')
    else:
        env.q('MATCH (n:KnowledgePoint {course_id:$c, version_id:"draft", kp_id:"child"}) SET n.name="Edited"', c=env.course)
    before, revision = env.g.dump(), _draft_revision(env)
    with pytest.raises(DeletionPreviewStale):
        delete_node_cascade(env.ctx, env.course, 'root', plan.preview_token, expected_revision=1)
    assert env.g.dump() == before
    assert _draft_revision(env) == revision


def test_real_invisible_root_is_404(env):
    env.g.node('root', tasks=(FAILED,))
    before = env.g.dump()
    with pytest.raises(AccessDenied):
        preview_deletion(env.ctx, env.course, 'root')
    with pytest.raises(AccessDenied):
        delete_node_cascade(env.ctx, env.course, 'root', 'a' * 64)
    assert env.g.dump() == before


def test_real_failure_rolls_back_nodes_relations_and_identities(env, monkeypatch):
    seed(env)
    plan = preview_deletion(env.ctx, env.course, 'root')
    before = env.g.dump()
    original = graph_edit.delete_merged_nodes

    def fail_after_delete(tx, ids):
        original(tx, ids)
        raise RepositoryConnectionError()

    monkeypatch.setattr(graph_edit, 'delete_merged_nodes', fail_after_delete)
    with pytest.raises(RepositoryConnectionError):
        delete_node_cascade(env.ctx, env.course, 'root', plan.preview_token)
    assert env.g.dump() == before


def test_two_real_confirmations_have_exactly_one_success(env):
    seed(env)
    plan = preview_deletion(env.ctx, env.course, 'root')
    barrier = threading.Barrier(2)
    outcomes = []

    def confirm():
        barrier.wait(timeout=5)
        try:
            delete_node_cascade(env.make_ctx(wait_seconds=3), env.course, 'root', plan.preview_token)
            outcomes.append('deleted')
        except AccessDenied as exc:
            outcomes.append(exc.status_code)
        except BaseException as exc:
            outcomes.append(type(exc).__name__)

    threads = [threading.Thread(target=confirm) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert outcomes.count('deleted') == 1
    assert outcomes.count(404) == 1
