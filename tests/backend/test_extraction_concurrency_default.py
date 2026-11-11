"""Default/override concurrency must control actual in-flight model requests."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
import test_e12 as e12
from test_extraction_perf_scheduler import CaptureScript
from app.config import load_settings
from app.workers.extract_task import ExtractLimits, ExtractStatus, run_extract_stage


storage = e12.storage


@pytest.mark.parametrize('environment, expected', [({}, 8), ({'LLM_MAX_CONCURRENCY': '2'}, 2)],
                         ids=['default-eight', 'environment-override'])
def test_configured_pool_fills_and_bounds_actual_calls(db_url, storage, environment, expected):
    lease, chunks = e12._extracting(db_url, storage)
    script = CaptureScript()
    full, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    started = 0

    def hold_first_wave(_attempt):
        nonlocal started
        with lock:
            started += 1
            if started == expected:
                full.set()
        assert release.wait(10), 'test did not release the model requests'

    for index in range(len(chunks)):
        script.hooks[e12._key(chunks, index)] = hold_first_wave
    limits = ExtractLimits.from_settings(load_settings(environment))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_extract_stage, db_url, lease,
                                 toolkit=e12._toolkit(db_url, script), limits=limits)
        try:
            assert full.wait(5), 'configured concurrency did not fill the first wave'
            assert script.active == expected
            assert len(script.calls) == expected
        finally:
            release.set()
        outcome = future.result(10)
    assert outcome.status is ExtractStatus.ADVANCED
    assert script.peak == expected
    assert len(script.calls) == 12
    assert e12._sql(db_url, 'SELECT COUNT(*), SUM(usage_input + usage_output) FROM model_calls '
                    'WHERE task_id = ? AND status = ?', lease.task_id, 'ok') == [(12, 60)]
