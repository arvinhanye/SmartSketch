"""Cancel stops new work but retains complete, leased results for explicit continuation."""
from dataclasses import replace
import threading

import pytest

from app.repositories.sqlite import connect
from app.repositories.task_leases import LeaseLost
from app.services.ai.fake import FakeModelClient
from app.workers.extract_task import ExtractLimits, ExtractStatus, run_extract_stage
from app.workers.extraction.state import _write_unit
from app.workers.extraction.dispatch import _Dispatcher
from app.workers.extraction.types import _UnitResult
from tests.backend.test_e12 import _extracting, storage
from tests.backend.test_section_decision_worker import kit, response


@pytest.mark.parametrize('purpose,chunks,pairs,sections,calls', [
    ('extract_entities', 1, 0, 0, 1),
    ('resolve_duplicate', 1, 1, 0, 2),
    ('extract_normalized_relations', 1, 3, 1, 5),
])
def test_cancellation_during_request_preserves_complete_result_without_next_call(
    db_url, storage, purpose, chunks, pairs, sections, calls,
):
    lease, _ = _extracting(db_url, storage, '原文说明三个不同概念。'.encode())
    def cancel_then_respond(request):
        if request.purpose == purpose:
            with connect(db_url) as db:
                db.execute('UPDATE processing_tasks SET cancel_requested=1 WHERE id=?', (lease.task_id,))
        return response(request)
    client = FakeModelClient(responder=cancel_then_respond)
    outcome = run_extract_stage(db_url, lease, toolkit=kit(db_url, client),
                                limits=ExtractLimits(max_attempts=3, max_concurrency=1))
    assert outcome.status == ExtractStatus.CANCELLED
    assert len(client.calls) == calls  # No new request after cancellation, including SAME's second phase.
    with connect(db_url) as db:
        assert db.execute("SELECT count(*) FROM task_chunk_checkpoints WHERE task_id=? AND unit_kind='chunk' AND status='done'", (lease.task_id,)).fetchone()[0] == chunks
        assert db.execute('SELECT count(*) FROM task_section_decisions WHERE task_id=?', (lease.task_id,)).fetchone()[0] == pairs
        assert db.execute("SELECT count(*) FROM task_chunk_checkpoints WHERE task_id=? AND unit_kind='section' AND status='done'", (lease.task_id,)).fetchone()[0] == sections
        row = db.execute('SELECT stage,lease_token,cancel_requested FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone()
        assert tuple(row) == ('cancelled', None, 1)


@pytest.mark.parametrize('change', ['expired', 'token', 'course', 'terminal'])
def test_cancelled_success_checkpoint_rejects_lost_or_wrong_scope(db_url, storage, change):
    lease, _ = _extracting(db_url, storage)
    with connect(db_url) as db:
        db.execute('UPDATE processing_tasks SET cancel_requested=1 WHERE id=?', (lease.task_id,))
        if change == 'expired':
            db.execute('UPDATE processing_tasks SET lease_expires_at=0 WHERE id=?', (lease.task_id,))
        if change == 'token':
            db.execute('UPDATE processing_tasks SET lease_token=? WHERE id=?', ('n' * 32, lease.task_id))
        if change == 'terminal':
            db.execute("UPDATE processing_tasks SET stage='cancelled',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL WHERE id=?", (lease.task_id,))
    if change == 'course':
        lease = replace(lease, course_id='other')
    with pytest.raises(LeaseLost):
        _write_unit(db_url, lease, 'section', 'section', _UnitResult('done', 1, None, {'relations': []}), .6)
    with connect(db_url) as db:
        assert db.execute('SELECT count(*) FROM task_chunk_checkpoints').fetchone()[0] == 0


def test_cancel_drains_other_inflight_complete_sections_into_checkpoints(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    first_saved = threading.Event()
    units = iter(['first', 'second'])
    def work(unit):
        if unit == 'first':
            with connect(db_url) as db:
                db.execute('UPDATE processing_tasks SET cancel_requested=1 WHERE id=?', (lease.task_id,))
        else:
            assert first_saved.wait(5)
        return _UnitResult('done', 1, None, {'relations': []})
    def write(unit, result):
        keep_running = _write_unit(db_url, lease, 'section', unit, result, .6)
        if unit == 'first':
            first_saved.set()
        return keep_running
    outcome = _Dispatcher(lambda: next(units, None), limit=2, work=work, write=write,
                          after_write=lambda *_: False, order=lambda value: value).run()
    assert outcome == 'cancel'
    with connect(db_url) as db:
        saved = {r[0] for r in db.execute("SELECT unit_id FROM task_chunk_checkpoints WHERE unit_kind='section'")}
        assert saved == {'first', 'second'}
        assert db.execute('SELECT progress FROM processing_tasks WHERE id=?', (lease.task_id,)).fetchone()[0] == .1


def test_legacy_extraction_does_not_start_repair_after_cancel(db_url, storage):
    from app.services.task_cancel import cancel_task
    from tests.backend.test_e12 import Script, _run, _toolkit
    lease, _ = _extracting(db_url, storage, '概念11是第1章的第1个知识点。'.encode())
    normal = Script()
    observed = []
    def cancel_with_bad_output(request):
        observed.append(request.purpose)
        if len(observed) == 1:
            cancel_task(db_url, lease.task_id, course_id=lease.course_id)
            return '{'
        return normal(request)
    outcome = _run(db_url, lease, _toolkit(db_url, cancel_with_bad_output))
    assert outcome.status == ExtractStatus.CANCELLED
    assert observed == ['extract_entities']
