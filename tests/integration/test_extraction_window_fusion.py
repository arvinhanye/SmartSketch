"""Incomplete extraction must never masquerade as a complete merge-safe graph."""
import pytest

from app.repositories import fusion
from app.repositories.graph_projection import read_snapshot
from app.repositories.sqlite import connect
from app.repositories.extraction_checkpoints import read_checkpoints, write_checkpoint
from app.repositories.task_leases import leased_transaction
from app.workers import persist_graph
from tests.integration import test_f13 as f13
from tests.integration.test_f13 import graph, live, db_url, storage
from tests.integration.test_fusion_pipeline import setup_task, prepare


@live
@pytest.mark.parametrize('status', ['failed', 'done'])
def test_incomplete_window_invalidates_cached_plan_and_preserves_independent_nodes(
        db_url, storage, graph, monkeypatch, status):
    lease, toolkit, client, _ = setup_task(db_url,storage,graph,monkeypatch)
    healthy=prepare(db_url,lease,graph,toolkit)
    assert len(healthy.payload['groups'])==1
    # Checkpoints are immutable: model a newly recorded incomplete unit, never
    # disable the production trigger to rewrite a previously successful unit.
    with leased_transaction(db_url,lease.task_id,lease.token) as db:
        section=read_checkpoints(db,course_id=graph.course,task_id=lease.task_id,unit_kind='section')[0]
        write_checkpoint(db,task_id=lease.task_id,course_id=graph.course,
            unit_kind='section',unit_id='extra-window-unit',status=status,attempts=1,
            error_code='OUTPUT_INVALID' if status=='failed' else None,
            result=section.result if status=='done' else None,
            metadata={'window_coverage':{'version':1,'status':'partial','reason':'window_limit',
                                      'planned_windows':None,'completed_windows':0}})
    calls=len(client.calls)
    blocked=prepare(db_url,lease,graph,toolkit)
    assert blocked.input_digest!=healthy.input_digest
    assert blocked.payload['groups']==[]
    assert blocked.payload['reason']=='extraction_incomplete'
    assert blocked.payload['completion']=='partial'
    assert blocked.payload['extraction_coverage']['reasons']==['window_limit']
    assert len(client.calls)==calls
    persist_graph.run_merge_stage(db_url,lease)
    assert f13._persist(db_url,lease,graph.repo).status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db:
        head=fusion.read_draft_head(db,graph.course)
        selected=fusion.get_plan(db,graph.course,blocked.plan_id)
        snapshot=read_snapshot(graph.repo,fusion.read_draft_scope(db,graph.course))
    assert len(snapshot['nodes'])==2 and not selected.applied
    from app.services.fusion.review import build_review_view
    view=build_review_view(head,selected,snapshot['nodes'])
    assert view.summary['status']=='partial'
    assert 'extraction_incomplete' in view.summary['reasons']
    assert 'window_limit' in view.summary['reasons']
    assert not view.proposals


@live
def test_complete_windows_reach_merged_graph_and_semantic_review(db_url,storage,graph,monkeypatch):
    from app.services.ai.extraction_windows import WindowPolicy
    from app.services.fusion.review import build_review_view
    lease,toolkit,_,_=setup_task(db_url,storage,graph,monkeypatch,window_policy=WindowPolicy())
    with connect(db_url) as db:
        checks=read_checkpoints(db,course_id=graph.course,task_id=lease.task_id)
    assert checks and all(c.metadata['window_coverage']['status']=='complete' for c in checks)
    plan=prepare(db_url,lease,graph,toolkit)
    assert len(plan.payload['groups'])==1
    persist_graph.run_merge_stage(db_url,lease)
    assert f13._persist(db_url,lease,graph.repo).status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db:
        head=fusion.read_draft_head(db,graph.course)
        selected=fusion.get_plan(db,graph.course,plan.plan_id)
        snapshot=read_snapshot(graph.repo,fusion.read_draft_scope(db,graph.course))
    assert len(snapshot['nodes'])==1 and selected.applied
    assert build_review_view(head,selected,snapshot['nodes']).summary['status']=='complete'
