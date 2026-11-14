"""Real extractor/worker boundaries, synthetic provider only; no paid requests."""
from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import pytest

from app.repositories.chunks import StoredChunk
from app.repositories.extraction_checkpoints import Checkpoint
from app.services.ai.client import Message, ModelRequest
from app.services.ai.entities import EntityExtractor
from app.services.ai.extraction_windows import WindowPolicy
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import CallAttribution, ModelCallPolicy
from app.services.ai.relations import RelationExtractor, SectionEntity
from app.services.ai.request_budget import WindowBudgetError
from app.services.credentials import CredentialUnavailable
from app.workers.extraction.types import ExtractionToolkit, ExtractLimits, _Section
from app.workers.extraction.units import _AttemptClient, _extract_chunk, _extract_section
from tests.backend.test_extraction_windows import source
from tests.backend.test_e12 import storage


def stored(text, index=0):
    c = source(text, index)
    i = c.identity
    return StoredChunk(i.chunk_id,i.course_id,i.document_id,i.revision_id,i.ordinal,c.text,i.text_sha256,(),i.sources)


def policy(client):
    return ModelCallPolicy(primary=client,
        store=SimpleNamespace(prewrite=lambda *a,**k:None, finish=lambda *a,**k:None),
        max_retries=0, failure_threshold=1000, open_seconds=30,
        task_token_budget=10**9, daily_token_budget=10**9)


def toolkit(client, **kwargs):
    return ExtractionToolkit(policy=policy(client), preserve_mentions=True,
        entities=lambda c: EntityExtractor(c,model='m',max_output_tokens=256),
        relations=lambda c: RelationExtractor(c,model='m',max_output_tokens=256),
        window_policy=WindowPolicy(max_input_bytes=5000,overlap_chars=64,max_windows=64), **kwargs)


LEASE = SimpleNamespace(course_id='c',task_id='t',attempt=1)
LIMITS = ExtractLimits(max_attempts=3,chunk_max_attempts=1)
QUOTE = '锚点是一个测试概念。'


def entity_reply(request):
    text = request.messages[0].content.split('资料块：\n',1)[1]
    rows = []
    start = 0
    while (start := text.find(QUOTE,start)) >= 0:
        rows.append(dict(name='锚点',type='concept',definition='测试定义',evidence=QUOTE,evidence_start=start))
        start += len(QUOTE)
    return json.dumps({'entities':rows},ensure_ascii=False)


def test_entity_offsets_and_page_survive_windows_without_collapsing_distinct_mentions():
    text = '甲'*600 + QUOTE + '乙'*1000 + QUOTE + '丙'*1600
    client = FakeModelClient(responder=entity_reply)
    outcome = _extract_chunk(toolkit(client),LEASE,LIMITS,stored(text))
    assert outcome.status == 'done'
    rows = outcome.result['entities']
    assert len(rows) == 2
    assert sorted(r['source']['evidence_start'] for r in rows) == [600, 1600+len(QUOTE)]
    assert all(r['source']['sources'][0]['locator']['page'] == 7 for r in rows)
    assert all(text[r['source']['evidence_start']:r['source']['evidence_end']] == QUOTE for r in rows)
    assert all(not r['source'].get('evidence_ambiguous',False) for r in rows)
    coverage = outcome.metadata['window_coverage']
    assert coverage['status'] == 'complete' and coverage['completed_windows'] == coverage['planned_windows'] > 1
    assert len(coverage['input_digest']) == 64
    assert all(sum(len(m.content.encode())+256 for m in call.request.messages)+4*call.request.max_output_tokens <= 5000
               for call in client.calls)


def test_relation_evidence_is_restored_to_original_block_offset_and_locator():
    quote='甲和乙彼此相关。'
    text='前文'*1200+quote+'后文'*600
    chunk=stored(text,1)
    def respond(request):
        return json.dumps({'relations': [dict(from_id='a',to_id='b',type='RELATED_TO',evidence=quote)]
                           if quote in request.messages[0].content else []},ensure_ascii=False)
    client=FakeModelClient(responder=respond)
    outcome=_extract_section(toolkit(client),LEASE,LIMITS,_Section('s',('r',0),None,(chunk,)),
        (SectionEntity('a','c','甲','concept'),SectionEntity('b','c','乙','concept')))
    assert outcome.status=='done' and len(outcome.result['relations'])==1
    row=outcome.result['relations'][0]
    assert row['source']['chunk_id']==chunk.chunk_id
    assert row['source']['evidence_start']==2400
    assert row['source']['sources'][0]['locator']['page']==8
    assert outcome.metadata['window_coverage']['status']=='complete'


def test_failed_later_window_does_not_commit_early_partial_entities():
    def respond(request):
        return entity_reply(request) if len(client.calls)==1 else 'not JSON'
    client=FakeModelClient(responder=respond)
    outcome=_extract_chunk(toolkit(client),LEASE,LIMITS,stored(QUOTE+'甲'*5000))
    assert outcome.status=='failed'
    assert outcome.result is None
    assert outcome.metadata['window_coverage']['status']=='partial'
    assert outcome.metadata['window_coverage']['completed_windows']==1
    assert outcome.metadata['window_coverage']['reason']=='output_invalid'


def test_window_limit_fails_before_provider_and_records_technical_gap():
    client=FakeModelClient(responder=entity_reply)
    kit=replace(toolkit(client),window_policy=WindowPolicy(max_input_bytes=5000,overlap_chars=64,max_windows=1))
    outcome=_extract_chunk(kit,LEASE,LIMITS,stored('甲'*5000))
    assert outcome.status=='failed' and not client.calls
    assert outcome.metadata['window_coverage']['reason']=='window_limit'


@pytest.mark.parametrize('purpose',['extract_entities','extract_relations','extract_entities_gleaning','repair'])
def test_physical_request_guard_includes_output_reserve_for_every_extraction_purpose(purpose):
    client=FakeModelClient()
    wrapped=_AttemptClient(policy(client),CallAttribution(course_id='c',task_id='t'),max_input_bytes=5000)
    request=ModelRequest(purpose=purpose,model='m',messages=(Message('user','x'*4500),),max_output_tokens=128)
    with pytest.raises(WindowBudgetError,match='input_budget'):
        wrapped.complete(request)
    assert not client.calls


def test_credential_guard_stops_between_windows():
    client=FakeModelClient(responder=entity_reply)
    def guard():
        if client.calls: raise CredentialUnavailable('credential_revoked')
    with pytest.raises(CredentialUnavailable):
        _extract_chunk(toolkit(client,guard=guard),LEASE,LIMITS,stored('甲'*5000))
    assert len(client.calls)==1


def test_factory_enables_windows_only_with_disambiguation():
    from app.config import load_settings
    from app.workers.runner import build_toolkit
    assert build_toolkit(load_settings({})).window_policy is None
    kit=build_toolkit(load_settings({'DISAMBIGUATION_ANALYSIS_ENABLED':'true'}))
    assert isinstance(kit.window_policy,WindowPolicy)


def test_checkpoint_policy_pins_resume_and_legacy_stays_legacy():
    from app.workers.extraction.windowed import checkpoint_policy
    old=WindowPolicy(max_input_bytes=6000,overlap_chars=32,max_windows=16)
    current=WindowPolicy()
    def checkpoint(data): return Checkpoint('chunk','id','done',1,None,{},data)
    assert checkpoint_policy(current,[])==current
    assert checkpoint_policy(current,[checkpoint({'window_policy':asdict(old)})])==old
    assert checkpoint_policy(current,[checkpoint({'entity_identity_version':2})]) is None
    with pytest.raises(ValueError):
        checkpoint_policy(current,[checkpoint({'window_policy':asdict(old)}),checkpoint({})])


def test_failed_window_roundtrips_through_real_checkpoint_and_keeps_policy(db_url,storage):
    from tests.backend.test_e12 import _extracting
    from app.repositories.extraction_checkpoints import list_checkpoints
    from app.repositories.chunks import get_chunks
    from app.workers.extraction.state import _write_unit
    from app.workers.extraction.windowed import checkpoint_policy
    lease,ids=_extracting(db_url,storage)
    client=FakeModelClient()
    kit=replace(toolkit(client),window_policy=WindowPolicy(max_input_bytes=1024))
    chunk=get_chunks(db_url,course_id=lease.course_id,chunk_ids=[ids[0]])[0]
    result=_extract_chunk(kit,lease,LIMITS,chunk)
    assert result.status=='failed'
    assert _write_unit(db_url,lease,'chunk',chunk.chunk_id,result,0.2)
    checkpoint=list_checkpoints(db_url,course_id=lease.course_id,task_id=lease.task_id)[0]
    assert checkpoint.result is None
    assert checkpoint.metadata['window_coverage']['reason']=='input_budget'
    assert checkpoint_policy(WindowPolicy(),[checkpoint])==kit.window_policy
    assert not client.calls


def test_metadata_rollback_blocks_active_tasks_and_preserves_finished_candidates(db_url,storage):
    import sqlite3
    from tests.backend.test_e12 import _extracting
    from app.repositories.extraction_checkpoints import write_checkpoint, list_checkpoints
    from app.repositories.sqlite import connect, migrate, MIGRATIONS_DIR
    from app.repositories.task_leases import leased_transaction
    lease,ids=_extracting(db_url,storage)
    with leased_transaction(db_url,lease.task_id,lease.token) as db:
        write_checkpoint(db,course_id=lease.course_id,task_id=lease.task_id,unit_kind='chunk',
            unit_id=ids[0],status='done',attempts=1,result={'entities':[]},metadata={'window_policy':asdict(WindowPolicy())})
        write_checkpoint(db,course_id=lease.course_id,task_id=lease.task_id,unit_kind='chunk',
            unit_id=ids[1],status='failed',attempts=1,error_code='OUTPUT_INVALID',metadata={'window_coverage':{}})
    migration=MIGRATIONS_DIR/'022_extraction_window_metadata.sql'
    commands=[line.removeprefix('-- ROLLBACK: ') for line in migration.read_text().splitlines()
              if line.startswith('-- ROLLBACK: ')]
    with connect(db_url) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE task_chunk_checkpoints SET metadata='{}'")
        db.execute('BEGIN')
        with pytest.raises(sqlite3.IntegrityError):
            for command in commands: db.execute(command)
        db.rollback()
        assert 'metadata' in {r[1] for r in db.execute('PRAGMA table_info(task_chunk_checkpoints)')}
        db.execute("""UPDATE processing_tasks SET stage='cancelled',cancel_requested=1,
                   lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL WHERE id=?""",(lease.task_id,))
        db.execute('BEGIN')
        for command in commands: db.execute(command)
        db.commit()
        assert db.execute('SELECT status,result FROM task_chunk_checkpoints ORDER BY unit_id').fetchall()==[
            ('done','{"entities": []}'),('failed',None)]
    migrate(db_url)
    rows=list_checkpoints(db_url,course_id=lease.course_id,task_id=lease.task_id)
    assert all(c.metadata is None for c in rows)


@pytest.mark.parametrize('rounds',[1,2])
def test_long_window_with_real_gleaner_preserves_added_occurrences_under_budget(rounds):
    from app.services.ai.gleaning import EntityGleaner
    def respond(request):
        if request.purpose=='extract_entities': return entity_reply(request)
        text=request.messages[0].content.split('资料块：\n',1)[1]
        start=text.find(QUOTE)
        return json.dumps({'entities':[] if start<0 else [dict(name='补漏',type='concept',
            definition='补漏定义',evidence=QUOTE,evidence_start=start)]},ensure_ascii=False)
    client=FakeModelClient(responder=respond)
    kit=toolkit(client,gleaner=lambda c:EntityGleaner(c,model='m',max_output_tokens=256,enabled=True,max_rounds=rounds))
    text=QUOTE+'甲'*5000+QUOTE
    outcome=_extract_chunk(kit,LEASE,LIMITS,stored(text))
    assert outcome.status=='done'
    added=[r for r in outcome.result['entities'] if r['name']=='补漏']
    assert sorted(r['source']['evidence_start'] for r in added)==[0,len(QUOTE)+5000]
    coverage=outcome.metadata['window_coverage']
    assert coverage['gleaning_completed_windows']==coverage['gleaning_planned_windows']>1
    assert all(sum(len(m.content.encode())+256 for m in call.request.messages)+4*call.request.max_output_tokens<=5000
               for call in client.calls)


def test_relation_limit_preflight_precedes_semantic_model_calls():
    from app.services.ai.entities import EntityCandidate,EntitySource
    from app.services.fusion.resolution import SemanticResolver
    from app.workers.extraction.types import TaskEntity
    from tests.backend.test_disambiguation_generation import different
    chunk=stored('原文'+'甲'*2000)
    candidate=EntityCandidate('同名','concept','定义','原文',0.8,
        EntitySource('c',chunk.material_id,chunk.revision_id,chunk.chunk_id,0,2,chunk.sources))
    task_entities=tuple(TaskEntity(i,'同名','concept',(candidate,)) for i in ('a','b'))
    client=FakeModelClient(responder=different)
    kit=replace(toolkit(client,resolver=lambda c:SemanticResolver(c,model='m')),
                window_policy=WindowPolicy(max_input_bytes=5000,overlap_chars=64,max_windows=1))
    outcome=_extract_section(kit,LEASE,LIMITS,_Section('s',('r',0),None,(chunk,)),
        tuple(SectionEntity(e.entity_id,'c',e.name,e.type) for e in task_entities),task_entities=task_entities)
    assert outcome.status=='failed' and outcome.metadata['window_coverage']['reason']=='window_limit'
    assert not client.calls


def test_minimum_gleaning_windows_over_cap_are_rejected_before_any_call():
    from app.services.ai.gleaning import EntityGleaner
    client=FakeModelClient(responder=entity_reply)
    kit=replace(toolkit(client,gleaner=lambda c:EntityGleaner(c,model='m',max_output_tokens=256,enabled=True)),
                window_policy=WindowPolicy(max_input_bytes=5000,overlap_chars=64,max_windows=1))
    result=_extract_chunk(kit,LEASE,LIMITS,stored(QUOTE))
    assert result.status=='failed' and not client.calls
    assert result.metadata['window_coverage']['reason']=='window_limit'


def test_failed_gleaning_does_not_commit_primary_candidates():
    from app.services.ai.gleaning import EntityGleaner
    client=FakeModelClient(responder=lambda r:entity_reply(r) if r.purpose=='extract_entities' else 'bad JSON')
    result=_extract_chunk(toolkit(client,gleaner=lambda c:EntityGleaner(c,model='m',max_output_tokens=256,enabled=True)),
                          LEASE,LIMITS,stored(QUOTE))
    assert result.status=='failed' and result.result is None
    assert result.metadata['window_coverage']['reason']=='gleaning_incomplete'
