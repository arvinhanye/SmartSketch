"""Strict normalized relation inputs retain raw endpoints and reject missing counterevidence."""
import json
from dataclasses import replace

import pytest

from app.services.ai.fake import FakeModelClient
from app.services.ai.relations import RelationExtractor, SectionEntity
from tests.backend.test_extraction_windows import source


def entities():
    return (SectionEntity('a','c','散列表','concept','完整限定甲','证据甲',canonical_id='a'),
            SectionEntity('b','c','哈希表','concept','完整限定乙','证据乙',canonical_id='a'))


def edge(**extra):
    return dict(from_id='a',to_id='b',type='RELATED_TO',evidence='二者有区别。',confidence=.9,**extra)


def extract(items, chunk=None):
    client = FakeModelClient(responder=lambda _: json.dumps({'relations':items},ensure_ascii=False))
    r = RelationExtractor(client,model='m',max_output_tokens=4000).normalized()
    return r.extract('c',entities(),(chunk or source('二者有区别。'),)),client


def test_grouped_prompt_keeps_definitions_raw_member_endpoints_and_internal_counteredge():
    outcome,client=extract([edge()])
    assert outcome.ok and [(r.from_id,r.to_id) for r in outcome.candidates] == [('a','b')]
    text=client.calls[0].request.messages[0].content
    assert all(s in text for s in ['canonical_id','members','完整限定甲','完整限定乙','证据甲','证据乙'])
    assert client.calls[0].request.purpose == 'extract_normalized_relations'


@pytest.mark.parametrize('items',[[edge()] , [edge() | {'to_id':'ghost'}], [edge() | {'type':'WRONG'}]])
def test_bad_or_ambiguous_relation_fails_whole_unit_after_one_repair(items):
    outcome,client=extract(items,source('二者有区别。再次：二者有区别。'))
    assert not outcome.ok and outcome.candidates == ()
    assert len(client.calls) == 2 and client.calls[1].request.purpose == 'repair'


def test_explicit_valid_occurrence_and_duplicates_are_accepted():
    chunk=source('二者有区别。再次：二者有区别。'); start=chunk.text.rindex('二者有区别。')
    item=edge(chunk_id=chunk.identity.chunk_id,evidence_start=start)
    outcome,client=extract([item,item],chunk)
    assert outcome.ok and len(outcome.candidates)==1 and len(client.calls)==1
    assert outcome.candidates[0].source.evidence_start == start


def test_wrong_explicit_locator_is_not_repaired_by_searching_elsewhere():
    outcome,client=extract([edge(chunk_id='unknown',evidence_start=0)])
    assert not outcome.ok and len(client.calls)==2


def test_mode_copy_does_not_change_legacy_prompt_or_ignore_budget():
    client=FakeModelClient(); legacy=RelationExtractor(client,model='m',max_output_tokens=4000)
    strict=legacy.normalized()
    assert legacy.prompt().purpose == 'extract_relations'
    assert strict.prompt().purpose == 'extract_normalized_relations'
    assert strict.request_size(entities(),(source('原文'),)) > 4000*4


def test_relation_windows_never_split_members_of_a_semantic_card():
    from app.services.ai.extraction_windows import relation_windows,WindowPolicy
    ns=entities()+tuple(SectionEntity(k,'c',k,'concept','限定'*200,canonical_id=k) for k in 'cde')
    ns=tuple(replace(e,definition='完整限定'*150+e.entity_id) for e in ns)
    r=RelationExtractor(FakeModelClient(),model='m',max_output_tokens=256).normalized()
    chunks=(source('原文'),)
    p=WindowPolicy(max_input_bytes=r.request_size(ns[:3],chunks)+64)
    windows=relation_windows(r,ns,chunks,p)
    assert len(windows)>1
    for w in windows:
        ids={e.entity_id for e in w.entities}
        if ids & {'a','b'}:
            assert {'a','b'}<=ids


def test_oversized_single_card_fails_instead_of_sending_partial_alias_definitions():
    from app.services.ai.extraction_windows import relation_windows,WindowPolicy,WindowBudgetError
    ns=tuple(SectionEntity(k,'c',k,'concept','限定'*300,canonical_id='a') for k in 'abc')
    client=FakeModelClient(); r=RelationExtractor(client,model='m',max_output_tokens=256).normalized()
    chunks=(source('原文'),)
    p=WindowPolicy(max_input_bytes=r.request_size(ns[:2],chunks)+64)
    with pytest.raises(WindowBudgetError,match='input_budget'):
        relation_windows(r,ns,chunks,p)
    assert not client.calls
