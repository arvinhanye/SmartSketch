"""C02-4 / C03-2 测量工具扩展，全部离线。

- `audit` 读出 ADR-089 的推理列（迁移 017）；旧库没有这些列时为未知，不报错。
- `ask --round-started-at`：一轮分多次调用 `ask` 时，止损窗口从整轮起点算，不从每次调用起点算。
- `audit-task`（C03-2）：按任务拆解抽取的各用途调用跨度、repair、usage 与派生的非模型耗时，取代 L11-6 的忽略目录脚本
  （那份脚本把缺失 usage 当 0、用字符串比较时间）。
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("measure_web_flow", ROOT / "evaluation/measure_web_flow.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)

CALLS_V17 = """
CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY NOT NULL, status TEXT NOT NULL, course_id TEXT NOT NULL, task_id TEXT, chunk_id TEXT,
    request_id TEXT, purpose TEXT NOT NULL, is_repair INTEGER NOT NULL DEFAULT 0, max_output_tokens INTEGER NOT NULL,
    usage_input INTEGER, usage_output INTEGER, created_at TEXT NOT NULL, finished_at TEXT, latency_ms INTEGER,
    error_class TEXT, usage_reasoning INTEGER, reasoning_chars INTEGER, first_reasoning_ms INTEGER,
    first_content_ms INTEGER
)"""
CALLS_V16 = """
CREATE TABLE model_calls (
    call_id TEXT PRIMARY KEY NOT NULL, status TEXT NOT NULL, course_id TEXT NOT NULL, task_id TEXT, chunk_id TEXT,
    request_id TEXT, purpose TEXT NOT NULL, is_repair INTEGER NOT NULL DEFAULT 0, max_output_tokens INTEGER NOT NULL,
    usage_input INTEGER, usage_output INTEGER, created_at TEXT NOT NULL, finished_at TEXT, latency_ms INTEGER,
    error_class TEXT
)"""
LOGS = """
CREATE TABLE chat_logs (
    request_id TEXT PRIMARY KEY NOT NULL, course_id TEXT NOT NULL, version_id TEXT NOT NULL, question TEXT NOT NULL,
    outcome TEXT NOT NULL, reason TEXT, error_code TEXT, error_reason TEXT, invalidation_subtype TEXT,
    truncated INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER NOT NULL, first_delta_latency_ms INTEGER,
    created_at TEXT NOT NULL
)"""


def _db(tmp_path: Path, ddl: str, calls: list[dict], logs: list[dict] = ()) -> Path:
    path = tmp_path / "m.sqlite3"
    con = sqlite3.connect(path)
    con.execute(ddl)
    con.execute(LOGS)
    for n, call in enumerate(calls):
        columns = ["call_id", "status", "course_id", "max_output_tokens", *call]
        values = [f"c{n}", call.get("status", "ok"), "c1", 2048, *call.values()]
        if "status" in call:
            columns.remove("status")
            values.pop(1)
        con.execute(f"INSERT INTO model_calls ({', '.join(columns)}) VALUES ({', '.join('?' * len(values))})", values)
    for log in logs:
        con.execute("INSERT INTO chat_logs (request_id, course_id, version_id, question, outcome, latency_ms,"
                    " first_delta_latency_ms, created_at) VALUES (?, 'c1', 'v', ?, ?, ?, ?, ?)",
                    (log["request_id"], log["question"], log["outcome"], log["latency_ms"],
                     log.get("first_delta_latency_ms"), log["created_at"]))
    con.commit()
    con.close()
    return path


T0 = "2026-10-03T20:00:00.000Z"
T1 = "2026-10-03T20:59:59.000Z"


def _qa_call(request_id: str, created_at: str, **extra) -> dict:
    return {"request_id": request_id, "purpose": "answer_with_context", "usage_input": 2000, "usage_output": 900,
            "created_at": created_at, "latency_ms": 8000, **extra}


# ---------------------------------------------------------------- audit：推理列


def test_audit_reports_reasoning_columns_per_request_and_in_the_ledger(tmp_path):
    db = _db(tmp_path, CALLS_V17, [
        _qa_call("r1", "2026-10-03T20:01:00.000Z", usage_reasoning=700, reasoning_chars=1500,
                 first_reasoning_ms=400, first_content_ms=7600),
        _qa_call("r2", "2026-10-03T20:02:00.000Z"),            # 供应商没报推理：未知
        {"request_id": "r1", "purpose": "embedding", "usage_input": 5, "usage_output": 0,
         "created_at": "2026-10-03T20:00:59.500Z", "latency_ms": 400},
    ], logs=[
        {"request_id": "r1", "question": "q1", "outcome": "answered", "latency_ms": 8500, "first_delta_latency_ms": 8000,
         "created_at": "2026-10-03T20:01:08.000Z"},
        {"request_id": "r2", "question": "q2", "outcome": "answered", "latency_ms": 8300, "first_delta_latency_ms": 7900,
         "created_at": "2026-10-03T20:02:08.000Z"},
    ])
    report = measure.audit(db, started_at=T0, ended_at=T1)
    rows = {r["request_id"]: r for r in report["per_request"]}
    assert (rows["r1"]["generation_reasoning_tokens"], rows["r1"]["generation_reasoning_chars"]) == (700, 1500)
    assert (rows["r1"]["generation_first_reasoning_ms"], rows["r1"]["generation_first_content_ms"]) == (400, 7600)
    assert rows["r2"]["generation_reasoning_tokens"] is None and rows["r2"]["generation_first_content_ms"] is None
    generation = report["ledger"]["generation"]
    assert (generation["reasoning_tokens"], generation["reasoning_unknown_calls"]) == (700, 1)
    assert report["reasoning_columns"] is True


def test_audit_on_a_database_before_migration_017_marks_reasoning_unknown(tmp_path):
    db = _db(tmp_path, CALLS_V16, [_qa_call("r1", "2026-10-03T20:01:00.000Z")],
             logs=[{"request_id": "r1", "question": "q", "outcome": "answered", "latency_ms": 8100,
                    "created_at": "2026-10-03T20:01:08.000Z"}])
    report = measure.audit(db, started_at=T0, ended_at=T1)
    assert report["reasoning_columns"] is False
    assert report["per_request"][0]["generation_reasoning_tokens"] is None
    assert report["ledger"]["generation"]["reasoning_tokens"] is None


# ---------------------------------------------------------------- audit-task（C03-2）

TASKS = """
CREATE TABLE processing_tasks (id TEXT PRIMARY KEY, course_id TEXT, stage TEXT, created_at TEXT, updated_at TEXT,
                               error_code TEXT);
CREATE TABLE task_revisions (task_id TEXT, revision_id TEXT);
CREATE TABLE chunks (chunk_id TEXT, revision_id TEXT);
"""


def _task_db(tmp_path: Path, calls: list[dict]) -> Path:
    db = _db(tmp_path, CALLS_V17, calls)
    con = sqlite3.connect(db)
    con.executescript(TASKS)
    con.execute("INSERT INTO processing_tasks VALUES ('t1', 'c1', 'awaiting_review', '2026-10-03T20:00:00.000Z',"
                " '2026-10-03T20:01:20.000Z', NULL)")
    con.execute("INSERT INTO task_revisions VALUES ('t1', 'rev1')")
    con.executemany("INSERT INTO chunks VALUES (?, 'rev1')", [(f"k{i}",) for i in range(24)])
    con.commit()
    con.close()
    return db


def _task_call(purpose: str, created: str, finished: str, *, repair: int = 0, usage=(1000, 500), status="ok",
               error_class=None, task_id="t1") -> dict:
    return {"task_id": task_id, "purpose": purpose, "is_repair": repair, "usage_input": usage[0] if usage else None,
            "usage_output": usage[1] if usage else None, "created_at": created, "finished_at": finished,
            "latency_ms": 1000, "status": status, "error_class": error_class}


def test_audit_task_splits_phases_repairs_and_derives_non_model_time(tmp_path):
    db = _task_db(tmp_path, [
        _task_call("extract_entities", "2026-10-03T20:00:02.000Z", "2026-10-03T20:00:20.000Z"),
        _task_call("extract_entities", "2026-10-03T20:00:03.500Z", "2026-10-03T20:00:40.250Z", repair=1),
        _task_call("extract_relations", "2026-10-03T20:00:41.000Z", "2026-10-03T20:01:10.000Z",
                   status="error", error_class="server"),
        _task_call("extract_entities", "2026-10-03T20:00:05.000Z", "2026-10-03T20:00:06.000Z", task_id="other"),
    ])
    report = measure.audit_task(db, task_id="t1", client_elapsed_seconds=82.5)
    entities = report["by_purpose"]["extract_entities"]
    assert (entities["calls"], entities["repair_calls"]) == (2, 1)
    assert entities["span_seconds"] == 38.25
    assert report["non_ok_calls"] == {"extract_relations:server": 1}
    assert report["model_span_seconds"] == 68.0             # 首条创建 20:00:02 → 末条完成 20:01:10
    assert report["non_model_seconds"] == 14.5              # 82.5 − 68.0（含排队、解析、分块、融合、入库）
    assert report["chunks"] == 24 and report["calls"] == 3 and report["repair_calls"] == 1
    assert report["ledger"]["generation"]["tokens"] == 4500 and report["ledger"]["generation"]["tokens_complete"] is True
    assert report["task"]["stage"] == "awaiting_review"


def test_audit_task_unfinished_call_makes_spans_and_usage_unknown(tmp_path):
    db = _task_db(tmp_path, [
        _task_call("extract_relations", "2026-10-03T20:00:41.000Z", "2026-10-03T20:01:10.000Z"),
        _task_call("extract_relations", "2026-10-03T20:00:42.000Z", None, usage=None, status="sent"),
    ])
    report = measure.audit_task(db, task_id="t1", client_elapsed_seconds=82.5)
    relations = report["by_purpose"]["extract_relations"]
    assert relations["unknown_usage_calls"] == 1 and relations["span_seconds"] is None
    assert report["non_ok_calls"] == {"extract_relations:sent": 1}
    assert report["model_span_seconds"] is None and report["non_model_seconds"] is None
    assert report["ledger"]["generation"]["tokens_complete"] is False


def test_audit_task_without_client_elapsed_leaves_non_model_time_unknown(tmp_path):
    db = _task_db(tmp_path, [_task_call("extract_entities", "2026-10-03T20:00:02.000Z", "2026-10-03T20:00:20.000Z")])
    report = measure.audit_task(db, task_id="t1")
    assert report["non_model_seconds"] is None


def test_audit_task_unknown_task_is_an_error(tmp_path):
    db = _task_db(tmp_path, [])
    with pytest.raises(ValueError):
        measure.audit_task(db, task_id="missing")


def test_cli_audit_task_prints_json(tmp_path, capsys):
    db = _task_db(tmp_path, [_task_call("extract_entities", "2026-10-03T20:00:02.000Z", "2026-10-03T20:00:20.000Z")])
    assert measure.main(["audit-task", "--db", str(db), "--task-id", "t1", "--client-elapsed-seconds", "30"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["model_span_seconds"] == 18.0 and payload["non_model_seconds"] == 12.0


# ---------------------------------------------------------------- ask --round-started-at


def test_round_started_at_makes_the_budget_window_span_the_whole_round(tmp_path, monkeypatch, capsys):
    from test_c01_measure import _FakeChat, CHAT_LOGS_DDL, MODEL_CALLS_DDL   # 复用本机假服务

    db = tmp_path / "live.sqlite3"
    con = sqlite3.connect(db)
    con.execute(MODEL_CALLS_DDL)
    con.execute(CHAT_LOGS_DDL)
    round_start = measure.utc_now_iso()
    # 同一轮里前一次 ask 已用掉 44950 生成 token
    con.execute("INSERT INTO model_calls (call_id, status, course_id, request_id, purpose, max_output_tokens,"
                " usage_input, usage_output, created_at) VALUES ('prev', 'ok', 'c1', 'prev', 'answer_with_context',"
                " 2048, 44000, 950, ?)", (measure.utc_now_iso(),))
    con.commit()
    con.close()
    questions = tmp_path / "q.txt"
    questions.write_text("什么是栈\n什么是队列\n", encoding="utf-8")
    monkeypatch.setenv("MEASURE_PASSWORD_TEST", "pw")
    fake = _FakeChat(db, usage=100)
    try:
        code = measure.main(["ask", "--base-url", fake.base, "--username", "s", "--password-env", "MEASURE_PASSWORD_TEST",
                             "--course-id", "c1", "--questions", str(questions), "--audit-db", str(db),
                             "--cap", "45000", "--round-started-at", round_start])
    finally:
        fake.server.shutdown()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert code == 3 and len(lines) == 2                   # 第 1 题后整轮 45050 ≥ 45000，停止
    assert lines[-1]["round"]["started_at"] == round_start
