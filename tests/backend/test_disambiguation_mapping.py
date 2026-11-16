"""Only complete compatible groups with a valid resulting graph may collapse."""
from copy import deepcopy
from dataclasses import replace
import pytest
from app.services.fusion.resolution import SemanticDecision


def snapshot():
    return dict(course_id="c", nodes=[dict(kp_id=k, course_id="c", name=k, definition="定义"+k,
        type="concept", aliases=[], contrib_tasks=["t"+k], contrib_manual=False,
        locked=False, revision=1, status="draft", source="ai", merged_from=[]) for k in "abc"],
        edges=[], chapters=[], evidence=[dict(kp_id=k, chunk_id="ch"+k, document_id="d",
        props=dict(chunk_id="ch"+k, task_id="t"+k, evidence_start=0, evidence_end=2)) for k in "abc"])


def same(a, b):
    return SemanticDecision(a, b, "complete", "SAME", "mixed", "同义",
                            (a+":s",), (b+":s",), model_calls=2, prompt_sha256="h")


def edge(a, b, kind="PREREQUISITE"):
    return dict(type=kind, from_id=a, to_id=b,
                p=dict(rel_id=a+b, course_id="c", status="draft", contrib_tasks=["t"], source="ai"))


def test_missing_pair_cannot_turn_transitive_similarity_into_equivalence():
    from app.services.fusion.mapping import plan_mapping
    result = plan_mapping(snapshot(), [same("a", "b"), same("b", "c")], existing_ids={"b"})
    assert result.mapping["a"] == result.mapping["b"] == "b"
    assert result.mapping["c"] == "c"
    assert any(x["reason"] == "unverified_group" for x in result.blocked)


def test_complete_group_preserves_names_definitions_sources_and_contributions():
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); original = deepcopy(raw)
    result = plan_mapping(raw, [same("a", "b"), same("a", "c"), same("b", "c")], existing_ids={"b"})
    assert raw == original and len(result.snapshot["nodes"]) == 1
    node = result.snapshot["nodes"][0]
    assert node["kp_id"] == "b" and node["definition"].splitlines() == ["定义b", "定义a", "定义c"]
    assert set(node["aliases"]) == {"a", "c"} and set(node["contrib_tasks"]) == {"ta", "tb", "tc"}
    assert set(node["merged_from"]) == {"a", "c"} and not node["locked"]
    assert len(result.snapshot["evidence"]) == 3


@pytest.mark.parametrize("condition", ["locked", "manual", "different", "unverified", "cross_course"])
def test_protected_or_unverified_group_cannot_merge(condition):
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); decisions = [same("a", "b")]
    if condition == "locked": raw["nodes"][0]["locked"] = True
    if condition == "manual": raw["nodes"][0]["contrib_manual"] = True
    if condition == "different": decisions = [replace(decisions[0], verdict="DIFFERENT")]
    if condition == "unverified": decisions = [replace(decisions[0], model_calls=1)]
    if condition == "cross_course":
        raw["nodes"][0]["course_id"] = "other"
        with pytest.raises(ValueError): plan_mapping(raw, decisions, existing_ids=())
        return
    result = plan_mapping(raw, decisions, existing_ids=())
    assert result.mapping["a"] != result.mapping["b"]


@pytest.mark.parametrize("edges", [[edge("a", "b", "CONTAINS")],
                                   [edge("a", "c"), edge("c", "b")]])
def test_merge_cannot_remove_relationships_or_create_an_indirect_cycle(edges):
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); raw["edges"] = edges
    result = plan_mapping(raw, [same("a", "b")], existing_ids=())
    assert not result.groups and result.snapshot["edges"] == edges
    assert result.blocked


def test_approved_teacher_node_is_not_silently_extended_by_auto_mapping():
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); raw['nodes'][0]['status'] = 'approved'
    result = plan_mapping(raw, [same('a','b')], existing_ids={'a'})
    assert not result.groups and result.blocked[0]['reason'] == 'protected_node'


def test_unrelated_directed_related_to_edges_keep_both_identities():
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); raw['nodes'].append({**deepcopy(raw['nodes'][1]), 'kp_id':'d'})
    raw['edges'] = [edge('c','a','RELATED_TO'), edge('a','c','RELATED_TO')]
    result = plan_mapping(raw, [same('b','d')], existing_ids=set())
    assert result.groups
    assert sorted(result.snapshot['edges'], key=lambda e:e['p']['rel_id']) == sorted(raw['edges'], key=lambda e:e['p']['rel_id'])


@pytest.mark.parametrize('protection', ['source', 'contrib_manual', 'status'])
def test_teacher_relation_cannot_be_redirected_by_auto_merge(protection):
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); raw['edges'] = [edge('b','c')]
    raw['edges'][0]['p'][protection] = {'source':'manual','contrib_manual':True,'status':'approved'}[protection]
    result = plan_mapping(raw, [same('a','b')], existing_ids={'a'})
    assert not result.groups and result.blocked[0]['reason'] == 'protected_relation'
    assert result.snapshot == raw


def test_existing_merged_group_cannot_expand_without_original_member_proofs():
    from app.services.fusion.mapping import plan_mapping
    raw = snapshot(); raw['nodes'] = [n for n in raw['nodes'] if n['kp_id']!='b']
    raw['evidence'] = [e for e in raw['evidence'] if e['kp_id']!='b']
    raw['nodes'][0]['merged_from'] = ['b']
    assert not plan_mapping(raw, [same('a','c')], existing_ids={'a'}).groups


def test_merge_keeps_substantive_definition_with_stable_canonical_id():
    from app.services.fusion.mapping import plan_mapping
    raw=snapshot()
    raw['nodes'][0].update(name='链栈', definition='链栈属于本章的数据结构。')
    raw['nodes'][1].update(name='链栈', definition='链栈用单链表存储栈元素，在表头执行入栈和出栈。')
    result=plan_mapping(raw,[same('a','b')],existing_ids={'a'})
    merged=next(n for n in result.snapshot['nodes'] if n['kp_id']=='a')
    assert merged['definition']=='链栈用单链表存储栈元素，在表头执行入栈和出栈。'
    assert merged['kp_id']=='a' and raw['nodes'][0]['definition']=='链栈属于本章的数据结构。'


def test_merge_preserves_complementary_conditions_without_slicing_formula():
    from app.services.fusion.mapping import plan_mapping
    raw=snapshot()
    raw['nodes'][0]['definition']='长度为(rear-front+C)%C。'
    raw['nodes'][1]['definition']='保留一个空槽时，最多存储C-1个元素。'
    merged=plan_mapping(raw,[same('a','b')],existing_ids={'a'}).snapshot['nodes'][0]
    assert '长度为(rear-front+C)%C。' in merged['definition']
    assert '保留一个空槽时，最多存储C-1个元素。' in merged['definition']


def test_definition_overflow_keeps_whole_definition_and_original_provenance():
    from app.services.fusion.mapping import plan_mapping
    raw=snapshot()
    first='甲'*260+'。仅当n>0。'; second='乙'*300+'。仅当n<0。'
    raw['nodes'][0]['definition']=first;raw['nodes'][1]['definition']=second
    merged=plan_mapping(raw,[same('a','b')],existing_ids={'a'}).snapshot['nodes'][0]
    assert merged['definition'] in (first,second)
    assert len(merged['definition'])<=500


def test_structural_definition_with_qualifier_is_not_generic_membership():
    from app.services.fusion.mapping import plan_mapping
    raw=snapshot()
    raw['nodes'][0].update(name='栈',definition='栈是遵循后进先出原则的数据结构。')
    raw['nodes'][1].update(name='栈',definition='栈的插入和删除操作限制在栈顶。')
    merged=plan_mapping(raw,[same('a','b')],existing_ids={'a'}).snapshot['nodes'][0]
    assert '遵循后进先出' in merged['definition'] and '限制在栈顶' in merged['definition']
