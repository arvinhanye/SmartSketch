"""Local SAME is a reversible semantic card, never destructive mention deduplication."""
from dataclasses import asdict, replace
from itertools import combinations

from app.services.ai.relations import SectionEntity
from app.services.fusion.resolution import SemanticDecision


def nodes():
    return tuple(SectionEntity(k, 'c', n, 'concept', '完整限定'+k, '证据'+k)
                 for k, n in [('a', '散列表'), ('b', '哈希表'), ('c', '映射表')])


def same(a, b):
    return SemanticDecision(a, b, 'complete', 'SAME', left_source_ids=('x',),
                            right_source_ids=('y',), model_calls=2, prompt_sha256='prompt')


def test_complete_link_preserves_all_original_members_and_is_deterministic():
    from app.services.fusion.local import local_normalization
    ns = nodes(); decisions = [asdict(same(a.entity_id,b.entity_id)) for a,b in combinations(ns,2)]
    result = local_normalization(ns, {'decisions':decisions})
    assert result['mapping'] == {'a':'a','b':'a','c':'a'}
    assert result['groups'] == [['a','b','c']]
    assert result == local_normalization(tuple(reversed(ns)), {'decisions':list(reversed(decisions))})
    assert result['version'] == 1 and len(result['digest']) == 64
    assert ns == nodes()


def test_missing_pair_cannot_merge_a_synonym_chain():
    from app.services.fusion.local import local_normalization
    result = local_normalization(nodes(), {'decisions':[asdict(same('a','b')),asdict(same('b','c'))]})
    assert result['groups'] == [['a','b']] and result['mapping']['c'] == 'c'


def test_unverified_or_different_decisions_are_identity_only():
    from app.services.fusion.local import local_normalization
    for bad in [replace(same('a','b'),model_calls=1), replace(same('a','b'),verdict='DIFFERENT'),
                replace(same('a','b'),left_source_ids=()),replace(same('a','b'),code='input_budget')]:
        assert not local_normalization(nodes(), {'decisions':[asdict(bad)]})['groups']
