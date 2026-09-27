"""K04's fake benchmark must measure the successful extraction path."""

from app.config import Settings
from app.services.ai.client import Message, ModelRequest
from app.services.ai.entities import ENTITY_PROMPT_PURPOSE
from evaluation.benchmark_pipeline import build_toolkit


def test_fake_benchmark_client_returns_extractable_entities() -> None:
    toolkit = build_toolkit(Settings())
    client = toolkit.policy._primary.client
    request = ModelRequest(
        purpose=ENTITY_PROMPT_PURPOSE,
        model="fake",
        messages=(Message("user", "第3章 栈与队列 > 3.2 栈 > 第1段\n栈是一种线性表。"),),
        max_output_tokens=4096,
        response_format="json",
    )

    entities = client.complete(request).json()["entities"]

    assert any(entity["name"] == "栈" for entity in entities)


# --- report shape, SQL against the migrated schema, SSE timing, paid guards ---

import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

import pytest  # noqa: E402

from app.repositories.sqlite import migrate  # noqa: E402
from evaluation import benchmark_pipeline as bench  # noqa: E402


@pytest.fixture
def sqlite_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'k04.sqlite3').as_posix()}"
    migrate(url)
    return url


def test_fixture_is_stable_markdown_of_about_twenty_thousand_characters() -> None:
    text = bench.fixture_text()
    assert text == bench.fixture_text()
    assert 19_000 <= len(text) <= bench.FIXTURE_CHARS + 1  # cut at the limit, plus a final newline
    assert text.lstrip().startswith("# 性能样本 1") and text.endswith("\n")


def test_percentiles_interpolate_and_empty_is_null() -> None:
    assert bench.percentile([], 0.5) is None
    assert bench.percentile([7.0], 0.95) == 7.0
    assert bench.percentile([40, 10, 30, 20], 0.5) == 25.0
    assert bench.percentile(list(range(1, 101)), 0.95) == 95.05


def test_queue_and_token_queries_run_on_the_real_schema(sqlite_url) -> None:
    assert bench.queued_fixture_count(sqlite_url) == 0
    assert bench.token_usage(sqlite_url, "task_id", "t") == {
        "calls": 0, "input": 0, "output": 0, "billed": 0, "estimated_calls": 0}
    with pytest.raises(ValueError):
        bench.token_usage(sqlite_url, "course_id", "c")


def _worker(ms, complete=True):
    return {"task_id": "t", "elapsed_ms": ms, "complete": complete,
            "stages": [{"stage": stage, "elapsed_ms": ms / 4, "tokens_billed": 0, "model_calls": 0}
                       for stage in bench.STAGES]}


def test_report_names_environment_and_separates_targets_from_measurements() -> None:
    qa = [{"elapsed_ms": 900.0, "first_token_ms": 300.0, "status": "answered"},
          {"elapsed_ms": 500.0, "first_token_ms": None, "status": "not_covered"}]
    report = bench.build_report(Settings(), [_worker(100.0), _worker(200.0)], qa)
    env = report["environment"]
    assert {"machine", "os", "python", "cpu", "model", "chat_model", "worker_processes",
            "llm_max_concurrency", "llm_mode"} <= env.keys()
    assert (env["llm_mode"], env["model"], env["chat_model"]) == ("fake", "fake", "fake")
    assert report["targets_ms"] == bench.TARGETS
    observed = report["observed"]
    assert observed["worker_samples"] == 2
    assert observed["worker_total_ms"] == {"count": 2, "p50": 150.0, "p95": 195.0}
    assert set(observed["stages_ms"]) == set(bench.STAGES)
    assert observed["qa_first_token_ms"] == {"count": 1, "p50": 300.0, "p95": 300.0}
    assert observed["qa_complete_ms"]["count"] == 2
    assert observed["qa_outcomes"] == {"answered": 1, "not_covered": 1}
    assert report["status"] == "measured"
    assert any("假模型" in note for note in report["notes"])
    assert bench.build_report(Settings(), [_worker(1.0, complete=False)], [])["status"] == "incomplete"
    assert bench.build_report(Settings(), [], [])["observed"]["worker_total_ms"]["p50"] is None


def _serve(events):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            Handler.seen = (self.path, self.headers["Accept"], self.headers["Authorization"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk, pause in events:
                time.sleep(pause)
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, Handler


def _sse(name, payload):
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


def test_sse_measurement_separates_first_token_from_completion(sqlite_url) -> None:
    server, handler = _serve([
        (_sse("meta", {"event": "meta", "request_id": "req-1"}), 0),
        (":ping\n\n", 0),
        (_sse("delta", {"event": "delta", "delta": "栈"}), 0.05),
        (_sse("delta", {"event": "delta", "delta": "是线性表"}), 0.3),
        (_sse("done", {"event": "done", "final": {"status": "answered", "request_id": "req-1"}}), 0.15),
    ])
    try:
        result = bench.measure_qa(sqlite_url, "course-1", f"http://127.0.0.1:{server.server_port}/", "tok")
    finally:
        server.shutdown()
    assert handler.seen == ("/api/v1/courses/course-1/chat", "text/event-stream", "Bearer tok")
    assert (result["status"], result["request_id"], result["error_code"]) == ("answered", "req-1", None)
    assert 40 <= result["first_token_ms"] < 300 < result["elapsed_ms"]
    assert result["elapsed_ms"] - result["first_token_ms"] >= 400
    assert result["tokens"]["calls"] == 0


def test_sse_error_and_missing_terminal_are_reported(sqlite_url) -> None:
    error = {"event": "error", "error": {"code": "LLM_UNAVAILABLE", "details": {"request_id": "req-2"}}}
    server, _ = _serve([(_sse("error", error), 0)])
    try:
        failed = bench.measure_qa(sqlite_url, "c", f"http://127.0.0.1:{server.server_port}", "tok")
    finally:
        server.shutdown()
    assert (failed["status"], failed["error_code"], failed["request_id"]) == ("error", "LLM_UNAVAILABLE", "req-2")
    assert failed["first_token_ms"] is None

    server, _ = _serve([(_sse("meta", {"event": "meta", "request_id": "req-3"}), 0)])
    try:
        cut = bench.measure_qa(sqlite_url, "c", f"http://127.0.0.1:{server.server_port}", "tok")
    finally:
        server.shutdown()
    assert (cut["status"], cut["request_id"]) == ("incomplete", "req-3")


@pytest.mark.parametrize("argv, env, message", [
    (["run", "--samples", "0"], {}, "--samples must be positive"),
    (["run", "--samples", "1", "--qa-samples", "1"], {}, "QA calls require --allow-paid"),
    (["run", "--samples", "1", "--qa-samples", "1", "--allow-paid"], {}, "QA requires --course-id"),
    (["run", "--samples", "1"], {"LLM_MODE": "live", "LLM_BASE_URL": "http://127.0.0.1:9/v1",
                                 "LLM_API_KEY": "not-a-real-key", "LLM_EXTRACTION_MODEL": "m",
                                 "LLM_CHAT_MODEL": "m"}, "live model calls require --allow-paid"),
    (["run", "--samples", "1"], {}, "upload one fresh K04 fixture"),
])
def test_run_refuses_paid_or_unprepared_runs_before_any_work(argv, env, message, sqlite_url, tmp_path,
                                                             monkeypatch, capsys) -> None:
    monkeypatch.setenv("SQLITE_URL", sqlite_url)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    out = tmp_path / "report.json"
    with pytest.raises(SystemExit) as exited:
        bench.main([*argv, "--out", str(out)])
    assert exited.value.code == 2
    assert message in capsys.readouterr().err
    assert not out.exists()


def test_fixture_command_writes_the_fixture(tmp_path) -> None:
    out = tmp_path / "fixture.md"
    assert bench.main(["fixture", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == bench.fixture_text()
