"""ADR-097: API semantics with real auth/SQLite and isolated graph I/O.

Real Cypher/transaction rollback is covered separately by integration/test_f09_cascade.py.
These regressions catch invisible roots, unbounded closure, changed previews and wrong delete IDs.
"""
from __future__ import annotations

import copy

import pytest

from app.repositories import edit_logs, graph_edit
from app.repositories.sqlite import connect
from tests.backend.test_f08 import kp, s  # noqa: F401 - shared real-app scenario fixture


@pytest.fixture
def graph(s, monkeypatch):
    edges = []
    store = s.store
    store.nodes.update({key: kp(key) for key in ('root', 'child', 'shared', 'other', 'after')})

    def edge(a, b, kind='CONTAINS', *, visible=True):
        edges.append(graph_edit.IncidentRelation(kind, a, b, {'rel_id': f'{kind}:{a}:{b}', 'revision': 1}, visible))

    edge('root', 'child')
    edge('child', 'shared')
    edge('other', 'shared')
    edge('root', 'after', 'PREREQUISITE')

    class Tx:
        def __init__(self, scope):
            self.scope = scope

    def transaction(scope, work):
        before = copy.deepcopy(store.nodes), list(edges)
        try:
            return work(Tx(scope))
        except BaseException:
            store.nodes, edges[:] = before
            raise

    def visible_nodes(tx, ids):
        return {key: dict(store.nodes[key]) for key in ids
                if key in store.nodes and store._visible(tx.scope, store.nodes[key])}

    def delete_nodes(tx, ids, relations):
        store.writes.append(('cascade', tuple(ids)))
        assert set(ids) <= store.nodes.keys()
        removed = {r.rel_id for r in relations}
        for key in ids:
            del store.nodes[key]
        edges[:] = [r for r in edges if r.rel_id not in removed]
        return len(ids)

    monkeypatch.setattr(store, 'transaction', transaction, raising=False)
    monkeypatch.setattr(graph_edit, 'read_cascade_nodes', lambda tx: copy.deepcopy(store.nodes), raising=False)
    monkeypatch.setattr(graph_edit, 'read_nodes', visible_nodes)
    monkeypatch.setattr(graph_edit, 'read_incident_relations', lambda tx, ids: list(edges))
    monkeypatch.setattr(graph_edit, 'delete_cascade_nodes', delete_nodes, raising=False)
    return s, edges, edge


def preview(s, kid='root', user=None):
    return s.call('GET', f'/kp/{kid}/delete-impact', user or s.teacher)


def remove(s, token=None, kid='root', **query):
    pairs = {'cascade': 'true', **query}
    if token is not None:
        pairs['preview_token'] = token
    suffix = '&'.join(f'{key}={value}' for key, value in pairs.items())
    return s.call('DELETE', f'/kp/{kid}?{suffix}', s.teacher)


def audit_rows(s):
    with connect(s.url) as db:
        cursor = db.execute('SELECT * FROM graph_edit_logs')
        keys = [column[0] for column in cursor.description]
        return [dict(zip(keys, row)) for row in cursor]


def pending_edit(s):
    edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id,
                    action='update', kp_id='child', kp_revision_before=1,
                    summary={'changes': {'name': {'before': 'CHILD', 'after': 'New name'}}})


def test_preview_does_not_change_prior_pending_audit(graph):
    s, _, _ = graph
    pending_edit(s)
    before = audit_rows(s), s.draft_revision()
    response = preview(s)
    assert response.status_code == 200, response.text
    assert (audit_rows(s), s.draft_revision()) == before
    assert s.store.writes == []


def test_stale_delete_does_not_change_prior_pending_audit(graph):
    s, _, _ = graph
    token = preview(s).json()['preview_token']
    pending_edit(s)
    before = audit_rows(s), s.draft_revision()
    response = remove(s, token)
    assert response.status_code == 409, response.text
    assert response.json()['details']['reason'] == 'deletion_preview_stale'
    assert (audit_rows(s), s.draft_revision()) == before
    assert s.store.writes == []


def test_root_revision_is_the_previewed_node_version(graph):
    s, _, _ = graph
    s.store.nodes['root']['revision'] = 4
    response = preview(s)
    assert response.status_code == 200, response.text
    assert response.json()['root_revision'] == 4


def test_expected_revision_conflict_does_not_resolve_pending_audit(graph):
    s, _, _ = graph
    pending_edit(s)
    token = preview(s).json()['preview_token']
    before = audit_rows(s), s.draft_revision()
    response = remove(s, token, expected_revision=2)
    assert response.status_code == 409, response.text
    assert response.json()['details']['current_revision'] == 1
    assert (audit_rows(s), s.draft_revision()) == before
    assert s.store.writes == []


def test_preview_is_readonly_and_cascade_keeps_shared_and_prerequisite_nodes(graph):
    s, edges, _ = graph
    before = s.draft_revision()
    response = preview(s)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [n['id'] for n in body['nodes']] == ['root', 'child']
    assert [n['id'] for n in body['retained']] == ['shared']
    assert body['retained'][0]['retained_parents'] == ['OTHER']
    assert body['relation_count'] == 3
    assert len(body['preview_token']) == 64
    assert s.store.writes == [] and audit_rows(s) == [] and s.draft_revision() == before
    assert preview(s).json()['preview_token'] == body['preview_token']
    deleted = remove(s, body['preview_token'])
    assert deleted.status_code == 200, deleted.text
    assert set(s.store.nodes) == {'shared', 'other', 'after'}
    assert [(e.from_id, e.to_id) for e in edges] == [('other', 'shared')]
    assert s.store.writes == [('cascade', ('root', 'child'))]
    assert s.draft_revision() == before + 1
    assert [row['state'] for row in audit_rows(s)] == ['committed']


@pytest.mark.parametrize('change', ['add_edge', 'remove_edge', 'rewire', 'node_revision', 'node_name', 'draft_revision', 'visibility'])
def test_changed_preview_conflicts_before_any_edit_write(graph, change):
    s, edges, edge = graph
    response = preview(s)
    assert response.status_code == 200, response.text
    token = response.json()['preview_token']
    if change == 'add_edge':
        edge('root', 'after')
    elif change == 'remove_edge':
        edges.pop()
    elif change == 'rewire':
        edges.pop(2)
        edge('root', 'shared')
    elif change == 'node_revision':
        s.store.nodes['child']['revision'] += 1
    elif change == 'node_name':
        s.store.nodes['child']['name'] = 'changed without revision'
    elif change == 'draft_revision':
        with connect(s.url) as db:
            db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?', (s.course.id,))
    else:
        s.task('new-effective', 'completed', doc='another-doc')
    before = copy.deepcopy(s.store.nodes), list(edges), s.draft_revision()
    deleted = remove(s, token, expected_revision=1)
    assert deleted.status_code == 409, deleted.text
    assert deleted.json()['code'] == 'REVISION_CONFLICT'
    assert deleted.json()['details']['reason'] == 'deletion_preview_stale'
    assert (s.store.nodes, edges, s.draft_revision()) == before
    assert s.store.writes == [] and audit_rows(s) == []


@pytest.mark.parametrize('token', [None, '', 'bad', 'g' * 64])
def test_cascade_requires_well_formed_preview_token_without_writes(graph, token):
    s, _, _ = graph
    response = remove(s, token)
    assert response.status_code == 422, response.text
    assert s.store.writes == [] and audit_rows(s) == []


@pytest.mark.parametrize('kid', ['absent', 'root'])
def test_invisible_or_missing_root_is_404(graph, kid):
    s, _, _ = graph
    s.store.nodes['root']['contrib_tasks'] = ['t-running']
    assert preview(s, kid).status_code == 404
    assert remove(s, 'a' * 64, kid).status_code == 404
    assert s.store.writes == [] and audit_rows(s) == []


def test_non_teachers_cannot_preview(graph):
    s, _, _ = graph
    assert preview(s, user=s.student).status_code == 403
    assert preview(s, user=s.outsider).status_code == 403


def test_visible_closure_is_complete_beyond_old_depth_limit_and_cycle_safe(graph):
    s, edges, edge = graph
    s.store.nodes = {'root': kp('root')}
    edges.clear()
    parent = 'root'
    for index in range(70):
        child = f'n{index:02}'
        s.store.nodes[child] = kp(child)
        edge(parent, child)
        parent = child
    edge(parent, 'root')
    s.store.nodes['hidden'] = kp('hidden', contrib_tasks=['t-running'])
    edge('root', 'hidden', visible=False)
    response = preview(s)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['deleted_count'] == 71
    assert body['nodes'][-1]['depth'] == 70
    assert 'hidden' not in [n['id'] for n in body['nodes']]
    assert remove(s, body['preview_token']).status_code == 200
    assert set(s.store.nodes) == {'hidden'}


def test_token_is_bound_to_root(graph):
    s, _, _ = graph
    response = preview(s)
    assert response.status_code == 200, response.text
    assert remove(s, response.json()['preview_token'], 'other').status_code == 409
    assert s.store.writes == []


def test_managed_transaction_retry_uses_the_pre_edit_revision_and_one_audit(graph, monkeypatch):
    s, edges, _ = graph
    pending_edit(s)
    before = s.draft_revision()
    response = preview(s)
    assert response.status_code == 200, response.text
    token = response.json()['preview_token']
    original = s.store.transaction
    calls = []

    def retry(scope, work):
        nodes_before, edges_before = copy.deepcopy(s.store.nodes), list(edges)
        original(scope, work)  # transient failure before the first graph commit
        calls.append('rolled back')
        s.store.nodes, edges[:] = nodes_before, edges_before
        s.store.writes.clear()
        return original(scope, work)

    monkeypatch.setattr(s.store, 'transaction', retry)
    response = remove(s, token)
    assert response.status_code == 200, response.text
    assert calls == ['rolled back']
    assert s.store.writes == [('cascade', ('root', 'child'))]
    assert set(s.store.nodes) == {'shared', 'other', 'after'}
    assert s.draft_revision() == before + 1
    rows = audit_rows(s)
    assert [row['state'] for row in rows] == ['aborted', 'committed']
    assert [row['resolved_by'] for row in rows] == ['reconcile', 'writer']


@pytest.mark.parametrize('query', ['', '?cascade=false'])
def test_default_single_delete_retains_neighbors_and_204(graph, monkeypatch, query):
    s, edges, _ = graph
    def single(tx, kid, expected):
        assert s.store.nodes[kid]['revision'] == expected
        del s.store.nodes[kid]
        count = len([r for r in edges if kid in (r.from_id, r.to_id)])
        edges[:] = [r for r in edges if kid not in (r.from_id, r.to_id)]
        return count
    monkeypatch.setattr(graph_edit, 'delete_draft_node', single)
    response = s.call('DELETE', f'/kp/root{query}', s.teacher)
    assert response.status_code == 204 and response.content == b''
    assert set(s.store.nodes) == {'child', 'shared', 'other', 'after'}


def test_single_delete_rejects_a_changed_previewed_root_revision(graph):
    s, _, _ = graph
    response = preview(s)
    assert response.status_code == 200, response.text
    revision = response.json()['root_revision']
    s.store.nodes['root']['revision'] += 1
    response = s.call('DELETE', f'/kp/root?cascade=false&expected_revision={revision}', s.teacher)
    assert response.status_code == 409, response.text
    assert response.json()['details']['current_revision'] == revision + 1
    assert s.store.writes == [] and audit_rows(s) == []


def test_relation_reordering_does_not_invalidate_an_unchanged_preview(graph):
    s, edges, _ = graph
    response = preview(s)
    assert response.status_code == 200, response.text
    edges.reverse()
    assert preview(s).json()['preview_token'] == response.json()['preview_token']
