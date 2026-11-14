"""Only invalidated sections rerun, with monotonic split and bounded safe fallback."""
from types import SimpleNamespace

import pytest


def sections():
    return {s:{'normalization':{'groups':[g]},'relation_input_digest':s+'-old'}
            for s,g in [('one',['a','b']),('two',['c','d']),('unaffected',['e','f'])]}


def mapping(**kw):
    return SimpleNamespace(mapping=dict(a='a',b='a',c='c',d='c',e='e',f='e')|kw)


def test_split_reextracts_only_affected_section_and_keeps_original_version_elsewhere():
    from app.workers.relation_reconciliation import settle_relations
    calls=[]
    def redo(s): calls.append(s); return {'kind':'revision','digest':s+'-new','status':'done'}
    def rebuild(selected,forbidden,disabled):
        assert ('a','b') in forbidden and not disabled
        return mapping(b='b')
    selected,mapped,coverage=settle_relations(sections(),mapping(b='b'),{x:x for x in 'abcdef'},redo,rebuild)
    assert calls==['one'] and coverage['status']=='complete'
    assert selected['one']['digest']=='one-new'
    assert selected['two']=={'kind':'initial','digest':'two-old'}
    assert selected['unaffected']['digest']=='unaffected-old'


def test_new_conflict_propagates_once_and_prior_split_cannot_rejoin():
    from app.workers.relation_reconciliation import settle_relations
    calls=[]
    def redo(s): calls.append(s); return {'kind':'revision','digest':s,'status':'done'}
    def rebuild(selected,forbidden,disabled):
        assert ('a','b') in forbidden
        if len(calls)==2: assert ('c','d') in forbidden
        return mapping(b='b',d='d')
    selected,_,coverage=settle_relations(sections(),mapping(b='b'),{x:x for x in 'abcdef'},redo,rebuild)
    assert calls==['one','two'] and coverage['reextracted_sections']==2
    assert selected['unaffected']['kind']=='initial'


@pytest.mark.parametrize('cap,failed,reason',[(0,False,'relation_reextraction_limit'),(32,True,'relation_reextraction_failed')])
def test_failure_or_limit_discards_all_unconfirmed_edges_and_disables_auto_merge(cap,failed,reason):
    from app.workers.relation_reconciliation import settle_relations
    calls=[]
    def redo(s): calls.append(s); return {'kind':'revision','digest':s,'status':'failed'}
    def rebuild(selected,forbidden,disabled):
        assert disabled and all(v['kind']!='initial' for v in selected.values())
        return mapping(b='b',d='d',f='f')
    selected,_,coverage=settle_relations(sections(),mapping(b='b'),{x:x for x in 'abcdef'},redo,rebuild,max_sections=cap)
    assert coverage['status']=='partial' and reason in coverage['reasons']
    assert len(calls)==int(failed)
    assert selected['two']['kind']=='omitted'


def test_real_graph_cycle_propagates_splits_without_deleting_edges_to_enable_merges():
    from app.services.fusion.mapping import plan_mapping
    from app.workers.relation_reconciliation import settle_relations
    from tests.backend.test_local_normalization import same
    nodes=[dict(kp_id=k,course_id='c',name=k,type='concept') for k in 'abcd']
    decisions=[same('a','b'),same('c','d')]
    def raw(pairs):
        return dict(course_id='c',nodes=nodes,evidence=[],edges=[dict(type='PREREQUISITE',
            from_id=a,to_id=b,p=dict(course_id='c',source='ai',status='candidate',rel_id=a+b)) for a,b in pairs])
    original=raw([('a','c'),('d','b')])
    first=plan_mapping(original,decisions,existing_ids=())
    assert first.mapping['a']==first.mapping['b'] and first.mapping['c']!=first.mapping['d']
    calls=[]
    def redo(s): calls.append(s); return dict(kind='revision',digest=s,status='done')
    def rebuild(selected,forbidden,disabled):
        # New evidence from the second section conflicts with the first local group.
        snapshot=raw([('a','c'),('c','b')])
        result=plan_mapping(snapshot,decisions,existing_ids=(),forbidden_pairs=forbidden)
        assert len(result.snapshot['edges'])==2
        return result
    selected,mapped,coverage=settle_relations({k:v for k,v in sections().items() if k!='unaffected'},
                                             first,{x:x for x in 'abcd'},redo,rebuild)
    assert calls==['two','one'] and not mapped.groups
    assert coverage['status']=='complete' and coverage['reextracted_sections']==2


def test_later_split_in_already_reextracted_section_never_rejoins_after_another_replacement():
    """Final review: S1's later a/b split must survive S2 removing its original counteredge."""
    from itertools import combinations
    from app.services.fusion.mapping import plan_mapping
    from app.workers.relation_reconciliation import settle_relations
    from tests.backend.test_local_normalization import same
    nodes=[dict(kp_id=k,course_id='c',name=k,type='concept') for k in 'abcxy']
    decisions=[same(a,b) for a,b in combinations('abc',2)]+[same('x','y')]
    old={'one':[('c','a')],'two':[('x','y'),('x','b')]}
    replacement={'one':[('c','a'),('a','x')],'two':[]}
    def graph(selected):
        pairs=[p for key in old for p in (replacement[key] if selected.get(key,{}).get('kind')=='revision' else old[key])]
        return dict(course_id='c',nodes=nodes,evidence=[],edges=[dict(type='PREREQUISITE',from_id=a,to_id=b,
            p=dict(course_id='c',source='ai',status='candidate',rel_id=a+b)) for a,b in pairs])
    first=plan_mapping(graph({}),decisions,existing_ids=())
    assert first.groups==( ('a','b'), )
    sections={k:dict(normalization={'groups':[g]},relation_input_digest=k) for k,g in [('one',list('abc')),('two',list('xy'))]}
    calls=[]; states=[]
    def redo(key): calls.append(key); return dict(kind='revision',digest=key,status='done')
    def rebuild(selected,forbidden,disabled):
        mapped=plan_mapping(graph(selected),decisions,existing_ids=(),forbidden_pairs=forbidden)
        states.append(mapped)
        return mapped
    _,mapped,coverage=settle_relations(sections,first,{k:k for k in 'abcxy'},redo,rebuild)
    assert calls==['one','two'] and states[0].mapping['a']!=states[0].mapping['b']
    assert mapped.mapping['a']!=mapped.mapping['b']
    assert not mapped.groups and coverage['status']=='complete'
