"""DISAMBIG-BE-03: saved semantic results, conservative freshness and honest coverage."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.repositories.fusion import DraftHead, FusionPlan
from app.services.fusion.review import build_review_view


def node(key, name='哈希表', **extra):
    return dict(kp_id=key, name=name, type='concept', status='draft', **extra)


def decision(a, b, verdict='DIFFERENT', status='complete'):
    return dict(left_id=a, right_id=b, verdict=verdict if status == 'complete' else None,
                status=status, reason='fixture reason', differences=['different scope'] if verdict=='DIFFERENT' else [],
                basis='mixed', code=None if status=='complete' else 'input_budget')


def fixture(verdict='DIFFERENT', status='complete'):
    nodes = [node('a'), node('b', '散列表')]
    before = dict(nodes=deepcopy(nodes))
    payload = dict(version=2, before=before, after=deepcopy(before), mapping={'a':'a','b':'b'},
        groups=[], blocked=[], deferred_pairs=[], decisions=[decision('a','b',verdict,status)],
        recall=dict(pairs=[dict(left_id='a',right_id='b',channels=['vector'],rank_score=.1)],
                    total_possible_pairs=1,truncated_pairs=0,limited_queries=0,missing_channels=[]),
        total_pairs=1, examined_pairs=1, completed_pairs=int(status=='complete'),
        unprocessed_pairs=int(status!='complete'), completion='complete' if status=='complete' else 'partial',
        reason=None, vector_error=None)
    original = DraftHead('course', 4, 'draft', ('old',))
    plan = FusionPlan('p','course','new',original,'digest','draftgen_p',payload,state='committed')
    head = replace(original, draft_revision=5, effective_task_ids=('new','old'))
    return head, plan, nodes


def test_current_different_is_counted_but_not_a_semantic_review_item():
    head, plan, nodes = fixture()
    view = build_review_view(head, plan, nodes)
    assert view.proposals == ()
    assert view.summary['status'] == 'complete'
    assert view.summary['queue_mode'] == 'semantic'
    assert view.summary['different_pairs'] == 1
    assert view.summary['technical_unchecked_pairs'] == 0
    assert view.summary['pair_unit'] == 'original_member_pairs'
    assert view.summary['recall']['pair_unit'] == 'visible_node_pairs'


@pytest.mark.parametrize('verdict, reason', [('UNCERTAIN','semantic_uncertain'),('SAME','merge_blocked')])
def test_uncertain_and_unmerged_same_are_proposals_without_a_lexical_match(verdict,reason):
    head, plan, nodes = fixture(verdict)
    view = build_review_view(head, plan, nodes)
    assert [(p.left_id,p.right_id,p.reason) for p in view.proposals] == [('a','b',reason)]
    assert view.proposals[0].analysis['verdict'] == verdict
    assert view.proposals[0].analysis['plan_id'] == 'p'


@pytest.mark.parametrize('status', ['failed','deferred'])
def test_technical_noncompletion_is_not_semantic_uncertainty(status):
    head, plan, nodes = fixture(status=status)
    view = build_review_view(head, plan, nodes)
    assert not view.proposals
    assert view.summary['status'] == 'partial'
    assert view.summary['uncertain_pairs'] == 0
    assert view.summary['technical_unchecked_pairs'] == 1


@pytest.mark.parametrize('change', ['revision','tasks','storage','prepared','skipped','undo','course'])
def test_stale_or_uncommitted_results_never_filter_current_queue(change):
    head, plan, nodes = fixture()
    undone = ()
    if change=='revision': head=replace(head,draft_revision=6)
    if change=='tasks': head=replace(head,effective_task_ids=('new','old','later'))
    if change=='storage': head=replace(head,storage_version_id='draftgen_else')
    if change in ('prepared','skipped'): plan=replace(plan,state=change)
    if change=='undo': undone=('g',)
    if change=='course': plan=replace(plan,course_id='another')
    view = build_review_view(head,plan,nodes,undone=undone)
    assert view.summary['queue_mode']=='legacy'
    assert view.summary['status']=='stale'
    assert view.summary['technical_unchecked_pairs'] is None
    assert view.summary['different_pairs'] is None
    assert not view.proposals


def test_absent_analysis_is_not_zero_work_complete():
    head, _, nodes = fixture()
    view = build_review_view(head,None,nodes)
    assert view.summary['status']=='not_analyzed'
    assert view.summary['total_pairs'] is None


def test_applied_group_disappears_and_cross_group_members_require_complete_proof():
    head, plan, nodes = fixture('UNCERTAIN')
    # a already represents original a + x; checking only a/b is insufficient.
    plan.payload['before']['nodes'][0]['merged_from']=['x']
    plan.payload['total_pairs']=2
    plan.payload['unprocessed_pairs']=1
    plan.payload['completion']='partial'
    assert not build_review_view(head,plan,nodes).proposals
    plan.payload['decisions'].append(decision('x','b','DIFFERENT'))
    plan.payload['completed_pairs']=2
    plan.payload['examined_pairs']=2
    plan.payload['unprocessed_pairs']=0
    assert not build_review_view(head,plan,nodes).proposals
    plan.payload['decisions'][-1]=decision('x','b','UNCERTAIN')
    assert len(build_review_view(head,plan,nodes).proposals)==1
    plan.payload['mapping']['b']='a'
    plan.payload['groups']=[dict(group_id='g',members=['a','b'],canonical_id='a')]
    plan=replace(plan,applied=True)
    head=replace(head,storage_version_id=plan.storage_version_id)
    view=build_review_view(head,plan,[nodes[0]])
    assert not view.proposals
    assert view.summary['auto_merged_groups']==1


def test_teacher_dismissal_filters_semantic_pair_without_invalidating_other_analysis():
    head, plan, nodes=fixture('UNCERTAIN')
    head=replace(head,review_decisions=(('suspected_duplicate','["a","b"]'),))
    view=build_review_view(head,plan,nodes)
    assert not view.proposals
    assert view.summary['queue_mode']=='semantic'


def test_recall_limit_and_missing_channels_remain_visible_even_if_queue_empty():
    head,plan,nodes=fixture()
    plan.payload['recall'].update(missing_channels=['vector'],truncated_pairs=7,limited_queries=2)
    plan.payload.update(total_pairs=8,unprocessed_pairs=7,completion='partial')
    view=build_review_view(head,plan,nodes)
    assert view.summary['status']=='partial'
    assert view.summary['recall']['truncated_pairs']==7
    assert view.summary['recall']['missing_channels']==['vector']
    assert view.summary['technical_unchecked_pairs']==7


@pytest.fixture
def queue_env(tmp_path):
    from app.repositories import fusion
    from app.repositories.courses import create_course
    from app.repositories.sqlite import connect
    from tests.backend.helpers.accounts import make_account
    from tests.backend.helpers.sqlite import migrated_database
    from tests.backend.helpers.tasks import insert_queued_task
    url=migrated_database(f'sqlite:///{tmp_path / "review.sqlite3"}')
    user=make_account(url,'review-teacher','teacher')
    course=create_course(url,name='test',description=None,creator_id=user.id)
    insert_queued_task(url,course.id,'new')
    _, sample, nodes=fixture('DIFFERENT')
    nodes[1]['name']='哈希表'  # a lexical false positive, removable only by the saved verdict
    sample.payload['before']['nodes']=deepcopy(nodes)
    sample.payload['after']['nodes']=deepcopy(nodes)
    with connect(url) as db:
        head=fusion.read_draft_head(db,course.id)
        db.execute('BEGIN IMMEDIATE')
        plan=fusion.put_plan(db,course_id=course.id,task_id='new',head=head,input_digest='digest',payload=sample.payload)
        fusion.activate_plan(db,plan,applied=False)
        db.execute("UPDATE processing_tasks SET stage='awaiting_review',t6_seq=1 WHERE id='new'")
        db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?',(course.id,))
        db.execute('COMMIT')
    class Reader:
        def nodes(self,*args): return nodes
        def edges(self,*args): return []
    ctx=SimpleNamespace(sqlite_url=url,reader=Reader())
    return ctx,course.id,user.id,plan,nodes


def test_queue_and_action_totals_use_same_filter_and_stale_head_restores_legacy(queue_env):
    from app.services.graph.review import read_queue,resolve_duplicate
    from app.repositories.sqlite import connect
    from app.services.access import AccessDenied
    ctx,cid,actor,plan,nodes=queue_env
    queue=read_queue(ctx,cid)
    assert queue['suspected_duplicates']==[]
    assert queue['totals']['suspected_duplicates']==0
    assert queue['disambiguation']['different_pairs']==1
    with pytest.raises(AccessDenied): resolve_duplicate(ctx,cid,['a','b'],'reject',None,actor)
    with connect(ctx.sqlite_url) as db:
        db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?',(cid,))
    queue=read_queue(ctx,cid)
    assert queue['totals']['suspected_duplicates']==1
    assert queue['disambiguation']['status']=='stale'
    result=resolve_duplicate(ctx,cid,['a','b'],'reject',None,actor)
    assert result.changed and result.totals['suspected_duplicates']==0
    assert not resolve_duplicate(ctx,cid,['a','b'],'reject',None,actor).changed


def test_queue_semantic_candidates_pagination_and_totals_are_shared(queue_env,monkeypatch):
    from app.services.graph.review import read_queue,resolve_duplicate
    from app.repositories import fusion
    ctx,cid,actor,plan,nodes=queue_env
    payload=deepcopy(plan.payload)
    payload['decisions'][0]=decision('a','b','UNCERTAIN')
    nodes[1]['name']='散列表'
    monkeypatch.setattr(fusion,'latest_review_plan',lambda *_:replace(plan,state='committed',payload=payload))
    queue=read_queue(ctx,cid,kind='suspected_duplicate',limit=1)
    assert queue['totals']['suspected_duplicates']==1
    assert queue['suspected_duplicates'][0]['reason']=='semantic_uncertain'
    assert queue['suspected_duplicates'][0]['analysis']['plan_id']==plan.plan_id
    assert queue['next_cursors']['suspected_duplicates'] is None
    result=resolve_duplicate(ctx,cid,['a','b'],'reject',None,actor)
    assert result.changed and result.totals['suspected_duplicates']==0


def test_changing_head_read_is_bounded_and_returns_storage_error(queue_env,monkeypatch):
    from app.services.graph.review import read_queue
    from app.repositories.neo4j import RepositoryError
    from app.repositories.sqlite import connect
    ctx,cid,_,_,nodes=queue_env
    calls=[]
    def changing(*args):
        calls.append(1)
        with connect(ctx.sqlite_url) as db:
            db.execute('UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?',(cid,))
        return nodes
    monkeypatch.setattr(ctx.reader,'nodes',changing)
    with pytest.raises(RepositoryError): read_queue(ctx,cid)
    assert len(calls)==2


def test_projected_pair_aggregates_every_original_member_not_only_first_recall_pair():
    head,plan,nodes=fixture('UNCERTAIN')
    plan.payload['before']['nodes'].append(node('c'))
    plan.payload['mapping']={'a':'a','b':'b','c':'a'}
    plan.payload['groups']=[dict(group_id='g',members=['a','c'],canonical_id='a')]
    plan.payload['decisions'] += [decision('b','c','DIFFERENT'),decision('a','c','SAME')]
    plan.payload['recall']['pairs'] += [dict(left_id='b',right_id='c',channels=['vector'],rank_score=.1)]
    plan.payload.update(total_pairs=3,examined_pairs=3,completed_pairs=3)
    plan=replace(plan,applied=True)
    head=replace(head,storage_version_id=plan.storage_version_id)
    assert build_review_view(head,plan,nodes).proposals==()
