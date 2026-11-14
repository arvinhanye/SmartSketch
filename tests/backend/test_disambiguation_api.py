"""Teacher-only review coverage/history/undo protocol; live writes tested separately."""
import json
import time
from types import SimpleNamespace

import pytest

from tests.backend.test_disambiguation_review import queue_env
from tests.backend.test_f11 import assert_schema

SECRET='disambiguation-api-test-signing-secret-only'


@pytest.fixture
def api(queue_env,monkeypatch):
    from fastapi.testclient import TestClient
    from app.services.auth import issue_access_token
    from app.repositories.courses import add_member
    from tests.backend.helpers.accounts import make_account
    ctx,cid,actor,plan,nodes=queue_env
    student=make_account(ctx.sqlite_url,'api-student','student')
    outsider=make_account(ctx.sqlite_url,'api-outsider','teacher')
    add_member(ctx.sqlite_url,course_id=cid,user_id=student.id,role='student',added_by=actor)
    monkeypatch.setenv('SQLITE_URL',ctx.sqlite_url)
    monkeypatch.setenv('AUTH_JWT_SECRET',SECRET)
    monkeypatch.setenv('COURSE_LOCK_WAIT_SECONDS','0')
    from app.main import create_app
    app=create_app()
    app.state.graph_reader=ctx.reader
    app.state.graph_node_store=SimpleNamespace()
    app.state.fusion_repository=object()
    def headers(who=actor,role='teacher'):
        token=issue_access_token(user_id=who,role=role,secret=SECRET.encode(),issued_at=int(time.time()),ttl_seconds=3600)
        return {'Authorization':f'Bearer {token}'}
    with TestClient(app) as client:
        yield SimpleNamespace(client=client,app=app,url=ctx.sqlite_url,cid=cid,actor=actor,plan=plan,
            headers=headers,student=student,outsider=outsider,base=f'/api/v1/courses/{cid}/review')


def test_coverage_route_matches_queue_and_contract(api):
    q=api.client.get(api.base,headers=api.headers())
    result=api.client.get(api.base+'/disambiguation',headers=api.headers())
    assert result.status_code==200,result.text
    assert result.json()==q.json()['disambiguation']
    assert_schema('DisambiguationCoverage',result.json())
    assert_schema('ReviewQueue',q.json())


@pytest.mark.parametrize('suffix,method', [('/disambiguation','get'),('/merges','get'),
    ('/merges/p/g/undo-preview','post'),('/merges/p/g/undo','post')])
def test_all_new_routes_require_current_course_teacher(api,suffix,method):
    call=getattr(api.client,method)
    kw={} if method=='get' else {'json':{'expected_revision':1}}
    assert call(api.base+suffix,**kw).status_code==401
    response=call(api.base+suffix,headers=api.headers(api.student.id,'student'),**kw)
    assert response.status_code==403
    assert response.json()['code']=='ROLE_FORBIDDEN'
    response=call(api.base+suffix,headers=api.headers(api.outsider.id),**kw)
    assert response.status_code==403 and response.json()['code']=='COURSE_FORBIDDEN'


@pytest.mark.parametrize('body', [{}, {'expected_revision':None},{'expected_revision':True},
    {'expected_revision':'1'},{'expected_revision':1.0},{'expected_revision':-1},
    {'expected_revision':1,'force':True}])
@pytest.mark.parametrize('action',['undo-preview','undo'])
def test_undo_input_is_strict(api,body,action):
    response=api.client.post(api.base+'/merges/p/g/'+action,headers=api.headers(),json=body)
    assert response.status_code==422,response.text
    assert response.json()['code']=='VALIDATION_ERROR'


@pytest.mark.parametrize('action,status,http', [('undo-preview','ready',200),('undo-preview','conflict',200),
    ('undo','conflict',409),('undo','undone',200),('undo','already_undone',200)])
def test_undo_wire_result_hides_storage_and_maps_conflicts(api,monkeypatch,action,status,http):
    from app.services.fusion import undo
    calls=[]
    def run(**kwargs):
        calls.append(kwargs)
        return undo.UndoResult(status,7,'g',affected_ids=('a','b'),storage_version_id='draftgen_private',
                               conflicts=({'reason':'stale_revision'},) if status=='conflict' else ())
    monkeypatch.setattr(undo,'preview_undo' if action=='undo-preview' else 'undo_merge',run)
    response=api.client.post(api.base+'/merges/p/g/'+action,headers=api.headers(),json={'expected_revision':6})
    assert response.status_code==http,response.text
    body=response.json()['details'] if http==409 else response.json()
    assert_schema('FusionUndoResult',body)
    assert body['status']==status and body['changed']==(status=='undone')
    assert 'storage_version_id' not in body
    assert calls[0]['actor_id']==api.actor and calls[0]['course_id']==api.cid
    assert calls[0]['expected_revision']==6


@pytest.mark.parametrize('fault,expected', [('lookup',404),('busy',409),('lease',409),('storage',503),('permission',403)])
def test_undo_failures_have_stable_error_codes(api,monkeypatch,fault,expected):
    from app.services.fusion import undo
    from app.repositories.neo4j import RepositoryError
    from app.repositories.task_leases import LeaseLost
    def fail(**kwargs):
        raise {'lookup':LookupError('no plan'),'busy':undo.UndoBusy('COURSE_BUSY'),
               'lease':LeaseLost('lost'),'storage':RepositoryError(),
               'permission':PermissionError('revoked')}[fault]
    monkeypatch.setattr(undo,'undo_merge',fail)
    response=api.client.post(api.base+'/merges/p/g/undo',headers=api.headers(),json={'expected_revision':1})
    assert response.status_code==expected,response.text
    assert response.json()['code'] in ('NOT_FOUND','COURSE_BUSY','REVISION_CONFLICT','STORAGE_UNAVAILABLE','COURSE_FORBIDDEN')
    assert 'private driver detail' not in response.text


def test_history_only_applied_groups_is_paged_and_course_scoped(api):
    from app.repositories import fusion
    from app.repositories.sqlite import connect
    from tests.backend.helpers.tasks import insert_queued_task
    # Original analysis had no applied group: it must not masquerade as an automatic merge.
    response=api.client.get(api.base+'/merges',headers=api.headers())
    assert response.status_code==200,response.text
    assert response.json()['items']==[]
    insert_queued_task(api.url,api.cid,'history')
    with connect(api.url) as db:
        db.execute('BEGIN IMMEDIATE')
        head=fusion.read_draft_head(db,api.cid)
        payload={**api.plan.payload,'groups':[dict(group_id=f'g{i}',members=['a','b'],canonical_id='a') for i in range(3)]}
        p=fusion.put_plan(db,course_id=api.cid,task_id='history',head=head,input_digest='history',payload=payload)
        fusion.activate_plan(db,p,applied=True)
        db.execute('COMMIT')
    seen=[]; cursor=None
    while True:
        params={'limit':1}
        if cursor: params['cursor']=cursor
        response=api.client.get(api.base+'/merges',headers=api.headers(),params=params)
        assert response.status_code==200,response.text
        body=response.json(); assert_schema('FusionMergeHistory',body)
        seen.extend(i['group_id'] for i in body['items'])
        assert 'before' not in response.text and 'draftgen_' not in response.text
        cursor=body['next_cursor']
        if cursor is None: break
    assert seen==['g0','g1','g2']
    assert api.client.get(api.base+'/merges',headers=api.headers(),params={'cursor':'bad'}).status_code==422
