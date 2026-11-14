"""Local mapping invalidation, persistence and undo against an isolated real Neo4j."""
from dataclasses import replace

import pytest

from app.repositories import fusion
from app.repositories.graph_projection import read_snapshot
from app.repositories.sqlite import connect
from app.workers import persist_graph
from app.workers.fusion_task import prepare_fusion
from tests.backend.helpers.accounts import make_account
from tests.backend.test_relation_reextract_worker import pinned_task
from tests.integration.test_f13 import db_url,storage,graph,live,_persist


def setup(url,storage,graph,**kw):
    user=make_account(url,'teacher','teacher')
    with connect(url) as db:
        db.execute("INSERT INTO courses(id,name,teacher_id) VALUES(?,'fixture',?)",(graph.course,user.id))
        db.execute("INSERT INTO course_members(course_id,user_id,role) VALUES(?,?,'teacher')",(graph.course,user.id))
    return pinned_task(url,storage,course=graph.course,**kw)


def prepare(url,lease,kit,graph,**kw):
    return prepare_fusion(url,lease,repo=graph.repo,toolkit=kit,max_pairs=32,top_k=8,
                          lock_seconds=30,lock_wait_seconds=0,**kw)


def snapshot(url,graph):
    with connect(url) as db:
        return read_snapshot(graph.repo,fusion.read_draft_scope(db,graph.course))


@live
def test_internal_counteredge_splits_local_group_reextracts_and_persists_raw_endpoints(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph)
    before=len(client.calls)
    plan=prepare(db_url,lease,kit,graph)
    assert not plan.payload['groups']
    assert plan.payload['relation_selection'][section.unit_id]['kind']=='revision'
    assert plan.payload['relation_coverage']['reextracted_sections']==1
    after=len(client.calls)
    assert after>before and prepare(db_url,lease,kit,graph).plan_id==plan.plan_id and len(client.calls)==after
    persist_graph.run_merge_stage(db_url,lease)
    assert _persist(db_url,lease,graph.repo).status=='advanced'
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==2 and len(data['edges'])==1
    assert data['edges'][0]['from_id']!=data['edges'][0]['to_id']


@live
def test_global_disagreement_reextracts_without_resurrecting_empty_initial_relation(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph,initial_edge=False)
    state['verdict']='DIFFERENT';state['edge']=True
    plan=prepare(db_url,lease,kit,graph)
    assert not plan.payload['groups'] and len(plan.payload['before']['edges'])==1
    assert plan.payload['relation_coverage']['reextracted_sections']==1


@live
def test_failed_reextract_omits_old_edge_and_reports_technical_gap(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph)
    state['failure']='bad JSON'
    plan=prepare(db_url,lease,kit,graph)
    assert not plan.payload['groups'] and not plan.payload['before']['edges']
    assert plan.payload['reason']=='relation_reextraction_incomplete'
    assert plan.payload['relation_coverage']['status']=='partial'
    assert all(d['verdict']!='UNCERTAIN' for d in plan.payload['decisions'])
    persist_graph.run_merge_stage(db_url,lease)
    assert _persist(db_url,lease,graph.repo).status=='advanced'
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==2 and not data['edges']
    from app.services.fusion.review import build_review_view
    with connect(db_url) as db:
        head=fusion.read_draft_head(db,graph.course)
        saved=fusion.task_plan(db,graph.course,lease.task_id)
    view=build_review_view(head,saved,data['nodes'])
    assert view.summary['status']=='partial'
    assert 'relation_reextraction_failed' in view.summary['reasons']
    assert not view.proposals  # technical inability to merge is not a teacher semantic decision


@live
def test_disabled_auto_merge_still_finalizes_pinned_relations_without_semantic_calls(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph,initial_edge=False)
    state['edge']=True
    kit=replace(kit,resolver=None,local_normalization=False,preserve_mentions=False)
    before=len(client.calls)
    plan=prepare(db_url,lease,kit,graph,allow_auto_merge=False)
    assert plan is not None and not plan.payload['groups']
    assert len(client.calls)==before+1
    assert plan.payload['relation_selection'][section.unit_id]['kind']=='revision'


@live
def test_accepted_local_group_keeps_one_version_but_stale_head_drops_dependent_edge(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph,external_edge=True)
    plan=prepare(db_url,lease,kit,graph)
    assert len(plan.payload['groups'])==1 and len(plan.payload['after']['edges'])==1
    assert plan.payload['relation_coverage']['reextracted_sections']==0
    with connect(db_url) as db:
        db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?',(graph.course,))
    persist_graph.run_merge_stage(db_url,lease)
    assert _persist(db_url,lease,graph.repo).status=='advanced'
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==3 and not data['edges']
    from app.services.fusion.review import build_review_view
    with connect(db_url) as db:
        head=fusion.read_draft_head(db,graph.course)
        saved=fusion.task_plan(db,graph.course,lease.task_id)
    assert 'relation_dependency_stale' in build_review_view(head,saved,data['nodes']).summary['reasons']


@live
def test_missing_plan_never_persists_unconfirmed_local_relations(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph,external_edge=True)
    persist_graph.run_merge_stage(db_url,lease)
    assert _persist(db_url,lease,graph.repo).status=='advanced'
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==3 and not data['edges']


@live
def test_undo_restores_the_original_member_endpoint_of_an_accepted_local_group(db_url,storage,graph):
    from app.services.fusion.undo import undo_merge
    lease,kit,client,state,section=setup(db_url,storage,graph,external_edge=True)
    plan=prepare(db_url,lease,kit,graph)
    original={(e['from_id'],e['to_id'],e['type']) for e in plan.payload['before']['edges']}
    persist_graph.run_merge_stage(db_url,lease)
    assert _persist(db_url,lease,graph.repo).status=='advanced'
    with connect(db_url) as db:
        head=fusion.read_draft_head(db,graph.course)
        actor=db.execute('SELECT teacher_id FROM courses WHERE id=?',(graph.course,)).fetchone()[0]
    out=undo_merge(sqlite_url=db_url,repo=graph.repo,course_id=graph.course,plan_id=plan.plan_id,
        group_id=plan.payload['groups'][0]['group_id'],actor_id=actor,expected_revision=head.draft_revision,
        lock_seconds=30,wait_seconds=0)
    assert out.status=='undone'
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==3
    assert {(e['from_id'],e['to_id'],e['type']) for e in data['edges']}==original


@live
def test_pipeline_takeover_with_flags_off_clears_dependencies_and_keeps_new_relation(db_url,storage,graph):
    from app.config import Settings
    from app.repositories.task_leases import release_on_shutdown
    lease,kit,client,state,section=setup(db_url,storage,graph,initial_edge=False)
    state['edge']=True
    kit=replace(kit,resolver=None,local_normalization=False,preserve_mentions=False)
    assert release_on_shutdown(db_url,lease.task_id,lease.token)
    settings=Settings(SQLITE_URL=db_url,LLM_MODE='fake',DISAMBIGUATION_AUTO_MERGE_ENABLED=False,
                      DISAMBIGUATION_ANALYSIS_ENABLED=False)
    before=len(client.calls)
    result=persist_graph.run_pipeline_once(settings,toolkit=kit,repo=graph.repo,storage=storage,owner='takeover')
    assert result.stages==( ('merging','advanced'),('persisting','advanced') )
    assert len(client.calls)==before+1
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==2 and len(data['edges'])==1


@live
def test_stale_plan_preserves_independent_reextracted_relation(db_url,storage,graph):
    lease,kit,client,state,section=setup(db_url,storage,graph)
    plan=prepare(db_url,lease,kit,graph)
    assert plan.payload['relation_selection'][section.unit_id]['kind']=='revision'
    with connect(db_url) as db:
        db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?',(graph.course,))
    persist_graph.run_merge_stage(db_url,lease)
    assert _persist(db_url,lease,graph.repo).status=='advanced'
    data=snapshot(db_url,graph)
    assert len(data['nodes'])==2 and len(data['edges'])==1
