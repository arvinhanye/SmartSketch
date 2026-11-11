"""EXTRACT-PERF-01 measurement accounting and isolation (no Docker required)."""

from __future__ import annotations

import importlib.util
import logging
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("measure_extraction_perf", ROOT / "evaluation/measure_extraction_perf.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)


def test_interval_union_does_not_add_parallel_model_time():
    assert measure.interval_union([(3, 8), (1, 5), (8, 10), (12, 13)]) == 10
    assert measure.interval_union([]) == 0


def test_purpose_timings_distinguish_span_active_time_and_sum():
    calls = [{"purpose": "extract_entities", "started_seconds": start, "ended_seconds": end}
             for start, end in [(0, 8), (0, 8), (10, 18)]]
    result = measure.purpose_timings(calls)["extract_entities"]
    assert result["span_seconds"] == 18
    assert result["active_wall_seconds"] == 16
    assert result["summed_seconds"] == 24


def test_graph_fingerprint_ignores_random_ids_but_detects_source_and_semantic_change():
    def snapshot(suffix, *, definition="definition", evidence_end=4):
        node = {"kp_id": "kp-" + suffix, "name": "栈", "type": "concept", "definition": definition,
                "confidence": 0.9, "status": "draft", "aliases": ["stack"]}
        chunk_id = "chunk-" + suffix
        edge = {"from_name": "栈", "from_type": "concept", "to_name": "队列", "to_type": "concept",
                "type": "RELATED_TO", "confidence": 0.8, "status": "draft", "source": "ai",
                "source_pairs": ['["task-' + suffix + '","' + chunk_id + '"]']}
        evidence = {"kp_id": node["kp_id"], "chunk_id": chunk_id, "evidence_start": 0,
                    "evidence_end": evidence_end}
        return measure.normalize_graph([node], [edge], [evidence], {chunk_id: {"ordinal": 1}})

    assert snapshot("one") == snapshot("two")
    assert snapshot("one")["sha256"] != snapshot("one", definition="changed")["sha256"]
    assert snapshot("one")["sha256"] != snapshot("one", evidence_end=5)["sha256"]


def test_parse_persist_steps_preserves_overlapping_t6_without_summing():
    result = measure.parse_worker_log(
        "persist steps task_id=t1 outcome=advanced candidates_ms=2 neo4j_ms=300 t6_ms=9 "
        "neo4j_attempts=1 total_ms=320", 15.0)
    assert result == {"kind": "persist_steps", "at_seconds": 15.0, "task_id": "t1",
                      "outcome": "advanced", "candidates_ms": 2, "neo4j_ms": 300,
                      "t6_ms": 9, "neo4j_attempts": 1, "total_ms": 320}
    assert measure.parse_worker_log("irrelevant log", 0) is None


def test_stage_log_has_millisecond_precision_handoff_bounds():
    result = measure.parse_worker_log(
        "task stage done task_id=t stage=extracting status=advanced duration_ms=8001", 10.0)
    assert result["started_seconds"] == pytest.approx(1.999)
    assert result["ended_seconds"] == 10.0
    assert result["duration_ms"] == 8001


def test_queue_time_uses_dependency_checkpoint_not_all_chunks_barrier():
    units = [
        {"kind": "chunk", "unit_id": "a", "started_seconds": 1.0, "ended_seconds": 9.0},
        {"kind": "chunk", "unit_id": "b", "started_seconds": 9.1, "ended_seconds": 17.1},
        {"kind": "section", "unit_id": "s", "chunk_ids": ["a"],
         "started_seconds": 17.2, "ended_seconds": 25.2},
    ]
    checkpoints = [{"kind": "chunk", "unit_id": "a", "at_seconds": 9.05},
                   {"kind": "chunk", "unit_id": "b", "at_seconds": 17.15}]
    measure.add_queue_times(units, checkpoints, chunks_ready=0.9)
    assert units[0]["queue_wait_seconds"] == pytest.approx(0.1)
    assert units[2]["ready_seconds"] == 9.05
    assert units[2]["queue_wait_seconds"] == pytest.approx(8.15)


def test_unobserved_checkpoint_is_unknown_not_zero():
    units = [{"kind": "section", "unit_id": "s", "chunk_ids": ["missing"],
              "started_seconds": 5, "ended_seconds": 6}]
    measure.add_queue_times(units, [], chunks_ready=0)
    assert units[0]["ready_seconds"] is None
    assert units[0]["queue_wait_seconds"] is None


def test_isolated_settings_ignore_inherited_paid_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://paid.example/v1")
    monkeypatch.setenv("EMBEDDING_MODE", "online")
    monkeypatch.setenv("SQLITE_URL", "sqlite:////production/state.sqlite3")
    env = measure.isolated_environment(tmp_path, "bolt://127.0.0.1:12345", "test-password", concurrency=4,
                                       delay_seconds=8)
    assert env["LLM_MODE"] == "personal" and env["EMBEDDING_MODE"] == "demo"
    assert "LLM_BASE_URL" not in env and "EMBEDDING_BASE_URL" not in env
    assert env["SQLITE_URL"] == f"sqlite:///{tmp_path / 'state.sqlite3'}"
    assert env["FAKE_PROVIDER_SLOW_SECONDS"] == "8"


def test_log_capture_filters_secrets_and_other_logger_messages():
    trace = measure.Trace()
    trace.origin = 0
    trace.emit(logging.LogRecord("unrelated", logging.INFO, "", 0, "secret-password", (), None))
    assert trace.logs == []


def test_logger_handle_does_not_deadlock_on_trace_data_lock():
    trace = measure.Trace()
    record = logging.LogRecord("app.workers.persist_graph", logging.INFO, "", 0,
                               "task stage done task_id=t stage=parsing status=advanced duration_ms=1", (), None)
    worker = threading.Thread(target=trace.handle, args=(record,), daemon=True)
    worker.start()
    worker.join(1)
    assert not worker.is_alive()
    assert trace.logs[0]["stage"] == "parsing"


def test_cli_rejects_nonfinite_or_out_of_range_delay_and_concurrency():
    parser = measure.build_parser()
    for arguments in (["--delay-seconds", "nan"], ["--delay-seconds", "121"],
                      ["--delay-seconds", "-1"], ["--concurrency", "0"]):
        with pytest.raises(SystemExit):
            parser.parse_args(arguments)


def test_warm_repeat_retains_imported_source_identity_without_rereading_disk(monkeypatch):
    monkeypatch.setattr(measure, "_IMPORTED_BASELINE", None)
    baseline = measure.capture_runtime()

    def changed_disk(path):
        raise AssertionError("warm repeat must not re-identify already imported code from changed disk")

    monkeypatch.setattr(Path, "read_bytes", changed_disk)
    assert measure.capture_runtime() == baseline
