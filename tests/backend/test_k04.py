"""K04 SSE timing and report summaries."""

from io import BytesIO

from app.config import Settings
from evaluation import benchmark_pipeline


def _stream(monkeypatch, payload: str, ticks: list[int]) -> None:
    monkeypatch.setattr(benchmark_pipeline.urllib.request, "urlopen",
                        lambda *args, **kwargs: BytesIO(payload.encode("utf-8")))
    clock = iter(ticks)
    monkeypatch.setattr(benchmark_pipeline.time, "perf_counter_ns", lambda: next(clock))
    monkeypatch.setattr(benchmark_pipeline, "token_usage", lambda *args: {"calls": 1})


def test_qa_records_first_delta_and_done(monkeypatch) -> None:
    _stream(monkeypatch, (
        'event: meta\ndata: {"event":"meta","request_id":"req-1"}\n\n'
        'event: delta\ndata: {"event":"delta","delta":"栈"}\n\n'
        'event: done\ndata: {"event":"done","final":{"status":"answered",'
        '"request_id":"req-1"}}\n\n'
    ), [1_000_000, 11_000_000, 51_000_000])

    result = benchmark_pipeline.measure_qa("unused", "course", "http://localhost", "token")

    assert result["first_token_ms"] == 10
    assert result["elapsed_ms"] == 50
    assert result["complete"] is True
    assert result["request_id"] == "req-1"


def test_qa_records_error_terminal_without_first_token(monkeypatch) -> None:
    _stream(monkeypatch, (
        'event: meta\ndata: {"event":"meta","request_id":"req-2"}\n\n'
        'event: error\ndata: {"event":"error","error":{"code":"LLM_UNAVAILABLE",'
        '"details":{"request_id":"req-2","reason":"upstream"}}}\n\n'
    ), [1_000_000, 21_000_000])

    result = benchmark_pipeline.measure_qa("unused", "course", "http://localhost", "token")

    assert result["first_token_ms"] is None
    assert result["elapsed_ms"] == 20
    assert result["status"] == "LLM_UNAVAILABLE"
    assert result["complete"] is False


def test_report_calculates_first_token_and_complete_percentiles() -> None:
    qa = [{"complete": True, "first_token_ms": value, "elapsed_ms": value * 2}
          for value in (10, 20, 30, 40, 50)]
    workers = [{"complete": True, "stages": [], "elapsed_ms": 100}]

    report = benchmark_pipeline.build_report(Settings(), workers, qa)

    assert report["observed"]["qa_samples"] == 5
    assert report["observed"]["qa_first_token_ms"] == {"count": 5, "p50": 30, "p95": 48}
    assert report["observed"]["qa_complete_ms"] == {"count": 5, "p50": 60, "p95": 96}
    assert report["environment"]["llm_max_concurrency"] == Settings().LLM_MAX_CONCURRENCY
