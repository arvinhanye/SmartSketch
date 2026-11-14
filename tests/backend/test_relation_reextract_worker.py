"""Real lease/checkpoint/model audit boundaries, synthetic model only."""
from dataclasses import replace
import json

import pytest

from app.repositories.extraction_checkpoints import list_checkpoints
from app.repositories.sqlite import connect
from app.repositories.task_leases import LeaseLost
from app.services.ai.client import ModelAuthError
from app.services.ai.entities import EntityExtractor
from app.services.ai.extraction_windows import WindowPolicy
from app.services.ai.fake import FakeModelClient
from app.services.ai.relations import RelationExtractor
from app.services.fusion.resolution import SemanticResolver
from app.workers.extract_task import ExtractionToolkit,run_extract_stage,load_candidates
from tests.backend.test_e12 import storage,_extracting,_policy
from tests.backend.test_extraction_window_worker import LIMITS

TEXT='散列表保存映射。哈希表保存映射。二者有区别。'


def pinned_task(url,storage,*,course='c',initial_edge=True,external_edge=False):
    state={'verdict':'SAME','edge':initial_edge,'failure':None,'hook':None}
    def respond(request):
        text=request.messages[0].content
        if state['hook']: state['hook']()
        if '待分析材料数据' in text:
            payload=json.loads(text.splitlines()[-1])
            verdict = state['verdict'] if all(payload[k]['name'] in ('散列表','哈希表') for k in ('left','right')) else 'DIFFERENT'
            return json.dumps(dict(verdict=verdict,basis='mixed',reason='fixture',differences=[],
                left_source_ids=[payload['left']['sources'][0]['source_id']],
                right_source_ids=[payload['right']['sources'][0]['source_id']]))
        if request.purpose=='extract_entities':
            names = [('散列表','保存映射'),('哈希表','保存映射')] + ([('索引','提供定位')] if external_edge else [])
            return json.dumps({'entities':[dict(name=n,type='concept',definition=d,evidence=n+d+'。')
                                          for n,d in names]},ensure_ascii=False)
        if state['failure']:
            if isinstance(state['failure'],Exception): raise state['failure']
            return state['failure']
        table=text.split('实体表（',1)[1].split('：\n',1)[1].split('\n\n来源资料',1)[0]
        cards=json.loads(table); members=[e for card in cards for e in card['members']]
        ids={e['name']:e['id'] for e in members}
        rows=[dict(from_id=ids['哈希表'],to_id=ids['索引'],type='RELATED_TO',evidence='哈希表与索引相关。')] if external_edge else [dict(from_id=members[0]['id'],to_id=members[1]['id'],type='RELATED_TO',evidence='二者有区别。')]
        return json.dumps({'relations':rows if state['edge'] else []},ensure_ascii=False)
    client=FakeModelClient(responder=respond)
    kit=ExtractionToolkit(policy=_policy(url,client),preserve_mentions=True,local_normalization=True,
        entities=lambda c:EntityExtractor(c,model='m',max_output_tokens=4000),
        relations=lambda c:RelationExtractor(c,model='m',max_output_tokens=4000),
        resolver=lambda c:SemanticResolver(c,model='m',max_output_tokens=4000),
        window_policy=WindowPolicy(max_input_bytes=32000))
    text = TEXT + ('索引提供定位。哈希表与索引相关。' if external_edge else '')
    lease,_=_extracting(url,storage,text.encode(),course=course)
    out=run_extract_stage(url,lease,toolkit=kit,limits=LIMITS)
    assert out.status=='advanced'
    checks=list_checkpoints(url,course_id=course,task_id=lease.task_id)
    section=next(c for c in checks if c.unit_kind=='section')
    assert section.result['normalization']['groups']
    return replace(lease,stage='merging'),kit,client,state,section


def reextract(url,lease,kit,section):
    from app.workers.relation_reconciliation import reextract_section
    return reextract_section(url,lease,section,toolkit=kit,limits=LIMITS)


def test_reextract_replaces_not_unions_old_edges_and_caches_identical_input(db_url,storage):
    lease,kit,client,state,section=pinned_task(db_url,storage)
    assert len(load_candidates(db_url,course_id='c',task_id=lease.task_id,provisional=True).relations)==1
    assert not load_candidates(db_url,course_id='c',task_id=lease.task_id).relations
    state['edge']=False; before=len(client.calls)
    choice=reextract(db_url,lease,kit,section)
    assert choice['status']=='done' and len(client.calls)==before+1
    assert reextract(db_url,lease,kit,section)==choice and len(client.calls)==before+1
    loaded=load_candidates(db_url,course_id='c',task_id=lease.task_id,relation_selection={section.unit_id:choice})
    assert len(loaded.entities)==2 and not loaded.relations and not loaded.failed_sections
    raw=list_checkpoints(db_url,course_id='c',task_id=lease.task_id,unit_kind='section')[0]
    assert len(raw.result['relations'])==1  # original immutable, simply no longer selected


def test_failed_revision_is_cached_and_does_not_fall_back_to_initial_relations(db_url,storage):
    lease,kit,client,state,section=pinned_task(db_url,storage)
    state['failure']='bad JSON'; before=len(client.calls)
    choice=reextract(db_url,lease,kit,section)
    assert choice['status']=='failed' and len(client.calls)==before+2
    state['failure']=None
    assert reextract(db_url,lease,kit,section)==choice and len(client.calls)==before+2
    loaded=load_candidates(db_url,course_id='c',task_id=lease.task_id,relation_selection={section.unit_id:choice})
    assert not loaded.relations and len(loaded.failed_sections)==1


@pytest.mark.parametrize('fault',['cancel','lost','auth'])
def test_fault_during_call_never_commits_replacement(db_url,storage,fault):
    from app.workers.fusion_task import FusionCancelled
    lease,kit,client,state,section=pinned_task(db_url,storage)
    def hook():
        state['hook']=None
        with connect(db_url) as db:
            if fault=='cancel': db.execute('UPDATE processing_tasks SET cancel_requested=1 WHERE id=?',(lease.task_id,))
            if fault=='lost': db.execute('UPDATE processing_tasks SET lease_expires_at=unixepoch()-1 WHERE id=?',(lease.task_id,))
    if fault=='auth': state['failure']=ModelAuthError('denied')
    else: state['hook']=hook
    with pytest.raises({'cancel':FusionCancelled,'lost':LeaseLost,'auth':ModelAuthError}[fault]):
        reextract(db_url,lease,kit,section)
    with connect(db_url) as db:
        assert db.execute('SELECT count(*) FROM task_relation_revisions').fetchone()[0]==0


def test_takeover_reuses_finished_revision_but_old_owner_cannot_write(db_url,storage):
    from app.repositories.task_leases import claim_next,reclaim_expired
    lease,kit,client,state,section=pinned_task(db_url,storage)
    choice=reextract(db_url,lease,kit,section); count=len(client.calls)
    with connect(db_url) as db:
        db.execute('UPDATE processing_tasks SET lease_expires_at=unixepoch()-1 WHERE id=?',(lease.task_id,))
    reclaim_expired(db_url,max_attempts=3)
    fresh=claim_next(db_url,owner='new',lease_seconds=60,max_attempts=3)
    assert fresh is not None and fresh.stage=='merging'
    assert reextract(db_url,fresh,kit,section)==choice and len(client.calls)==count
    with pytest.raises(LeaseLost): reextract(db_url,lease,kit,section)


def test_output_budget_change_invalidates_revision_cache(db_url,storage):
    lease,kit,client,state,section=pinned_task(db_url,storage)
    first=reextract(db_url,lease,kit,section); count=len(client.calls)
    kit=replace(kit,relations=lambda c:RelationExtractor(c,model='m',max_output_tokens=4001))
    second=reextract(db_url,lease,kit,section)
    assert second['digest']!=first['digest'] and len(client.calls)==count+1
