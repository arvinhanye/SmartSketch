"""Undo is a guarded inverse patch, preserving unrelated current facts."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.services.fusion.mapping import project_snapshot
from tests.backend.test_disambiguation_mapping import snapshot


def fixture():
    raw = snapshot()
    raw['nodes'].append({**deepcopy(raw['nodes'][-1]), 'kp_id': 'd', 'name': 'd'})
    mapping = dict(a='a', b='a', c='c', d='c')
    groups = [dict(group_id='ab', members=['a','b'], canonical_id='a'),
              dict(group_id='cd', members=['c','d'], canonical_id='c')]
    return dict(before=raw, after=project_snapshot(raw, mapping), groups=groups, mapping=mapping)


def test_undo_one_group_preserves_other_group_and_later_unrelated_edit():
    from app.services.fusion.undo import inverse_patch
    p = fixture(); current = deepcopy(p['after'])
    current['nodes'].append(dict(kp_id='later', course_id='c', name='teacher later', definition='new', locked=True))
    result, conflicts = inverse_patch(p, 'ab', current, undone=())
    assert not conflicts
    assert {n['kp_id'] for n in result['nodes']} == {'a','b','c','later'}
    assert next(n for n in result['nodes'] if n['kp_id']=='later') == current['nodes'][-1]
    result2, conflicts = inverse_patch(p, 'cd', result, undone=('ab',))
    assert not conflicts and {n['kp_id'] for n in result2['nodes']} == {'a','b','c','d','later'}


@pytest.mark.parametrize('mutation', ['edit', 'lock', 'delete', 'new_edge'])
def test_later_affected_changes_return_conflict_without_partial_undo(mutation):
    from app.services.fusion.undo import inverse_patch
    p = fixture(); current = deepcopy(p['after'])
    if mutation == 'edit': current['nodes'][0]['name'] = 'teacher edit'
    if mutation == 'lock': current['nodes'][0]['locked'] = True
    if mutation == 'delete': current['nodes'] = current['nodes'][1:]
    if mutation == 'new_edge': current['edges'].append(dict(type='RELATED_TO',from_id='a',to_id='c',
        p=dict(rel_id='new',course_id='c',contrib_manual=True)))
    original = deepcopy(current)
    result, conflicts = inverse_patch(p, 'ab', current, undone=())
    assert result is None and conflicts and current == original


def test_undo_invalidates_stale_revisions_of_canonical_and_restored_nodes():
    from app.services.fusion.undo import inverse_patch
    from app.services.graph.edit_node import _current, RevisionConflict
    p = fixture()
    next(n for n in p['before']['nodes'] if n['kp_id'] == 'b')['revision'] = 7
    current = deepcopy(p['after'])
    result, conflicts = inverse_patch(p, 'ab', current, undone=())
    assert not conflicts
    nodes = {n['kp_id']: n for n in result['nodes']}
    assert nodes['a']['revision'] > 2
    assert nodes['b']['revision'] > 7
    ctx = SimpleNamespace(store=SimpleNamespace(node=lambda _scope, key: nodes[key]))
    for key, stale in [('a', 2), ('b', 7)]:
        with pytest.raises(RevisionConflict):
            _current(ctx, None, key, stale)


def test_merge_undo_and_different_merge_never_reuses_the_original_revision():
    from app.services.fusion.mapping import plan_mapping
    from app.services.fusion.undo import inverse_patch
    from app.services.graph.edit_node import _current, RevisionConflict
    from tests.backend.test_disambiguation_mapping import same
    raw = snapshot()
    first = plan_mapping(raw, [same('a', 'b')], existing_ids={'a'})
    payload = dict(before=raw, groups=[dict(group_id='ab', members=['a', 'b'], canonical_id='a')])
    restored, conflicts = inverse_patch(payload, 'ab', first.snapshot, undone=())
    assert not conflicts
    second = plan_mapping(restored, [same('a', 'c')], existing_ids={'a'})
    node = next(n for n in second.snapshot['nodes'] if n['kp_id'] == 'a')
    assert node['aliases'] == ['c']
    ctx = SimpleNamespace(store=SimpleNamespace(node=lambda *_: node))
    with pytest.raises(RevisionConflict):
        _current(ctx, None, 'a', 2)  # The edit page was opened on the original a+b merge.


@pytest.mark.parametrize('order', [('ab', 'cd'), ('cd', 'ab')])
def test_independent_groups_undo_in_either_order_and_keep_prior_restored_revisions(order):
    from app.services.fusion.undo import inverse_patch
    p = fixture()
    first, conflicts = inverse_patch(p, order[0], p['after'], undone=())
    assert not conflicts
    first_members = next(g['members'] for g in p['groups'] if g['group_id'] == order[0])
    edited = next(n for n in first['nodes'] if n['kp_id'] == first_members[0])
    edited.update(name='later teacher correction', locked=True, revision=edited['revision'] + 1)
    first_nodes = {n['kp_id']: deepcopy(n) for n in first['nodes'] if n['kp_id'] in first_members}
    second, conflicts = inverse_patch(p, order[1], first, undone=(order[0],))
    assert not conflicts
    final = {n['kp_id']: n for n in second['nodes']}
    assert set(final) == {'a', 'b', 'c', 'd'}
    assert all(final[key] == node for key, node in first_nodes.items())
    assert all(final[key]['revision'] > 1 for key in ('b', 'd'))


def test_revision_only_teacher_change_still_blocks_undo():
    from app.services.fusion.undo import inverse_patch
    p = fixture()
    current = deepcopy(p['after'])
    # Content was edited and restored, so its revision is the only evidence of that work.
    current['nodes'][0]['revision'] += 2
    result, conflicts = inverse_patch(p, 'ab', current, undone=())
    assert result is None and conflicts[0]['reason'] == 'affected_content_changed'
