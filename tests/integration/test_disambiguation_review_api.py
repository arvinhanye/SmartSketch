"""Real Neo4j + SQLite: generation → review/history → HTTP undo; fake model only."""
from contextlib import contextmanager
import json
import time

import pytest

from app.repositories import fusion
from app.repositories.sqlite import connect
from app.repositories.graph_projection import read_snapshot
from app.workers import persist_graph
from tests.integration.test_fusion_pipeline import setup_task,prepare
from tests.integration.test_f13 import graph,live,db_url,storage
from tests.integration import test_f13 as f13
from tests.backend.test_f11 import assert_schema

SECRET='fusion-live-api-test-key-0123456789abcdefghij'


@contextmanager
def http_client(db_url,graph,actor,monkeypatch):
    from fastapi.testclient import TestClient
    from app.repositories.graph_read import GraphReader
    from app.repositories.graph_edit import DraftNodeStore
    from app.services.auth import issue_access_token
    monkeypatch.setenv('SQLITE_URL',db_url)
    monkeypatch.setenv('AUTH_JWT_SECRET',SECRET)
    monkeypatch.setenv('COURSE_LOCK_WAIT_SECONDS','0')
    from app.main import create_app
    app=create_app()
    app.state.graph_reader=GraphReader(graph.repo)
    app.state.graph_node_store=DraftNodeStore(graph.repo)
    app.state.fusion_repository=graph.repo
    token=issue_access_token(user_id=actor,role='teacher',secret=SECRET.encode(),issued_at=int(time.time()),ttl_seconds=3600)
    with TestClient(app,headers={'Authorization':f'Bearer {token}'}) as client:
        yield client,f'/api/v1/courses/{graph.course}/review'


def persisted(db_url,lease,graph):
    assert persist_graph.run_merge_stage(db_url,lease).status is persist_graph.PersistStatus.ADVANCED
    assert f13._persist(db_url,lease,graph.repo).status is persist_graph.PersistStatus.ADVANCED


@live
def test_generated_merge_history_preview_undo_and_repeat_are_real_and_read_without_models(db_url,storage,graph,monkeypatch):
    lease,toolkit,model,actor=setup_task(db_url,storage,graph,monkeypatch)
    plan=prepare(db_url,lease,graph,toolkit)
    persisted(db_url,lease,graph)
    calls=len(model.calls)
    with http_client(db_url,graph,actor,monkeypatch) as (client,base):
        queue=client.get(base).json()
        assert_schema('ReviewQueue',queue)
        assert queue['disambiguation']['queue_mode']=='semantic'
        assert queue['disambiguation']['auto_merged_groups']==1
        assert queue['suspected_duplicates']==[]
        history=client.get(base+'/merges').json()
        assert_schema('FusionMergeHistory',history)
        assert len(history['items'])==1
        group=history['items'][0]
        assert len(group['members'])==2
        path=f"{base}/merges/{group['plan_id']}/{group['group_id']}"
        body={'expected_revision':history['draft_revision']}
        preview=client.post(path+'/undo-preview',json=body)
        assert preview.status_code==200,preview.text
        assert preview.json()['status']=='ready' and not preview.json()['changed']
        with connect(db_url) as db:
            assert len(read_snapshot(graph.repo,fusion.read_draft_scope(db,graph.course))['nodes'])==1
        undone=client.post(path+'/undo',json=body)
        assert undone.status_code==200,undone.text
        assert_schema('FusionUndoResult',undone.json())
        assert undone.json()['status']=='undone' and undone.json()['changed']
        again=client.post(path+'/undo',json=body)
        assert again.status_code==200 and again.json()['status']=='already_undone'
        assert not again.json()['changed']
        history=client.get(base+'/merges').json()
        assert history['items'][0]['status']=='undone' and history['items'][0]['undone_at']
        assert client.get(base).json()['disambiguation']['status']=='stale'
    with connect(db_url) as db:
        assert len(read_snapshot(graph.repo,fusion.read_draft_scope(db,graph.course))['nodes'])==2
        assert db.execute('SELECT stage FROM processing_tasks WHERE id=?',(lease.task_id,)).fetchone()[0]=='awaiting_review'
        assert db.execute('SELECT count(*) FROM fusion_undos WHERE plan_id=?',(plan.plan_id,)).fetchone()[0]==1
    assert len(model.calls)==calls


@live
@pytest.mark.parametrize('verdict',['DIFFERENT','UNCERTAIN','invalid_output'])
def test_persisted_semantic_results_drive_actual_queue_and_coverage(db_url,storage,graph,monkeypatch,verdict):
    lease,toolkit,model,actor=setup_task(db_url,storage,graph,monkeypatch)
    def respond(request):
        if verdict=='invalid_output': return '{'
        data=json.loads(request.messages[0].content.splitlines()[-1])
        return json.dumps(dict(verdict=verdict,basis='mixed',reason='fixture comparison',
            differences=['different scope'] if verdict=='DIFFERENT' else [],
            left_source_ids=[data['left']['sources'][0]['source_id']],
            right_source_ids=[data['right']['sources'][0]['source_id']]))
    monkeypatch.setattr(model,'_responder',respond)
    plan=prepare(db_url,lease,graph,toolkit)
    assert not plan.payload['groups']
    persisted(db_url,lease,graph)
    with http_client(db_url,graph,actor,monkeypatch) as (client,base):
        response=client.get(base)
        assert response.status_code==200,response.text
        body=response.json(); assert_schema('ReviewQueue',body)
        coverage=body['disambiguation']
        assert coverage['queue_mode']=='semantic'
        assert coverage['technical_unchecked_pairs']==int(verdict=='invalid_output')
        assert body['totals']['suspected_duplicates']==int(verdict=='UNCERTAIN')
        if verdict=='UNCERTAIN':
            pair=body['suspected_duplicates'][0]
            assert pair['reason']=='semantic_uncertain'
            resolved=client.post(base+'/actions',json=dict(item='suspected_duplicate',action='reject',
                kp_ids=[n['id'] for n in pair['candidates']]))
            assert resolved.status_code==200,resolved.text
            assert resolved.json()['totals']['suspected_duplicates']==0
            assert client.get(base).json()['disambiguation']['queue_mode']=='semantic'


@live
def test_http_undo_conflict_preserves_later_teacher_changes_and_cross_course_is_hidden(db_url,storage,graph,monkeypatch):
    from app.repositories.courses import create_course
    lease,toolkit,_,actor=setup_task(db_url,storage,graph,monkeypatch)
    plan=prepare(db_url,lease,graph,toolkit); persisted(db_url,lease,graph)
    group=plan.payload['groups'][0]
    with http_client(db_url,graph,actor,monkeypatch) as (client,base):
        path=f"{base}/merges/{plan.plan_id}/{group['group_id']}"
        rev=client.get(base+'/merges').json()['draft_revision']
        assert client.post(path+'/undo-preview',json={'expected_revision':rev}).json()['status']=='ready'
        revision=next(n['revision'] for n in plan.payload['after']['nodes'] if n['kp_id']==group['canonical_id'])
        edited=client.patch(f"/api/v1/courses/{graph.course}/kp/{group['canonical_id']}",
            json={'expected_revision':revision,'definition':'teacher correction'})
        assert edited.status_code==200,edited.text
        fresh=client.get(base+'/merges').json()['draft_revision']
        response=client.post(path+'/undo',json={'expected_revision':fresh})
        assert response.status_code==409,response.text
        assert response.json()['details']['conflicts'][0]['reason']=='affected_content_changed'
        assert client.get(base).json()['disambiguation']['status']=='stale'
        other=create_course(db_url,name='other',description=None,creator_id=actor)
        response=client.post(f"/api/v1/courses/{other.id}/review/merges/{plan.plan_id}/{group['group_id']}/undo",
            json={'expected_revision':0})
        assert response.status_code==404 and response.json()['code']=='NOT_FOUND'
    with connect(db_url) as db:
        current=read_snapshot(graph.repo,fusion.read_draft_scope(db,graph.course))
        assert len(current['nodes'])==1 and current['nodes'][0]['definition']=='teacher correction'
        assert not fusion.undone_groups(db,graph.course,plan.plan_id)


@live
def test_skipped_stale_plan_is_neither_automatic_history_nor_a_filter(db_url,storage,graph,monkeypatch):
    lease,toolkit,_,actor=setup_task(db_url,storage,graph,monkeypatch)
    prepare(db_url,lease,graph,toolkit)
    with connect(db_url) as db:
        db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?',(graph.course,))
    persisted(db_url,lease,graph)
    with http_client(db_url,graph,actor,monkeypatch) as (client,base):
        assert client.get(base+'/merges').json()['items']==[]
        state=client.get(base+'/disambiguation').json()
        assert state['status']=='stale' and state['queue_mode']=='legacy'
        assert state['completed_pairs'] is None
