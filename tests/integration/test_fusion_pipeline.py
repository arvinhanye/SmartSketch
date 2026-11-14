"""Generation must consume a checked map and atomically select the new draft."""
from dataclasses import replace
import json
import sqlite3
import pytest

from app.repositories import fusion, task_leases
from app.repositories.graph_projection import read_snapshot
from app.repositories.model_calls import SqliteCallStore
from app.repositories.sqlite import connect
from app.services.ai.entities import EntityExtractor
from app.services.ai.relations import RelationExtractor
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import ModelCallPolicy
from app.services.fusion.resolution import SemanticResolver
from app.workers.extract_task import ExtractionToolkit
from app.workers import persist_graph
from tests.backend.helpers.accounts import make_account
from tests.integration import test_f13 as f13
from tests.integration.test_f13 import graph, live, db_url, storage


def setup_task(db_url, storage, graph, monkeypatch, *, pairs=(), names=('概念11', '概念12')):
    user = make_account(db_url, "teacher", "teacher")
    with connect(db_url) as db:
        db.execute("INSERT INTO courses(id,name,teacher_id) VALUES(?, 'test', ?)", (graph.course, user.id))
        db.execute("INSERT INTO course_members(course_id,user_id,role) VALUES(?,?,'teacher')", (graph.course, user.id))
    def respond(request):
        if "待分析材料数据" not in request.messages[0].content:
            return f13._responder(request)
        payload = json.loads(request.messages[0].content.splitlines()[-1])
        return json.dumps(dict(verdict="SAME", basis="mixed", reason="fixture synonyms", differences=[],
            left_source_ids=[payload["left"]["sources"][0]["source_id"]],
            right_source_ids=[payload["right"]["sources"][0]["source_id"]]))
    client = FakeModelClient(responder=respond)
    policy = ModelCallPolicy(primary=client, store=SqliteCallStore(db_url), max_retries=0,
        failure_threshold=100, open_seconds=30, task_token_budget=10**9, daily_token_budget=10**9)
    toolkit = ExtractionToolkit(policy=policy, preserve_mentions=True,
        entities=lambda c: EntityExtractor(c, model="m", max_output_tokens=4000),
        relations=lambda c: RelationExtractor(c, model="m", max_output_tokens=4000),
        resolver=lambda c: SemanticResolver(c, model="m"))
    monkeypatch.setattr(f13, "_toolkit", lambda _: toolkit)
    lease = f13._to_merging(db_url, storage, f13._material(list(pairs), list(names)), graph.course)
    return lease, toolkit, client, user.id


def prepare(db_url, lease, graph, toolkit):
    from app.workers.fusion_task import prepare_fusion
    return prepare_fusion(db_url, lease, repo=graph.repo, toolkit=toolkit,
                          max_pairs=16, top_k=8, lock_seconds=60, lock_wait_seconds=0)


@live
def test_generated_mapping_is_consumed_and_repeat_preparation_reuses_saved_result(db_url, storage, graph, monkeypatch):
    lease, toolkit, client, _ = setup_task(db_url, storage, graph, monkeypatch)
    plan = prepare(db_url, lease, graph, toolkit)
    assert len(plan.payload["groups"]) == 1
    calls = len(client.calls)
    assert prepare(db_url, lease, graph, toolkit).plan_id == plan.plan_id
    assert len(client.calls) == calls
    with connect(db_url) as db:
        assert not read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))["nodes"]
    assert persist_graph.run_merge_stage(db_url, lease).status is persist_graph.PersistStatus.ADVANCED
    outcome = f13._persist(db_url, lease, graph.repo)
    assert outcome.status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db:
        scope = fusion.read_draft_scope(db, graph.course)
        assert scope.storage_version_id == plan.storage_version_id
        assert fusion.get_plan(db, graph.course, plan.plan_id).applied
    result = read_snapshot(graph.repo, scope)
    assert len(result["nodes"]) == 1 and len(result["evidence"]) == 2
    assert not result["nodes"][0]["locked"]
    # Publication must read the selected physical generation through the ordinary service.
    from app.repositories.versions import read_draft_state
    from app.repositories.graph_read import GraphReader
    from app.services.versions.publish import load_draft
    publication = load_draft(db_url, GraphReader(graph.repo), read_draft_state(db_url, graph.course))
    assert len(publication.nodes) == 1
    assert set(publication.nodes[0].source_refs) == {e['chunk_id'] for e in result['evidence']}


@live
def test_graph_commit_without_t6_does_not_change_visible_draft_then_takeover_is_idempotent(db_url, storage, graph, monkeypatch):
    lease, toolkit, _, _ = setup_task(db_url, storage, graph, monkeypatch)
    plan = prepare(db_url, lease, graph, toolkit)
    persist_graph.run_merge_stage(db_url, lease)
    real_t6 = persist_graph._t6_in
    def fail(*args): raise sqlite3.OperationalError("injected T6 failure")
    monkeypatch.setattr(persist_graph, "_t6_in", fail)
    assert f13._persist(db_url, lease, graph.repo).status is persist_graph.PersistStatus.LOST
    with connect(db_url) as db:
        assert fusion.read_draft_head(db, graph.course).storage_version_id == "draft"
        assert not read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))["nodes"]
    monkeypatch.setattr(persist_graph, "_t6_in", real_t6)
    f13._expire(db_url, lease.task_id)
    task_leases.reclaim_expired(db_url, max_attempts=3)
    again = f13._claim(db_url, "takeover")
    assert f13._persist(db_url, again, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db:
        assert fusion.read_draft_head(db, graph.course).storage_version_id == plan.storage_version_id
        assert len(read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))["nodes"]) == 1


@live
def test_stale_fusion_keeps_raw_nodes_and_marks_unapplied_plan(db_url, storage, graph, monkeypatch):
    lease, toolkit, _, _ = setup_task(db_url, storage, graph, monkeypatch)
    plan = prepare(db_url, lease, graph, toolkit)
    with connect(db_url) as db:
        db.execute("UPDATE courses SET draft_revision=draft_revision+1 WHERE id=?", (graph.course,))
    persist_graph.run_merge_stage(db_url, lease)
    assert f13._persist(db_url, lease, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db:
        saved = fusion.get_plan(db, graph.course, plan.plan_id)
        assert not saved.applied and saved.reason == "stale_snapshot"
        assert len(read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))["nodes"]) == 2


@live
def test_semantic_same_cannot_collapse_an_existing_prerequisite(db_url, storage, graph, monkeypatch):
    lease, toolkit, _, _ = setup_task(db_url, storage, graph, monkeypatch, pairs=[("概念12", "概念11")])
    plan = prepare(db_url, lease, graph, toolkit)
    assert not plan.payload["groups"] and plan.payload["blocked"]
    persist_graph.run_merge_stage(db_url, lease)
    assert f13._persist(db_url, lease, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db:
        result = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))
    assert len(result["nodes"]) == 2 and len(result["edges"]) == 1


@live
@pytest.mark.parametrize('enabled', [False, True])
def test_pipeline_reclaims_merging_and_obeys_auto_switch(db_url, storage, graph, monkeypatch, enabled):
    from app.config import load_settings
    lease, toolkit, _, _ = setup_task(db_url, storage, graph, monkeypatch)
    f13._expire(db_url, lease.task_id)
    settings = load_settings(dict(SQLITE_URL=db_url, STORAGE_DIR=str(storage.root),
        TASK_LEASE_SECONDS='60', DISAMBIGUATION_AUTO_MERGE_ENABLED=str(enabled).lower()))
    result = persist_graph.run_pipeline_once(settings, toolkit=toolkit, repo=graph.repo, storage=storage)
    assert result.stages == (('merging', 'advanced'), ('persisting', 'advanced'))
    with connect(db_url) as db:
        found = fusion.task_plan(db, graph.course, lease.task_id)
        assert (found is not None and found.applied) == enabled
        assert len(read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))['nodes']) == (1 if enabled else 2)


@live
def test_cancellation_between_judgments_does_not_store_or_activate_plan(db_url, storage, graph, monkeypatch):
    from app.workers.fusion_task import FusionCancelled
    lease, toolkit, client, _ = setup_task(db_url, storage, graph, monkeypatch)
    checked = []
    def cancel():
        checked.append(1)
        if len(checked) == 5:
            with connect(db_url) as db:
                db.execute('UPDATE processing_tasks SET cancel_requested=1 WHERE id=?', (lease.task_id,))
    guarded = replace(toolkit, guard=cancel)
    with pytest.raises(FusionCancelled): prepare(db_url, lease, graph, guarded)
    assert persist_graph.run_merge_stage(db_url, lease).status is persist_graph.PersistStatus.CANCELLED
    with connect(db_url) as db: assert fusion.task_plan(db, graph.course, lease.task_id) is None


@live
def test_undo_restores_raw_occurrences_idempotently_and_keeps_later_nodes(db_url, storage, graph, monkeypatch):
    from app.services.fusion.undo import preview_undo, undo_merge
    from app.repositories.graph_nodes import derive_kp_id
    lease, toolkit, _, actor = setup_task(db_url, storage, graph, monkeypatch)
    plan = prepare(db_url, lease, graph, toolkit)
    persist_graph.run_merge_stage(db_url, lease)
    assert f13._persist(db_url, lease, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    # A later unrelated task must survive undo of the first task's one group.
    later = f13._to_merging(db_url, storage, f13._material([], ['概念99']), graph.course)
    persist_graph.run_merge_stage(db_url, later)
    assert f13._persist(db_url, later, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    with connect(db_url) as db: head = fusion.read_draft_head(db, graph.course)
    kw = dict(sqlite_url=db_url, repo=graph.repo, course_id=graph.course, plan_id=plan.plan_id,
              group_id=plan.payload['groups'][0]['group_id'], actor_id=actor,
              expected_revision=head.draft_revision, lock_seconds=60, wait_seconds=0)
    with connect(db_url) as db:
        assert len(read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))['nodes']) == 2
    preview = preview_undo(**kw)
    assert preview.status == 'ready'
    done = undo_merge(**kw)
    assert done.status == 'undone'
    assert undo_merge(**kw).status == 'already_undone'
    with connect(db_url) as db:
        after_head = fusion.read_draft_head(db, graph.course)
        assert after_head.draft_revision == head.draft_revision + 1
        assert db.execute('SELECT stage FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone()[0] == 'awaiting_review'
        assert db.execute('SELECT count(*) FROM fusion_undos').fetchone()[0] == 1
        result = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))
    assert {n['name'] for n in result['nodes']} == {'概念11', '概念12', '概念99'}
    assert len(result['evidence']) == 3
    original = {n['kp_id']: n['revision'] for n in plan.payload['before']['nodes']}
    merged = {n['kp_id']: n['revision'] for n in plan.payload['after']['nodes']}
    for node in result['nodes']:
        if node['kp_id'] in original:
            assert node['revision'] > max(original[node['kp_id']], merged.get(node['kp_id'], 0))


@live
@pytest.mark.parametrize('reverse', [False, True])
def test_independent_automatic_groups_undo_in_either_order_with_fresh_node_revisions(
        db_url, storage, graph, monkeypatch, reverse):
    from app.services.fusion.undo import undo_merge
    lease, toolkit, model, actor = setup_task(db_url, storage, graph, monkeypatch,
                                            names=('概念11', '概念12', '概念13', '概念14'))
    def respond(request):
        pair = json.loads(request.messages[0].content.splitlines()[-1])
        names = {pair['left']['name'], pair['right']['name']}
        same = names <= {'概念11', '概念12'} or names <= {'概念13', '概念14'}
        return json.dumps(dict(verdict='SAME' if same else 'DIFFERENT', basis='mixed',
            reason='fixture independent groups', differences=[] if same else ['different group'],
            left_source_ids=[pair['left']['sources'][0]['source_id']],
            right_source_ids=[pair['right']['sources'][0]['source_id']]))
    monkeypatch.setattr(model, '_responder', respond)
    plan = prepare(db_url, lease, graph, toolkit)
    assert len(plan.payload['groups']) == 2
    persist_graph.run_merge_stage(db_url, lease)
    assert f13._persist(db_url, lease, graph.repo).status is persist_graph.PersistStatus.ADVANCED
    groups = list(reversed(plan.payload['groups'])) if reverse else plan.payload['groups']
    prior_restored = {}
    for group in groups:
        with connect(db_url) as db:
            head = fusion.read_draft_head(db, graph.course)
        result = undo_merge(sqlite_url=db_url, repo=graph.repo, course_id=graph.course,
            plan_id=plan.plan_id, group_id=group['group_id'], actor_id=actor,
            expected_revision=head.draft_revision, lock_seconds=60, wait_seconds=0)
        assert result.status == 'undone'
        with connect(db_url) as db:
            current = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))
        nodes = {n['kp_id']: n for n in current['nodes']}
        assert all(nodes[key] == node for key, node in prior_restored.items())
        prior_restored.update({key: nodes[key] for key in group['members']})
    assert {n['name'] for n in current['nodes']} == {'概念11', '概念12', '概念13', '概念14'}
    assert all(n['revision'] > 1 for n in current['nodes'])


@live
def test_undo_sql_failure_leaves_visible_draft_unchanged(db_url, storage, graph, monkeypatch):
    from app.services.fusion.undo import undo_merge
    lease, toolkit, _, actor = setup_task(db_url, storage, graph, monkeypatch)
    plan = prepare(db_url, lease, graph, toolkit)
    persist_graph.run_merge_stage(db_url, lease); f13._persist(db_url, lease, graph.repo)
    with connect(db_url) as db: head = fusion.read_draft_head(db, graph.course)
    real = fusion.record_undo
    def fail(*args, **kwargs): raise sqlite3.OperationalError('injected undo failure')
    monkeypatch.setattr(fusion, 'record_undo', fail)
    kw = dict(sqlite_url=db_url, repo=graph.repo, course_id=graph.course, plan_id=plan.plan_id,
              group_id=plan.payload['groups'][0]['group_id'], actor_id=actor,
              expected_revision=head.draft_revision, lock_seconds=60, wait_seconds=0)
    with pytest.raises(sqlite3.OperationalError): undo_merge(**kw)
    with connect(db_url) as db:
        assert fusion.read_draft_head(db, graph.course) == head
        assert len(read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))['nodes']) == 1
    monkeypatch.setattr(fusion, 'record_undo', real)
    assert undo_merge(**kw).status == 'undone'


@live
def test_cross_task_mapping_keeps_existing_id_and_undo_detects_later_mapping(db_url, storage, graph, monkeypatch):
    from app.services.fusion.undo import preview_undo
    lease, toolkit, _, actor = setup_task(db_url, storage, graph, monkeypatch)
    ids = {}
    def ordered_ids(course_id, task_id, entity_id):
        if task_id != lease.task_id: return 'kp_m'
        if entity_id not in ids: ids[entity_id] = 'kp_a' if not ids else 'kp_z'
        return ids[entity_id]
    # Existing canonical a has hidden original z; later m makes z/m reversed,
    # regardless of the random course/task hashes used by the fixture.
    monkeypatch.setattr(persist_graph, 'derive_kp_id', ordered_ids)
    first = prepare(db_url, lease, graph, toolkit)
    persist_graph.run_merge_stage(db_url, lease); f13._persist(db_url, lease, graph.repo)
    canonical = first.payload['groups'][0]['canonical_id']
    later = f13._to_merging(db_url, storage, f13._material([], ['概念13']), graph.course)
    second = prepare(db_url, later, graph, toolkit)
    assert second.payload['groups'][0]['canonical_id'] == canonical
    persist_graph.run_merge_stage(db_url, later); f13._persist(db_url, later, graph.repo)
    with connect(db_url) as db:
        head = fusion.read_draft_head(db, graph.course)
        result = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))
    assert len(result['nodes']) == 1 and len(result['evidence']) == 3
    preview = preview_undo(sqlite_url=db_url, repo=graph.repo, course_id=graph.course, plan_id=first.plan_id,
        group_id=first.payload['groups'][0]['group_id'], actor_id=actor, expected_revision=head.draft_revision,
        lock_seconds=60, wait_seconds=0)
    assert preview.status == 'conflict' and preview.conflicts


@live
def test_undo_requires_teacher_current_revision_and_preserves_published_copy(db_url, storage, graph, monkeypatch):
    from app.services.fusion.undo import preview_undo, undo_merge
    lease, toolkit, _, actor = setup_task(db_url, storage, graph, monkeypatch)
    plan = prepare(db_url, lease, graph, toolkit)
    persist_graph.run_merge_stage(db_url, lease); f13._persist(db_url, lease, graph.repo)
    with connect(db_url) as db: head = fusion.read_draft_head(db, graph.course)
    graph.q("CREATE (n:KnowledgePoint {course_id:$c,version_id:'published-test',kp_id:'published',name:'frozen'})", c=graph.course)
    kw = dict(sqlite_url=db_url, repo=graph.repo, course_id=graph.course, plan_id=plan.plan_id,
              group_id=plan.payload['groups'][0]['group_id'], actor_id=actor,
              expected_revision=head.draft_revision, lock_seconds=60, wait_seconds=0)
    with pytest.raises(PermissionError): preview_undo(**{**kw, 'actor_id':'stranger'})
    assert preview_undo(**{**kw, 'expected_revision':0}).conflicts == ({'reason':'stale_revision'},)
    assert undo_merge(**kw).status == 'undone'
    assert graph.q("MATCH(n:KnowledgePoint {course_id:$c,version_id:'published-test'}) RETURN n.name AS name", c=graph.course) == [{'name':'frozen'}]


@live
@pytest.mark.parametrize('fault', ['auth', 'record', 'circuit', 'credential'])
def test_global_analysis_task_failures_preserve_task_semantics(db_url, storage, graph, monkeypatch, fault):
    from app.config import load_settings
    from app.services.ai.client import ModelAuthError
    from app.services.ai.policy import CallRecordError, ModelUnavailableError
    from app.services.credentials import CredentialUnavailable
    from app.workers.fusion_task import run_fusion_stage
    lease, toolkit, _, _ = setup_task(db_url, storage, graph, monkeypatch)
    errors = dict(auth=ModelAuthError('m'), record=CallRecordError(),
                  circuit=ModelUnavailableError(), credential=CredentialUnavailable('credential_unreadable'))
    def fail(): raise errors[fault]
    settings = load_settings(dict(SQLITE_URL=db_url))
    result = run_fusion_stage(settings, lease, repo=graph.repo, toolkit=replace(toolkit, guard=fail),
                             lock_seconds=60, lock_wait_seconds=0)
    assert result.status.value == ('failed' if fault in ('auth','credential') else 'released')
    with connect(db_url) as db: assert fusion.task_plan(db, graph.course, lease.task_id) is None


@live
def test_corpus_budget_stops_inference_and_reports_partial(db_url, storage, graph, monkeypatch):
    from app.workers.fusion_task import prepare_fusion
    lease, toolkit, client, _ = setup_task(db_url, storage, graph, monkeypatch)
    count = len(client.calls)
    plan = prepare_fusion(db_url, lease, repo=graph.repo, toolkit=toolkit, max_pairs=16, top_k=8,
                          lock_seconds=60, lock_wait_seconds=0, max_corpus_bytes=1)
    assert len(client.calls) == count and not plan.payload['groups']
    assert plan.payload['completion']=='partial' and plan.payload['reason']=='corpus_budget'
    assert plan.payload['unprocessed_pairs']==1


@live
def test_embedding_audit_failure_is_not_silently_a_missing_channel(db_url, storage, graph, monkeypatch):
    from app.workers.fusion_task import prepare_fusion
    from app.services.ai.embeddings import EmbeddingRecordError
    lease, toolkit, client, _ = setup_task(db_url, storage, graph, monkeypatch)
    class BrokenAudit:
        space = 'real/test/2'
        def embed(self, *a, **kw): raise EmbeddingRecordError('injected', 0, 0)
    with pytest.raises(EmbeddingRecordError):
        prepare_fusion(db_url, lease, repo=graph.repo, toolkit=toolkit, max_pairs=16, top_k=8,
                       lock_seconds=60, lock_wait_seconds=0, embedding=BrokenAudit())


@live
@pytest.mark.parametrize('timing', ['before_analysis', 'before_t6'])
def test_teacher_not_duplicate_decision_blocks_global_merge(db_url, storage, graph, monkeypatch, timing):
    from app.repositories import review
    lease, toolkit, _, actor = setup_task(db_url, storage, graph, monkeypatch)
    # Existing unmerged task nodes are valid targets of teacher dismissal.
    persist_graph.run_merge_stage(db_url, lease); f13._persist(db_url, lease, graph.repo)
    with connect(db_url) as db:
        prior = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))
    a,b = [n['kp_id'] for n in prior['nodes']]
    later = f13._to_merging(db_url, storage, f13._material([], ['概念13']), graph.course)
    if timing=='before_analysis': review.dismiss(db_url, graph.course, review.DUPLICATE, review.pair_key(a,b), actor)
    plan = prepare(db_url, later, graph, toolkit)
    if timing=='before_t6': review.dismiss(db_url, graph.course, review.DUPLICATE, review.pair_key(a,b), actor)
    persist_graph.run_merge_stage(db_url, later); f13._persist(db_url, later, graph.repo)
    with connect(db_url) as db:
        now = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))
        saved = fusion.get_plan(db, graph.course, plan.plan_id)
    assert all(not {a,b} <= {n['kp_id'], *n.get('merged_from',[])} for n in now['nodes'])
    if timing=='before_t6': assert saved.reason=='stale_snapshot'


@live
def test_cross_task_extension_checks_lost_member_definition_again(db_url, storage, graph, monkeypatch):
    lease, toolkit, _, _ = setup_task(db_url, storage, graph, monkeypatch)
    first = prepare(db_url, lease, graph, toolkit)
    persist_graph.run_merge_stage(db_url, lease); f13._persist(db_url, lease, graph.repo)
    canonical = first.payload['groups'][0]['canonical_id']
    lost = next(n['name'] for n in first.payload['before']['nodes'] if n['kp_id']!=canonical)
    later = f13._to_merging(db_url, storage, f13._material([], ['概念13']), graph.course)
    seen=[]
    def respond(request):
        payload = json.loads(request.messages[0].content.splitlines()[-1]); seen.append(payload)
        same = lost not in (payload['left']['name'], payload['right']['name'])
        return json.dumps(dict(verdict='SAME' if same else 'DIFFERENT', basis='mixed', reason='fixture different original sense',
            differences=[] if same else ['原始定义不同'],
            left_source_ids=[payload['left']['sources'][0]['source_id']],
            right_source_ids=[payload['right']['sources'][0]['source_id']]))
    client=FakeModelClient(responder=respond)
    policy=ModelCallPolicy(primary=client, store=SqliteCallStore(db_url), max_retries=0,
        failure_threshold=100, open_seconds=30, task_token_budget=10**9, daily_token_budget=10**9)
    second=prepare(db_url,later,graph,replace(toolkit,policy=policy))
    assert not second.payload['groups']
    assert any(lost in (p['left']['name'],p['right']['name']) for p in seen)


@live
def test_teacher_keep_isolated_decision_protects_original_node(db_url, storage, graph, monkeypatch):
    from app.repositories import review
    lease, toolkit, _, actor = setup_task(db_url, storage, graph, monkeypatch)
    persist_graph.run_merge_stage(db_url, lease); f13._persist(db_url, lease, graph.repo)
    with connect(db_url) as db:
        kept = read_snapshot(graph.repo, fusion.read_draft_scope(db, graph.course))['nodes'][0]
    review.dismiss(db_url, graph.course, review.ISOLATED, kept['kp_id'], actor)
    later = f13._to_merging(db_url, storage, f13._material([], ['概念13']), graph.course)
    plan = prepare(db_url, later, graph, toolkit)
    assert all(kept['kp_id'] not in group['members'] for group in plan.payload['groups'])
    assert next(n for n in plan.payload['after']['nodes'] if n['kp_id']==kept['kp_id']) == kept
