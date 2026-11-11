"""EXTRACT-PERF-01: conservative overlap, with real checkpoints and local model doubles.

The tail block is held by Events, never sleeps. A ready section may overlap only
after even every unfinished block failing would remain within the threshold.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

import test_e12 as e12
from app.services.ai.client import ModelAuthError, ModelRateLimitedError, Usage
from app.services.ai.fake import BAD_JSON_TEXT, FakeReply
from app.services.credentials import CredentialUnavailable
from app.workers import extract_task
from app.workers.extraction import dispatch

# Import fixtures, not the test functions, from the established E12 harness.
storage = e12.storage
WAIT = 2


class CaptureScript(e12.Script):
    def __init__(self):
        super().__init__()
        self.requests = []

    def __call__(self, request):
        with self.lock:
            self.requests.append(request)
        reply = super().__call__(request)
        return FakeReply(text=reply, usage=Usage(2, 3)) if isinstance(reply, str) else reply


@contextmanager
def running(db_url, lease, toolkit, *release_events, **limits):
    """Always unblock calls before joining, including an expected red assertion."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(e12._run, db_url, lease, toolkit, **limits)
        try:
            yield future
        finally:
            for event in release_events:
                event.set()


def hold(event, started=None, *, outcome=None):
    def hook(_attempt):
        if started is not None:
            started.set()
        assert event.wait(5), "test did not release the model call"
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    return hook


def tail_case(db_url, storage):
    lease, chunks = e12._extracting(db_url, storage)
    script = CaptureScript()
    tail_started, release_tail = threading.Event(), threading.Event()
    script.hooks[e12._key(chunks, 9)] = hold(release_tail, tail_started)
    return lease, chunks, script, tail_started, release_tail


def observe_writes(monkeypatch, observer):
    real = dispatch._write_unit

    def write(*args, **kwargs):
        try:
            written = real(*args, **kwargs)
        except e12.task_leases.LeaseLost:
            observer(args[2], args[3], "lost")
            raise
        observer(args[2], args[3], "written" if written else "cancel")
        return written

    monkeypatch.setattr(dispatch, "_write_unit", write)


@pytest.mark.parametrize("overlap", [False, True], ids=["baseline", "overlap"])
def test_ready_section_overlaps_safe_tail_and_all_calls_are_accounted(db_url, storage, overlap):
    """A global chunk barrier prevents this overlap; a second pool exceeds the cap."""
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    section_started = threading.Event()
    script.hooks["sec:" + chunks[0]] = lambda _n: section_started.set()
    if not overlap:
        release_tail.set()

    with running(db_url, lease, e12._toolkit(db_url, script), release_tail,
                 max_concurrency=2) as future:
        assert tail_started.wait(WAIT)
        assert section_started.wait(WAIT), "ready section stayed behind the global chunk barrier"
        if overlap:
            assert not future.done()
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is e12.ExtractStatus.ADVANCED
    assert script.peak <= 2
    assert len(script.calls) == 12
    assert e12._sql(db_url, "SELECT COUNT(*), SUM(usage_input + usage_output) FROM model_calls "
                    "WHERE task_id = ? AND status = 'ok'", lease.task_id) == [(12, 60)]


def test_unsafe_tail_does_not_start_sections_before_early_threshold_failure(db_url, storage, monkeypatch):
    """Nine settled chunks include two failures; the remaining failure is unsafe."""
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    for index in (6, 7):
        script.hooks[e12._key(chunks, index)] = lambda _n: BAD_JSON_TEXT
    script.hooks[e12._key(chunks, 9)] = hold(release_tail, tail_started, outcome=BAD_JSON_TEXT)
    settled = set()
    nine_settled = threading.Event()

    def observe(kind, unit, status):
        if kind == "chunk" and status == "written":
            settled.add(unit)
            if len(settled) == 9:
                nine_settled.set()

    observe_writes(monkeypatch, observe)
    with running(db_url, lease, e12._toolkit(db_url, script), release_tail,
                 max_concurrency=2, chunk_max_attempts=1) as future:
        assert tail_started.wait(WAIT) and nine_settled.wait(WAIT)
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is e12.ExtractStatus.FAILED
    assert outcome.chunks_failed == 3
    assert not any(key.startswith("sec:") for _, key in script.calls)
    assert e12._checkpoints(db_url, lease.task_id, "section") == {}


def test_threshold_halt_drops_late_result_and_never_dispatches_remaining_blocks(db_url, storage, monkeypatch):
    lease, chunks = e12._extracting(db_url, storage)
    script = CaptureScript()
    second_started, release_second, halted = (threading.Event() for _ in range(3))
    script.hooks[e12._key(chunks, 0)] = lambda _n: BAD_JSON_TEXT
    script.hooks[e12._key(chunks, 1)] = hold(release_second, second_started)
    real_settle = extract_task._Dispatcher._settle

    def settle(dispatcher, unit, future):
        real_settle(dispatcher, unit, future)
        if dispatcher.halt == "threshold":
            halted.set()

    monkeypatch.setattr(extract_task._Dispatcher, "_settle", settle)
    with running(db_url, lease, e12._toolkit(db_url, script), release_second,
                 max_concurrency=2, max_failed_ratio=0, chunk_max_attempts=1) as future:
        assert second_started.wait(WAIT) and halted.wait(WAIT)
        release_second.set()
        outcome = future.result(5)

    assert outcome.status is e12.ExtractStatus.FAILED and outcome.chunks_failed == 1
    assert set(e12._checkpoints(db_url, lease.task_id)) == {chunks[0]}
    assert {key for _, key in script.calls} == {e12._key(chunks, 0), e12._key(chunks, 1)}
    assert e12._checkpoints(db_url, lease.task_id, "section") == {}


@pytest.mark.parametrize("stop", ["cancel", "lost"])
def test_mixed_inflight_results_are_discarded_after_cancel_or_lease_loss(db_url, storage, monkeypatch, stop):
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    section_started, release_section, observed = (threading.Event() for _ in range(3))
    script.hooks["sec:" + chunks[0]] = hold(release_section, section_started)
    observe_writes(monkeypatch, lambda _kind, _unit, status: observed.set() if status == stop else None)

    with running(db_url, lease, e12._toolkit(db_url, script), release_tail, release_section,
                 max_concurrency=2) as future:
        assert tail_started.wait(WAIT)
        assert section_started.wait(WAIT), "test requires one block and one section in flight"
        before = e12._checkpoints(db_url, lease.task_id)
        if stop == "cancel":
            e12._sql(db_url, "UPDATE processing_tasks SET cancel_requested = 1 WHERE id = ?", lease.task_id)
        else:
            e12._sql(db_url, "UPDATE processing_tasks SET lease_token = ? WHERE id = ?", "f" * 32, lease.task_id)
        release_section.set()
        assert observed.wait(WAIT)
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is (e12.ExtractStatus.CANCELLED if stop == "cancel" else e12.ExtractStatus.LOST)
    assert e12._checkpoints(db_url, lease.task_id) == before
    assert e12._checkpoints(db_url, lease.task_id, "section") == {}
    assert [key for _, key in script.calls if key.startswith("sec:")] == ["sec:" + chunks[0]]


def test_takeover_skips_both_early_section_and_completed_chunks(db_url, storage, monkeypatch):
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    section_written = threading.Event()
    script.hooks[e12._key(chunks, 9)] = hold(release_tail, tail_started, outcome=e12._Crash())
    observe_writes(monkeypatch, lambda kind, _unit, status:
                   section_written.set() if kind == "section" and status == "written" else None)

    with running(db_url, lease, e12._toolkit(db_url, script), release_tail,
                 max_concurrency=2) as future:
        assert tail_started.wait(WAIT)
        assert section_written.wait(WAIT), "ready section was not checkpointed while the tail was in flight"
        progress = e12._row(db_url, lease.task_id)["progress"]
        release_tail.set()
        with pytest.raises(e12._Crash):
            future.result(5)

    assert len(e12._checkpoints(db_url, lease.task_id)) == 9
    assert len(e12._checkpoints(db_url, lease.task_id, "section")) == 1
    e12._sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", lease.task_id)
    takeover = e12._claim(db_url, "worker-b")
    resumed = CaptureScript()
    outcome = e12._run(db_url, takeover, e12._toolkit(db_url, resumed), max_concurrency=2)

    assert outcome.status is e12.ExtractStatus.ADVANCED
    assert [key for _, key in resumed.calls] == [e12._key(chunks, 9), "sec:" + chunks[5]]
    assert e12._row(db_url, lease.task_id)["progress"] >= progress


def test_revoked_credential_stops_ready_section_before_sending_a_request(db_url, storage, monkeypatch):
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    rejected, section_ready, enter_section, revoked = (threading.Event() for _ in range(4))
    extract_section = dispatch._extract_section

    def ready_section(*args, **kwargs):
        section_ready.set()
        assert enter_section.wait(5), "test did not release the section attempt"
        return extract_section(*args, **kwargs)

    monkeypatch.setattr(dispatch, "_extract_section", ready_section)

    def guard():
        if revoked.is_set():
            rejected.set()
            raise CredentialUnavailable("credential_revoked")

    toolkit = dataclasses.replace(e12._toolkit(db_url, script), guard=guard)
    with running(db_url, lease, toolkit, release_tail, enter_section, max_concurrency=2) as future:
        assert tail_started.wait(WAIT)
        assert section_ready.wait(WAIT), "ready section stayed behind the global chunk barrier"
        revoked.set()
        enter_section.set()
        assert rejected.wait(WAIT), "credential guard was not checked for the ready section"
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is e12.ExtractStatus.FAILED
    assert json.loads(e12._row(db_url, lease.task_id)["error_details"]) == {"reason": "credential_revoked"}
    assert len(script.calls) == 10
    assert e12._checkpoints(db_url, lease.task_id, "section") == {}


@pytest.mark.parametrize("fault", ["auth", "circuit"])
def test_section_fault_stops_dispatch_and_settles_inflight_by_existing_rules(db_url, storage, monkeypatch, fault):
    """Auth discards late success; a 429-opened breaker keeps it before release."""
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    halted = threading.Event()
    real_settle = extract_task._Dispatcher._settle

    def settle(dispatcher, unit, future):
        real_settle(dispatcher, unit, future)
        if dispatcher.halt == fault:
            halted.set()

    monkeypatch.setattr(extract_task._Dispatcher, "_settle", settle)
    error = ModelAuthError(e12.MODEL) if fault == "auth" else ModelRateLimitedError(e12.MODEL)
    script.hooks["sec:" + chunks[0]] = lambda _n: error
    toolkit = e12._toolkit(db_url, script, failure_threshold=1)
    with running(db_url, lease, toolkit, release_tail, max_concurrency=2) as future:
        assert tail_started.wait(WAIT)
        assert halted.wait(WAIT), "ready section fault was not observed before the tail finished"
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is (e12.ExtractStatus.FAILED if fault == "auth" else e12.ExtractStatus.RELEASED)
    assert (chunks[9] in e12._checkpoints(db_url, lease.task_id)) is (fault == "circuit")
    assert e12._checkpoints(db_url, lease.task_id, "section") == {}
    assert [key for _, key in script.calls if key.startswith("sec:")] == ["sec:" + chunks[0]]
    if fault == "auth":
        assert json.loads(e12._row(db_url, lease.task_id)["error_details"]) == {"reason": "auth"}
    else:
        assert outcome.chunks_failed == 0
        assert e12._row(db_url, lease.task_id)["not_before"] is not None


def test_relation_429_retries_inside_the_shared_limit_and_records_each_attempt(db_url, storage, monkeypatch):
    lease, chunks, script, tail_started, release_tail = tail_case(db_url, storage)
    section_written = threading.Event()
    script.hooks["sec:" + chunks[0]] = lambda n: ModelRateLimitedError(e12.MODEL) if n == 1 else None
    observe_writes(monkeypatch, lambda kind, _unit, status:
                   section_written.set() if kind == "section" and status == "written" else None)
    with running(db_url, lease, e12._toolkit(db_url, script, max_retries=1), release_tail,
                 max_concurrency=2) as future:
        assert tail_started.wait(WAIT)
        assert section_written.wait(WAIT), "ready section retry did not finish during the slow tail"
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is e12.ExtractStatus.ADVANCED
    assert script.count("sec:" + chunks[0]) == 2 and script.peak <= 2
    assert e12._sql(db_url, "SELECT status, COUNT(*) FROM model_calls WHERE task_id = ? "
                    "GROUP BY status ORDER BY status", lease.task_id) == [("error", 1), ("ok", 12)]


@pytest.mark.parametrize("overlap", [False, True], ids=["baseline", "overlap"])
def test_section_inputs_keep_document_order_with_failed_and_shared_entities(db_url, storage, overlap):
    """Completion order must not replace document order or include failed blocks."""
    data = e12._material_text().replace("学习概念22之前需要先掌握概念21".encode(),
                                      "学习概念22之前需要先掌握概念11".encode())
    lease, chunks = e12._extracting(db_url, storage, data)
    script = CaptureScript()
    release_tail, tail_started, section_started = (threading.Event() for _ in range(3))
    script.hooks[e12._key(chunks, 0)] = lambda _n: BAD_JSON_TEXT
    script.hooks[e12._key(chunks, 9)] = hold(release_tail, tail_started)
    script.hooks["sec:" + chunks[1]] = lambda _n: section_started.set()
    if not overlap:
        release_tail.set()
    with running(db_url, lease, e12._toolkit(db_url, script), release_tail,
                 max_concurrency=2, chunk_max_attempts=1) as future:
        assert tail_started.wait(WAIT)
        assert section_started.wait(WAIT), "one failed plus one unfinished block is threshold-safe"
        release_tail.set()
        outcome = future.result(5)

    assert outcome.status is e12.ExtractStatus.ADVANCED and outcome.chunks_failed == 1
    requests = [request for request in script.requests if request.purpose == "extract_relations"]
    requests.sort(key=lambda request: e12._CHUNK_HEAD.findall(request.messages[0].content)[0])
    assert len(requests) == 2
    expected_names = [["概念12", "概念11", "概念13", "概念14", "概念15"],
                      ["概念21", "概念22", "概念11", "概念23", "概念24", "概念25"]]
    expected_chunks = [list(chunks[1:5]), list(chunks[5:])]
    for request, names, members in zip(requests, expected_names, expected_chunks):
        prompt = request.messages[0].content
        rows = [json.loads(line.strip().rstrip(",")) for line in prompt.splitlines()
                if line.strip().startswith('{"id"')]
        assert [row["name"] for row in rows] == names
        assert [row["type"] for row in rows] == ["concept"] * len(names)
        assert e12._CHUNK_HEAD.findall(prompt) == members
    shared = [json.loads(line.strip().rstrip(","))["id"] for request in requests
              for line in request.messages[0].content.splitlines()
              if line.strip().startswith('{"id"') and '"name": "概念11"' in line]
    assert len(shared) == 2 and shared[0] == shared[1]


def test_measurement_observes_split_worker_units_and_checkpoints(db_url, storage):
    """OPT-06 must not silently detach timing probes from the actual worker."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "evaluation/measure_extraction_perf.py"
    spec = importlib.util.spec_from_file_location("extraction_perf_trace_regression", path)
    measure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(measure)
    lease, _chunks = e12._extracting(db_url, storage)
    trace = measure.Trace()
    with trace.observe_units():
        outcome = e12._run(db_url, lease, e12._toolkit(db_url, CaptureScript()))
    assert outcome.status is e12.ExtractStatus.ADVANCED
    assert len(trace.units) == 12
    assert sum(unit["kind"] == "chunk" for unit in trace.units) == 10
    assert sum(unit["kind"] == "section" for unit in trace.units) == 2
    assert len(trace.checkpoints) == 12
    assert all(unit["ended_seconds"] >= unit["started_seconds"] for unit in trace.units)
    identity = measure.capture_runtime()["source_sha256"]
    assert "src/backend/app/workers/extraction/dispatch.py" in identity
    assert "src/backend/app/workers/extraction/types.py" in identity
