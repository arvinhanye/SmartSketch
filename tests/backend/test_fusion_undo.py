"""Undo is a guarded inverse patch, preserving unrelated current facts."""
from copy import deepcopy
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
