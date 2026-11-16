"""SQLite checkpoints preserve semantic work across relation faults and lease takeover."""
from dataclasses import replace
import json

import pytest

from app.repositories import task_leases
from app.repositories.sqlite import connect
from app.services.ai.client import ModelTimeoutError
from app.services.ai.entities import EntityExtractor
from app.services.ai.extraction_windows import WindowPolicy
from app.services.ai.fake import FakeModelClient
from app.services.ai.relations import RelationExtractor
from app.services.fusion.resolution import SemanticResolver
from app.workers.extract_task import ExtractionToolkit, ExtractLimits, ExtractStatus, run_extract_stage
from app.workers.extraction.types import _Halt
from tests.backend.test_disambiguation_generation import different, entities
from tests.backend.test_e12 import _extracting, _policy, storage


def kit(db_url, client):
    return ExtractionToolkit(
        policy=_policy(db_url, client, failure_threshold=1),
        entities=lambda c: EntityExtractor(c, model='m', max_output_tokens=2048),
        relations=lambda c: RelationExtractor(c, model='m', max_output_tokens=256),
        resolver=lambda c: SemanticResolver(c, model='m'),
        preserve_mentions=True, local_normalization=True,
        window_policy=WindowPolicy(max_input_bytes=16000),
    )


def response(request):
    if request.purpose == 'extract_entities':
        text = request.messages[0].content.split('资料块：\n', 1)[1].strip()
        return json.dumps({'entities': [dict(name='概念'+name, type='concept', definition='定义'+name,
                                            evidence=text, evidence_start=0) for name in '甲乙丙']}, ensure_ascii=False)
    if request.purpose == 'resolve_duplicate':
        return different(request)
    return '{"relations":[]}'


def test_relation_fault_reclaim_uses_completed_pair_results_without_model_replay(db_url, storage):
    lease, _ = _extracting(db_url, storage, '原文说明三个不同概念。'.encode())
    def fail_relation(request):
        if request.purpose == 'extract_normalized_relations':
            raise ModelTimeoutError('m')
        return response(request)
    first = FakeModelClient(responder=fail_relation)
    out = run_extract_stage(db_url, lease, toolkit=kit(db_url, first), limits=ExtractLimits(max_attempts=3))
    assert out.status == ExtractStatus.RELEASED, (out, [c.request.purpose for c in first.calls])
    assert sum(c.request.purpose == 'resolve_duplicate' for c in first.calls) == 3
    with connect(db_url) as db:
        db.execute('UPDATE processing_tasks SET not_before=0 WHERE id=?', (lease.task_id,))
    claimed = task_leases.claim_next(db_url, owner='replacement', lease_seconds=60, max_attempts=3)
    assert claimed and claimed.attempt == 2
    second = FakeModelClient(responder=response)
    out = run_extract_stage(db_url, claimed, toolkit=kit(db_url, second), limits=ExtractLimits(max_attempts=3))
    assert out.status == ExtractStatus.ADVANCED
    assert [c.request.purpose for c in second.calls] == ['extract_normalized_relations']
    with connect(db_url) as db:
        assert db.execute('SELECT count(*) FROM task_section_decisions WHERE task_id=?', (lease.task_id,)).fetchone()[0] == 3


@pytest.mark.parametrize('condition,reason', [('cancel', 'cancel'), ('token', 'lost'), ('expired', 'lost'),
                                              ('stage', 'lost'), ('course', 'lost')])
def test_cached_reads_and_writes_obey_cancellation_and_lease_scope(db_url, storage, condition, reason):
    from app.workers.extraction.decision_cache import SectionDecisionCache
    from app.workers.extraction.analysis import analyze_section
    lease, _ = _extracting(db_url, storage)
    nodes, chunks = entities(2)
    cache = SectionDecisionCache(db_url, lease, 'section')
    report = analyze_section(nodes, chunks, resolver=SemanticResolver(FakeModelClient(responder=different), model='m'),
                             max_pairs=1, cache=cache)
    decision = report['decisions'][0]
    with connect(db_url) as db:
        if condition == 'cancel': db.execute('UPDATE processing_tasks SET cancel_requested=1 WHERE id=?', (lease.task_id,))
        elif condition == 'token': db.execute('UPDATE processing_tasks SET lease_token=? WHERE id=?', ('n' * 32, lease.task_id))
        elif condition == 'expired': db.execute('UPDATE processing_tasks SET lease_expires_at=0 WHERE id=?', (lease.task_id,))
        elif condition == 'stage': db.execute("UPDATE processing_tasks SET stage='merging' WHERE id=?", (lease.task_id,))
    if condition == 'course': cache = SectionDecisionCache(db_url, replace(lease, course_id='other'), 'section')
    operations = [lambda: cache.get(report['input_digest'], 'e0', 'e1')]
    if condition != 'cancel':
        operations.append(lambda: cache.put('new-digest', decision))
    for operation in operations:
        with pytest.raises(_Halt) as caught:
            operation()
        assert caught.value.reason == reason
    with connect(db_url) as db:
        assert db.execute('SELECT count(*) FROM task_section_decisions').fetchone()[0] == 1
    if condition == 'cancel':
        # A complete result from an already-issued request may be retained for explicit resume.
        cache.put('new-digest', decision)
        with connect(db_url) as db:
            assert db.execute('SELECT count(*) FROM task_section_decisions').fetchone()[0] == 2
