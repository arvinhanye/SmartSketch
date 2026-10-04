"""C01（B-EVAL-01）：测量工具的关联、时间边界与预算分账，全部离线。

夹具由 `evaluation/raw/l15/codex-closeout-audit.json` 生成（L15 真实十题 + 1 次额外尝试、19 条调用），
复现第二阶段收尾审查指出的问题：错误响应的编号在 `details.request_id`；`18:16:00.314Z` 被字符串比较漏掉；
生成与向量混算；缺失 usage 不能当 0；工具 exit 0 不等于所有题答成功。
"""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("measure_web_flow", ROOT / "evaluation/measure_web_flow.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)

AUDIT = json.loads((ROOT / "evaluation/raw/l15/codex-closeout-audit.json").read_text(encoding="utf-8"))
STARTED = AUDIT["measurement_started_at"]          # 2026-10-03T18:16:00Z
ENDED = "2026-10-03T18:30:00Z"
FAILED_ID = AUDIT["evidence_corrections"]["failed_question_request_id"]

MODEL_CALLS_DDL = """
CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY NOT NULL, status TEXT NOT NULL, course_id TEXT NOT NULL, task_id TEXT,
    request_id TEXT, purpose TEXT NOT NULL, max_output_tokens INTEGER NOT NULL,
    usage_input INTEGER, usage_output INTEGER, created_at TEXT NOT NULL, finished_at TEXT, latency_ms INTEGER
)"""
CHAT_LOGS_DDL = """
CREATE TABLE chat_logs (
    request_id TEXT PRIMARY KEY NOT NULL, course_id TEXT NOT NULL, version_id TEXT NOT NULL, question TEXT NOT NULL,
    outcome TEXT NOT NULL, reason TEXT, error_code TEXT, error_reason TEXT, invalidation_subtype TEXT,
    truncated INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER NOT NULL, first_delta_latency_ms INTEGER,
    created_at TEXT NOT NULL
)"""


def _db(tmp_path: Path, *, extra_calls=(), extra_logs=()) -> Path:
    path = tmp_path / "measure.sqlite3"
    con = sqlite3.connect(path)
    con.execute(MODEL_CALLS_DDL)
    con.execute(CHAT_LOGS_DDL)
    for n, call in enumerate([*AUDIT["model_calls"], *extra_calls]):
        con.execute(
            "INSERT INTO model_calls (call_id, status, course_id, request_id, purpose, max_output_tokens,"
            " usage_input, usage_output, created_at, finished_at, latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"call-{n}", call["status"], "course", call["request_id"], call["purpose"], call["max_output_tokens"],
             call["usage_input"], call["usage_output"], call["created_at"], call.get("finished_at"), call.get("latency_ms")))
    for log in [*AUDIT["questions"], *AUDIT["extra_attempts"], *extra_logs]:
        con.execute(
            "INSERT INTO chat_logs (request_id, course_id, version_id, question, outcome, reason, error_code,"
            " error_reason, invalidation_subtype, truncated, latency_ms, first_delta_latency_ms, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (log["request_id"], log["course_id"], log["version_id"], log["question"], log["outcome"], log["reason"],
             log["error_code"], log["error_reason"], log["invalidation_subtype"], log["truncated"], log["latency_ms"],
             log["first_delta_latency_ms"], log["created_at"]))
    con.commit()
    con.close()
    return path


def _http_records() -> list[dict]:
    """十题的客户端记录（与 `ask` 写出的格式一致）：失败题是 HTTP 503 错误对象，编号在 details 里。"""
    records = []
    for q in AUDIT["questions"]:
        if q["outcome"] == "error":
            body = {"code": q["error_code"], "message": "回答过长被截断，已撤回。",
                    "details": {"reason": q["error_reason"], "request_id": q["request_id"]}}
        else:
            body = {"status": q["outcome"], "request_id": q["request_id"], "reason": q["reason"],
                    "latency_ms": q["latency_ms"], "citations": q.get("citations") or []}
        records.append(measure.normalize_ask_result(
            question=q["question"], course_id=q["course_id"], http_status=q["http_status"], body=body,
            client_elapsed_seconds=q["client_elapsed_seconds"]))
    return records


# ---------------------------------------------------------------- HTTP 结局与关联


def test_error_response_request_id_comes_from_details_and_fields_stay_separate():
    record = measure.normalize_ask_result(
        question="栈和队列有什么区别", course_id="c1", http_status=503,
        body={"code": "LLM_UNAVAILABLE", "message": "x", "details": {"reason": "truncated", "request_id": FAILED_ID}},
        client_elapsed_seconds=10.27)
    assert record["request_id"] == FAILED_ID
    assert record["outcome"] == "error"
    assert record["error_code"] == "LLM_UNAVAILABLE"
    assert record["error_reason"] == "truncated"
    assert record["reason"] is None


def test_answered_and_not_covered_keep_their_status_and_reason():
    answered = measure.normalize_ask_result(question="q", course_id="c1", http_status=200,
                                            body={"status": "answered", "request_id": "r1", "citations": [{}, {}]},
                                            client_elapsed_seconds=5.0)
    assert (answered["outcome"], answered["error_code"], answered["citations"]) == ("answered", None, 2)
    uncovered = measure.normalize_ask_result(question="q", course_id="c1", http_status=200,
                                             body={"status": "not_covered", "reason": "below_similarity_threshold",
                                                   "request_id": "r2"}, client_elapsed_seconds=0.4)
    assert (uncovered["outcome"], uncovered["reason"]) == ("not_covered", "below_similarity_threshold")


def test_no_response_is_its_own_outcome_without_request_id():
    record = measure.normalize_ask_result(question="q", course_id="c1", http_status=None, body=None,
                                          client_elapsed_seconds=60.0)
    assert record["outcome"] == "no_response" and record["request_id"] is None


# ---------------------------------------------------------------- 时间边界


def test_millisecond_timestamp_in_the_same_second_is_inside_the_window():
    # 字符串比较会把 .314Z 排在 Z 之前而漏掉（第二阶段 18 vs 19 调用的原因）
    assert not ("2026-10-03T18:16:00.314Z" >= STARTED)
    assert measure.in_window("2026-10-03T18:16:00.314Z", STARTED, ENDED)
    assert not measure.in_window("2026-10-03T18:15:59.999Z", STARTED, ENDED)
    assert not measure.in_window(ENDED, STARTED, ENDED)           # 结束边界开区间


def test_timestamps_without_timezone_are_rejected():
    with pytest.raises(ValueError):
        measure.parse_utc("2026-10-03T18:16:00")


# ---------------------------------------------------------------- 离线重算第二阶段真实测量


def test_offline_recount_matches_the_audited_ledger(tmp_path):
    report = measure.audit(_db(tmp_path), started_at=STARTED, ended_at=ENDED)
    assert report["requests"] == 11
    ledger = report["ledger"]
    assert ledger["generation"]["calls"] == 9
    assert ledger["generation"]["tokens"] == 28951
    assert ledger["generation"]["usage_input"] == 18764 and ledger["generation"]["usage_output"] == 10187
    assert ledger["embedding"]["calls"] == 10 and ledger["embedding"]["tokens"] == 59
    assert ledger["generation"]["unknown_usage_calls"] == 0
    assert report["window"] == {"started_at": STARTED, "ended_at": ENDED, "request_ids": None}


def test_later_calls_outside_the_end_boundary_do_not_pollute_the_round(tmp_path):
    later = {"request_id": "later-req", "purpose": "answer_with_context", "status": "ok", "max_output_tokens": 2048,
             "usage_input": 9999, "usage_output": 9999, "created_at": "2026-10-03T18:45:00.000Z"}
    report = measure.audit(_db(tmp_path, extra_calls=[later]), started_at=STARTED, ended_at=ENDED)
    assert report["ledger"]["generation"]["tokens"] == 28951


def test_fixed_request_ids_select_exactly_those_requests(tmp_path):
    report = measure.audit(_db(tmp_path), request_ids=[FAILED_ID])
    assert report["requests"] == 1
    assert report["ledger"]["generation"]["calls"] == 1
    assert report["ledger"]["embedding"]["calls"] == 1


def test_audit_requires_an_end_boundary_or_request_ids(tmp_path):
    with pytest.raises(ValueError):
        measure.audit(_db(tmp_path), started_at=STARTED)


def test_audit_opens_the_database_read_only(tmp_path):
    path = _db(tmp_path)
    before = path.stat().st_mtime_ns
    with measure.open_readonly(path) as con:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM model_calls")
    assert path.stat().st_mtime_ns == before


# ---------------------------------------------------------------- usage 未知、中断与缓存


def test_missing_usage_is_unknown_not_zero_and_interrupted_calls_still_count(tmp_path):
    interrupted = {"request_id": "r-int", "purpose": "answer_with_context", "status": "sent", "max_output_tokens": 2048,
                   "usage_input": None, "usage_output": None, "created_at": "2026-10-03T18:20:00.500Z"}
    failed = {"request_id": "r-fail", "purpose": "answer_with_context", "status": "error", "max_output_tokens": 2048,
              "usage_input": 120, "usage_output": 0, "created_at": "2026-10-03T18:20:01.000Z"}
    report = measure.audit(_db(tmp_path, extra_calls=[interrupted, failed]), started_at=STARTED, ended_at=ENDED)
    generation = report["ledger"]["generation"]
    assert generation["calls"] == 11
    assert generation["unknown_usage_calls"] == 1
    assert generation["tokens"] == 28951 + 120          # 已知部分照计，失败但有 usage 的不漏
    assert generation["tokens_complete"] is False
    stop, why = measure.budget_stop(generation, cap=10_000_000)
    assert stop and "未知" in why


def test_cache_hit_adds_no_ledger_row_and_is_not_an_error(tmp_path):
    cached = {"request_id": "r-cache", "course_id": "c", "version_id": "v", "question": "什么是栈", "outcome": "answered",
              "reason": None, "error_code": None, "error_reason": None, "invalidation_subtype": None, "truncated": 0,
              "latency_ms": 300, "first_delta_latency_ms": 200, "created_at": "2026-10-03T18:21:00.000Z"}
    report = measure.audit(_db(tmp_path, extra_logs=[cached]), started_at=STARTED, ended_at=ENDED)
    row = next(r for r in report["per_request"] if r["request_id"] == "r-cache")
    assert row["embedding_calls"] == 0 and row["generation_calls"] == 0
    assert report["ledger"]["embedding"]["calls"] == 10


def test_budget_stop_counts_generation_only():
    assert measure.budget_stop({"tokens": 44_999, "unknown_usage_calls": 0}, cap=45_000) == (False, None)
    stop, why = measure.budget_stop({"tokens": 45_000, "unknown_usage_calls": 0}, cap=45_000)
    assert stop and "45000" in why


# ---------------------------------------------------------------- 汇总与分位


def test_summary_counts_denominators_and_nearest_rank_percentiles(tmp_path):
    summary = measure.summarize(_http_records(), measure.audit(_db(tmp_path), started_at=STARTED, ended_at=ENDED))
    assert summary["counts"] == {"answered": 7, "not_covered": 2, "error": 1, "no_response": 0, "total": 10}
    assert summary["all_answered"] is False
    first = summary["server_first_delta_ms"]
    assert first["denominator"] == "answered (n=7)"
    assert (first["p50"], first["p95"], first["max"]) == (5020, 9287, 9287)
    assert summary["percentile_method"] == "nearest-rank"
    assert summary["client_elapsed_seconds"]["max"] == 10.27
    assert summary["client_sse_first_delta_ms"] == "未测"
    assert summary["browser_first_token_ms"] == "未测"


def test_nearest_rank_percentile():
    assert measure.nearest_rank([5, 1, 3], 0.5) == 3
    assert measure.nearest_rank([1, 2, 3, 4], 0.95) == 4
    assert measure.nearest_rank([], 0.5) is None


# ---------------------------------------------------------------- SSE 首个 delta


def _clock(*ticks):
    values = iter(ticks)
    return lambda: next(values)


def test_sse_first_delta_is_timed_on_arrival_and_ignores_meta_and_comments():
    stream = io.BytesIO(
        b": keepalive\n\n"
        b'event: meta\ndata: {"event":"meta","status":"answered","request_id":"r1"}\n\n'
        b'event: delta\ndata: {"event":"delta","delta":"\xe6\xa0\x88"}\n\n'
        b'event: done\ndata: {"event":"done","final":{"status":"answered","request_id":"r1","citations":[]}}\n\n')
    result = measure.read_chat_sse(stream, started=0.0, clock=_clock(0.4, 1.25, 2.0))
    assert result["first_delta_ms"] == 1250
    assert result["terminal"] == "done"
    assert result["final"]["request_id"] == "r1"


def test_sse_error_before_any_delta_has_no_first_delta():
    stream = io.BytesIO(
        b'event: error\ndata: {"event":"error","error":{"code":"LLM_UNAVAILABLE","details":'
        b'{"reason":"truncated","request_id":"r9"}}}\n\n')
    result = measure.read_chat_sse(stream, started=0.0, clock=_clock(3.0))
    assert result["first_delta_ms"] is None
    assert result["terminal"] == "error"
    assert result["error"]["details"]["request_id"] == "r9"


# ---------------------------------------------------------------- 命令行端到端（本机假服务，不联网、不付费）

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _FakeChat:
    """假问答服务：JSON 或 SSE；「区别」题按 ADR-082 返回 503 截断错误；每题写一条生成调用到 SQLite。"""

    def __init__(self, db: Path, usage: int | None):
        self.db, self.usage, self.seq = db, usage, 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, status, payload):
                raw = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                if self.path == "/api/v1/auth/login":
                    return self._json(200, {"access_token": "t", "token_type": "bearer", "expires_in": 60})
                fake.seq += 1
                request_id = f"req-{fake.seq}"
                fake.record(request_id)
                if "区别" in body["question"]:
                    return self._json(503, {"code": "LLM_UNAVAILABLE", "message": "x",
                                            "details": {"reason": "truncated", "request_id": request_id}})
                final = {"status": "answered", "answer": "栈后进先出[1]。", "request_id": request_id,
                         "citations": [{"index": 1}], "latency_ms": 900}
                if self.headers.get("Accept", "").startswith("application/json"):
                    return self._json(200, final)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for event in ({"event": "meta", "status": "answered", "request_id": request_id},
                              {"event": "delta", "delta": "栈后进先出[1]。"}, {"event": "done", "final": final}):
                    self.wfile.write(f"event: {event['event']}\ndata: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def record(self, request_id):
        con = sqlite3.connect(self.db)
        now = measure.utc_now_iso()
        con.execute("INSERT INTO model_calls (call_id, status, course_id, request_id, purpose, max_output_tokens,"
                    " usage_input, usage_output, created_at) VALUES (?, 'ok', 'c1', ?, 'answer_with_context', 2048, ?, ?, ?)",
                    (request_id, request_id, self.usage, None if self.usage is None else 0, now))
        con.commit()
        con.close()


@pytest.fixture
def chat_env(tmp_path, monkeypatch):
    db = tmp_path / "live.sqlite3"
    con = sqlite3.connect(db)
    con.execute(MODEL_CALLS_DDL)
    con.execute(CHAT_LOGS_DDL)
    con.close()
    questions = tmp_path / "q.txt"
    questions.write_text("什么是栈\n栈和队列有什么区别\n什么是队列\n", encoding="utf-8")
    monkeypatch.setenv("MEASURE_PASSWORD_TEST", "pw")
    servers = []

    def start(usage):
        fake = _FakeChat(db, usage)
        servers.append(fake)
        return fake

    yield db, questions, tmp_path, start
    for fake in servers:
        fake.server.shutdown()


def _ask(base, questions, *extra):
    return measure.main(["ask", "--base-url", base, "--username", "s", "--password-env", "MEASURE_PASSWORD_TEST",
                         "--course-id", "c1", "--questions", str(questions), *extra])


def _lines(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_cli_ask_exit_zero_does_not_mean_all_answered(chat_env, capsys):
    db, questions, tmp, start = chat_env
    fake = start(usage=100)
    out = tmp / "run.jsonl"
    assert _ask(fake.base, questions, "--out", str(out), "--audit-db", str(db)) == 0
    lines = _lines(capsys)
    failed = lines[1]
    assert (failed["outcome"], failed["error_code"], failed["error_reason"], failed["request_id"]) == (
        "error", "LLM_UNAVAILABLE", "truncated", "req-2")
    summary = lines[-1]["summary"]
    assert summary["counts"]["answered"] == 2 and summary["counts"]["error"] == 1
    assert summary["all_answered"] is False
    assert summary["ledger"]["generation"] == {"calls": 3, "usage_input": 300, "usage_output": 0, "tokens": 300,
                                               "unknown_usage_calls": 0, "tokens_complete": True}
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3


def test_cli_ask_stream_records_client_sse_first_delta(chat_env, capsys):
    db, questions, tmp, start = chat_env
    fake = start(usage=100)
    assert _ask(fake.base, questions, "--stream") == 0
    lines = _lines(capsys)
    assert lines[0]["outcome"] == "answered" and isinstance(lines[0]["client_sse_first_delta_ms"], int)
    assert lines[1]["outcome"] == "error" and lines[1]["client_sse_first_delta_ms"] is None
    assert lines[-1]["summary"]["client_sse_first_delta_ms"]["denominator"] == "answered (n=2)"


def test_cli_ask_hard_stops_on_generation_budget(chat_env, capsys):
    db, questions, tmp, start = chat_env
    fake = start(usage=30_000)
    assert _ask(fake.base, questions, "--audit-db", str(db), "--cap", "45000") == 3
    lines = _lines(capsys)
    assert len(lines) == 3                               # 第 2 题后累计 60000 ≥ 45000，不再问第 3 题
    assert "45000" in lines[-1]["round"]["stopped"]


def test_cli_ask_stops_when_usage_is_unknown(chat_env, capsys):
    db, questions, tmp, start = chat_env
    fake = start(usage=None)
    assert _ask(fake.base, questions, "--audit-db", str(db)) == 3
    assert "未知" in _lines(capsys)[-1]["round"]["stopped"]


def test_cli_audit_joins_records_by_request_id(tmp_path, capsys):
    db = _db(tmp_path)
    records = tmp_path / "records.jsonl"
    records.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _http_records()), encoding="utf-8")
    assert measure.main(["audit", "--db", str(db), "--records", str(records)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["audit"]["requests"] == 10                     # 只按十题的编号关联，不含额外尝试
    assert payload["audit"]["ledger"]["generation"]["tokens"] == 28951 - 4606
    assert payload["summary"]["counts"]["total"] == 10
