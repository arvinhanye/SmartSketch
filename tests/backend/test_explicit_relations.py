"""Source-grounded gap filling must never connect nodes by name similarity alone."""
import json
import pytest
from app.services.ai.fake import FakeModelClient
from app.services.ai.relations import RelationExtractor, SectionEntity
from tests.backend.test_extraction_windows import source


def extract(text, names, response=(), *, confirm_hints=True):
    entities=tuple(SectionEntity(str(i),'c',name,'concept') for i,name in enumerate(names))
    from app.services.ai.explicit_relations import explicit_relations
    def respond(request):
        items = list(response)
        if confirm_hints and not items:
            items = explicit_relations(entities, (source(text),))
        return json.dumps({'relations':items},ensure_ascii=False)
    client=FakeModelClient(responder=respond)
    outcome=RelationExtractor(client,model='m',max_output_tokens=4000).normalized().extract('c',entities,(source(text),))
    return outcome,client


@pytest.mark.parametrize('text,kind,ends', [
    ('学习课程乙之前需要先掌握课程甲。','PREREQUISITE',('0','1')),
    ('课程甲是课程乙的前置知识。','PREREQUISITE',('0','1')),
    ('课程乙包含课程甲。','CONTAINS',('1','0')),
    ('课程甲是课程乙的一种。','CONTAINS',('1','0')),
    ('课程甲是课程乙的一个例子。','EXAMPLE_OF',('0','1')),
])
def test_confirmed_source_hint_keeps_evidence_without_extra_call(text,kind,ends):
    result,client=extract(text,['课程甲','课程乙'])
    assert result.ok and [(r.from_id,r.to_id,r.type) for r in result.candidates]==[(*ends,kind)]
    r=result.candidates[0]
    assert text[r.source.evidence_start:r.source.evidence_end]==r.evidence==text
    assert len(client.calls)==1


@pytest.mark.parametrize('text',[
    '课程甲不是课程乙的前置知识。', '学习课程乙之前不需要先掌握课程甲。',
    '错误说法：课程甲是课程乙的前置知识。', '“课程甲是课程乙的前置知识”是错误的。',
    '如果课程甲是课程乙的前置知识，就需要调整计划。',
    '课程甲与课程乙同时出现。', '高级课程甲是课程乙的前置知识。',
    '课程甲是课程乙的前置知识，但这一说法并不成立。',
])
def test_negation_hypothetical_substring_and_cooccurrence_never_create_edges(text):
    result,_=extract(text,['课程甲','课程乙'])
    assert result.ok and not result.candidates


def test_ambiguous_or_missing_named_endpoint_does_not_guess():
    for names in (['课程甲','课程甲','课程乙'],['课程甲','别的课程']):
        result,_=extract('课程甲是课程乙的前置知识。',names)
        assert result.ok and not result.candidates


def test_existing_model_edge_is_not_duplicated_and_repeated_quotes_have_exact_offsets():
    sentence='课程甲是课程乙的前置知识。'
    edge=dict(from_id='0',to_id='1',type='PREREQUISITE',evidence=sentence,confidence=.9,
              chunk_id='ch',evidence_start=0)
    # Use the actual test source ID, keeping an explicit occurrence for repeated text.
    edge['chunk_id']=source(sentence).identity.chunk_id
    result,client=extract(sentence+'\n'+sentence,['课程甲','课程乙'],[edge])
    assert result.ok and len(result.candidates)==1 and len(client.calls)==1


@pytest.mark.parametrize('text',[
    '课程甲是课程乙的前置知识？',
    '下列说法不正确：\n课程甲是课程乙的前置知识。',
    '课程甲是课程乙的前置知识。这句话不对。',
    '以下是错误说法。课程甲是课程乙的前置知识。',
    '反例：\n课程甲是课程乙的前置知识。',
    '```\n课程甲是课程乙的前置知识。\n```',
])
def test_questions_and_counterexample_context_never_create_assertions(text):
    result,_=extract(text,['课程甲','课程乙'])
    assert result.ok and not result.candidates


def test_curriculum_prefix_and_explicit_hierarchy_list_preserve_direction_and_offsets():
    text='在本课程的学习顺序中，学习课程乙之前需要先掌握课程甲。\n课程乙的知识体系包含课程甲、课程丙。'
    result,client=extract(text,['课程甲','课程乙','课程丙'])
    assert {(r.from_id,r.to_id,r.type) for r in result.candidates}=={
        ('0','1','PREREQUISITE'),('1','0','CONTAINS'),('1','2','CONTAINS')}
    assert all(text[r.source.evidence_start:r.source.evidence_end]==r.evidence for r in result.candidates)
    assert len(client.calls)==1


def test_conjunction_character_inside_name_is_not_a_list_separator():
    result,_=extract('数值计算的知识体系包含饱和算术、集合论。',['数值计算','饱和算术','集合论'])
    assert result.ok and {(r.from_id,r.to_id) for r in result.candidates}=={('0','1'),('0','2')}


def test_unconfirmed_hints_do_not_create_graph_edges():
    result,client=extract('课程甲是课程乙的前置知识。',['课程甲','课程乙'],confirm_hints=False)
    assert result.ok and not result.candidates and len(client.calls)==1
    assert '"from_id": "0"' in client.calls[0].request.messages[0].content


def test_hint_content_is_included_in_request_size_and_prompt():
    entities=(SectionEntity('0','c','课程甲','concept'),SectionEntity('1','c','课程乙','concept'))
    chunks=(source('课程甲是课程乙的前置知识。'),)
    client=FakeModelClient(responder=lambda _:json.dumps({'relations':[]}))
    extractor=RelationExtractor(client,model='m',max_output_tokens=4000).normalized()
    size=extractor.request_size(entities,chunks)
    extractor.extract('c',entities,chunks)
    from app.services.ai.request_budget import rendered_request_size
    assert size==rendered_request_size(client.calls[0].request.messages[0].content,4000)
