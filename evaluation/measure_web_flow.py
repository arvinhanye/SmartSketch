#!/usr/bin/env python3
"""经真实 HTTP 接口测量抽取与问答耗时（L02、L16）。只用标准库；不读也不打印任何密钥。

计时边界（docs/superpowers/specs/2026-10-02-contest-sprint-design.md 第 5 节）：

- ``extract``：发出上传请求 → 任务快照 ``stage`` 进入 ``awaiting_review`` / ``failed`` / ``cancelled``。
  含排队、解析、分块、抽取、直通融合与入库。每 0.5 秒轮询一次，读数误差不超过一个轮询间隔。
- ``ask``：发出问答请求 → 收到完整 JSON 响应（客户端完整响应）；同时记录服务端 ``latency_ms``。
  ``--stream`` 改走 SSE，另记**客户端 SSE 首个 delta**（收到第一条 ``delta`` 事件的时刻）。
  **服务端首个 delta** 在 ``chat_logs.first_delta_latency_ms``，由 ``audit`` 只读关联。
  浏览器可见首字不在本工具测量范围，未实测时一律写「未测」。
- ``audit``（C01，B-EVAL-01）：只读打开 SQLite（``mode=ro`` + ``query_only``），按固定请求 ID 集合或
  ``[started_at, ended_at)`` 时间窗口关联 ``chat_logs`` 与 ``model_calls``。时间按 UTC 时刻比较，不做字符串比较
  （``18:16:00.314Z`` 必须落在起点 ``18:16:00Z`` 之内）。生成（``purpose != embedding``）与向量分账；
  缺失 usage 记为未知而不是 0；分位数用最近秩法并注明分母。

口令从 ``--password-env`` 指定的环境变量读取，不出现在命令行参数里。

用法（仓库根目录）::

    python evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:8001 \\
        --username demo_teacher --password-env MEASURE_PASSWORD --course-name "基线" --file path/to/chapter.md
    python evaluation/measure_web_flow.py ask --base-url http://127.0.0.1:8001 \\
        --username demo_student --password-env MEASURE_PASSWORD --course-id <cid> --questions questions.txt

``extract`` 输出一行 JSON，任务到达 ``awaiting_review`` 时退出码为 0，否则为 1。
``ask`` 每题输出一行 JSON，最后输出一行汇总；退出码 0 只表示测量跑完，**不表示所有题都答成功**
（看汇总里的 ``counts`` 与 ``all_answered``）；因预算止损或拿不到响应而提前停止时退出码为 3。

    python evaluation/measure_web_flow.py ask ... --out run.jsonl --audit-db path/to/smartsketch.sqlite3 --cap 45000
    python evaluation/measure_web_flow.py audit --db path/to/smartsketch.sqlite3 --records run.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

TERMINAL = frozenset({"awaiting_review", "completed", "failed", "cancelled"})
POLL_SECONDS = 0.5
BOUNDARY = "measure-web-flow-boundary"


def is_terminal(stage: str) -> bool:
    return stage in TERMINAL


def encode_multipart(filename: str, data: bytes, *, boundary: str) -> tuple[str, bytes]:
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return f"multipart/form-data; boundary={boundary}", head + data + f"\r\n--{boundary}--\r\n".encode()


def call(base: str, method: str, path: str, *, token: str | None = None, body: bytes | None = None,
         content_type: str = "application/json", timeout: float = 120):
    request = urllib.request.Request(base.rstrip("/") + path, data=body, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", content_type)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw) if raw else None
        except ValueError:
            return error.code, None


# ---------------------------------------------------------------- C01：时间、结局、关联与分账


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


_ZONE = re.compile(r"(Z|[+-]\d\d:\d\d)$")


def parse_utc(text: str) -> datetime:
    """ISO 8601 时刻 → 带时区的 datetime。没有时区的读数无法确定时刻，直接拒绝。"""
    if not isinstance(text, str) or not _ZONE.search(text):
        raise ValueError(f"时间缺少时区：{text!r}")
    value = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    return value.astimezone(timezone.utc)


def in_window(created_at: str, started_at: str, ended_at: str) -> bool:
    """``[started_at, ended_at)``，按时刻比较。"""
    return parse_utc(started_at) <= parse_utc(created_at) < parse_utc(ended_at)


def normalize_ask_result(*, question: str, course_id: str, http_status: int | None, body: Mapping[str, Any] | None,
                         client_elapsed_seconds: float, client_sse_first_delta_ms: int | None = None) -> dict[str, Any]:
    """一次问答的客户端结局。HTTP 错误对象的编号在 ``details.request_id``；结局、错误码与错误原因分开记录。"""
    record: dict[str, Any] = {
        "question": question, "course_id": course_id, "http_status": http_status,
        "request_id": None, "outcome": None, "reason": None, "error_code": None, "error_reason": None,
        "citations": 0, "server_latency_ms": None,
        "client_elapsed_seconds": client_elapsed_seconds, "client_sse_first_delta_ms": client_sse_first_delta_ms,
    }
    if http_status is None:
        record["outcome"] = "no_response"
        return record
    body = body or {}
    if 200 <= http_status < 300 and isinstance(body.get("status"), str):
        record.update(outcome=body["status"], reason=body.get("reason"), request_id=body.get("request_id"),
                      citations=len(body.get("citations") or []), server_latency_ms=body.get("latency_ms"))
        return record
    details = body.get("details") if isinstance(body.get("details"), Mapping) else {}
    record.update(outcome="error", error_code=body.get("code"), error_reason=details.get("reason"),
                  request_id=body.get("request_id") or details.get("request_id"))
    return record


@contextmanager
def open_readonly(path: str | Path) -> Iterator[sqlite3.Connection]:
    """只读打开：URI ``mode=ro`` 加 ``PRAGMA query_only``，任何写入都报错，文件不被改动。"""
    uri = "file:" + urllib.parse.quote(str(Path(path).resolve())) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only = ON")
        yield con
    finally:
        con.close()


CALL_COLUMNS = ("request_id", "purpose", "status", "max_output_tokens", "usage_input", "usage_output",
                "created_at", "latency_ms")
#: 系统计费口径（``BILLED_TOKENS_SQL``）需要的列；夹具或旧库缺少时，未知 usage 无法估算
BILLING_COLUMNS = ("input_tokens_est", "error_class")
REJECTED_SUFFIX = ":rejected_before_generation"
#: ADR-089（迁移 017）推理列；旧库没有时一律视为未知
REASONING_COLUMNS = ("usage_reasoning", "reasoning_chars", "first_reasoning_ms", "first_content_ms")


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
LOG_COLUMNS = ("request_id", "course_id", "question", "outcome", "reason", "error_code", "error_reason",
               "invalidation_subtype", "truncated", "latency_ms", "first_delta_latency_ms", "created_at")


def _select(con: sqlite3.Connection, table: str, columns: Sequence[str],
            request_ids: Sequence[str] | None) -> list[dict[str, Any]]:
    sql = f"SELECT {', '.join(columns)} FROM {table}"
    if request_ids is None:
        return [dict(row) for row in con.execute(sql)]
    marks = ", ".join("?" for _ in request_ids)
    return [dict(row) for row in con.execute(f"{sql} WHERE request_id IN ({marks})", tuple(request_ids))]


def _group(calls: Iterable[Mapping[str, Any]], *, reasoning: bool = False) -> dict[str, Any]:
    rows = list(calls)
    known = [r for r in rows if r["usage_input"] is not None and r["usage_output"] is not None]
    usage_input = sum(r["usage_input"] for r in known)
    usage_output = sum(r["usage_output"] for r in known)
    unknown = len(rows) - len(known)
    billed = [_billed(r) for r in rows]
    group: dict[str, Any] = {"calls": len(rows), "usage_input": usage_input, "usage_output": usage_output,
                             "tokens": usage_input + usage_output, "unknown_usage_calls": unknown,
                             "tokens_complete": unknown == 0,
                             # 系统计费口径：未知 usage 按「输入估算 + 输出上限」计、生成前被拒计 0；缺估算列时为未知
                             "billed_tokens": None if None in billed else sum(billed),
                             "billed_complete": None not in billed}
    if reasoning:
        # 推理 token 是 usage_output 的一部分，只用于诊断，不另计费
        reported = [r["usage_reasoning"] for r in rows if r.get("usage_reasoning") is not None]
        group["reasoning_tokens"] = sum(reported) if reported or not rows else None
        group["reasoning_unknown_calls"] = len(rows) - len(reported)
    return group


def _latency(calls: Iterable[Mapping[str, Any]]) -> int | None:
    rows = list(calls)
    if any(r["latency_ms"] is None for r in rows):
        return None
    return sum(r["latency_ms"] for r in rows)


def _billed(call: Mapping[str, Any]) -> int | None:
    """与 ``app.repositories.model_calls.BILLED_TOKENS_SQL`` 同一规则（只允许高估）。"""
    if call["usage_input"] is not None and call["usage_output"] is not None:
        return call["usage_input"] + call["usage_output"]
    if call.get("status") == "error" and str(call.get("error_class") or "").endswith(REJECTED_SUFFIX):
        return 0
    if call.get("input_tokens_est") is None:
        return None
    return call["input_tokens_est"] + call["max_output_tokens"]


def _is_embedding(call: Mapping[str, Any]) -> bool:
    return call["purpose"] == "embedding"


def ledger(calls: Sequence[Mapping[str, Any]], *, reasoning: bool = True) -> dict[str, Any]:
    """生成（``purpose != embedding``，计入生成预算）与向量分开计；另列各用途明细。"""
    purposes = sorted({c["purpose"] for c in calls})
    generation = _group((c for c in calls if not _is_embedding(c)), reasoning=reasoning)
    if not reasoning:
        generation.update(reasoning_tokens=None, reasoning_unknown_calls=generation["calls"])
    return {
        "generation": generation,
        "embedding": _group(c for c in calls if _is_embedding(c)),
        "by_purpose": {p: _group(c for c in calls if c["purpose"] == p) for p in purposes},
    }


def audit(db_path: str | Path, *, started_at: str | None = None, ended_at: str | None = None,
          request_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """只读关联一轮测量。必须给固定请求 ID，或同时给起止时刻（结束边界防止后续调用污染本轮）。"""
    if request_ids is None and (started_at is None or ended_at is None):
        raise ValueError("audit 需要 request_ids，或同时给 started_at 与 ended_at")
    ids = None if request_ids is None else list(dict.fromkeys(request_ids))
    with open_readonly(db_path) as con:
        present = _columns(con, "model_calls")
        has_reasoning = set(REASONING_COLUMNS) <= present
        columns = (CALL_COLUMNS + tuple(c for c in BILLING_COLUMNS if c in present)
                   + (REASONING_COLUMNS if has_reasoning else ()))
        calls = _select(con, "model_calls", columns, ids)
        logs = _select(con, "chat_logs", LOG_COLUMNS, ids)
    if ids is None:
        calls = [c for c in calls if in_window(c["created_at"], started_at, ended_at)]
        logs = [g for g in logs if in_window(g["created_at"], started_at, ended_at)]
    calls.sort(key=lambda c: parse_utc(c["created_at"]))
    logs.sort(key=lambda g: parse_utc(g["created_at"]))
    by_request: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_request.setdefault(call["request_id"], []).append(call)
    per_request = []
    for log in logs:
        own = by_request.get(log["request_id"], [])
        generation = _group(c for c in own if not _is_embedding(c))
        embedding = _group(c for c in own if _is_embedding(c))
        embedding_ms = _latency(c for c in own if _is_embedding(c))
        generation_ms = _latency(c for c in own if not _is_embedding(c))
        other_ms = (None if embedding_ms is None or generation_ms is None
                    else log["latency_ms"] - embedding_ms - generation_ms)
        final = [c for c in own if not _is_embedding(c)][-1:]      # 给出结局的那次生成（含主备切换后的最后一次）
        last = final[0] if final else {}
        per_request.append({**log, "generation_calls": generation["calls"], "embedding_calls": embedding["calls"],
                            "generation_reasoning_tokens": last.get("usage_reasoning"),
                            "generation_reasoning_chars": last.get("reasoning_chars"),
                            "generation_first_reasoning_ms": last.get("first_reasoning_ms"),
                            "generation_first_content_ms": last.get("first_content_ms"),
                            "generation_tokens": generation["tokens"] if generation["tokens_complete"] else None,
                            "embedding_tokens": embedding["tokens"] if embedding["tokens_complete"] else None,
                            # C02-3 分段：总耗时 − 查询向量 − 生成 = 其余（检索、组装、校验等）；任一调用缺耗时即未知
                            "embedding_ms": embedding_ms, "generation_ms": generation_ms, "other_ms": other_ms})
    logged = {g["request_id"] for g in logs}
    return {
        "window": {"started_at": started_at, "ended_at": ended_at, "request_ids": ids},
        "requests": len(logs),
        "per_request": per_request,
        "reasoning_columns": has_reasoning,
        "ledger": ledger(calls, reasoning=has_reasoning),
        # 窗口内没有对应 chat_logs 的调用（如同期抽取任务、未落日志的中断）照样计费，单列以便核对
        "unmatched_calls": sum(1 for c in calls if c["request_id"] not in logged),
    }


TASK_CALL_COLUMNS = ("purpose", "status", "is_repair", "max_output_tokens", "usage_input", "usage_output",
                     "created_at", "finished_at", "latency_ms", "error_class")


def _span_seconds(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """首条创建 → 末条完成；有任一调用未完成（无 finished_at）即未知。"""
    if not rows or any(r["finished_at"] is None for r in rows):
        return None
    start = min(parse_utc(r["created_at"]) for r in rows)
    end = max(parse_utc(r["finished_at"]) for r in rows)
    return round((end - start).total_seconds(), 3)


def audit_task(db_path: str | Path, *, task_id: str, client_elapsed_seconds: float | None = None) -> dict[str, Any]:
    """C03-2：一次抽取任务的调用拆解（只读）。

    各用途：调用数、repair 数、usage（缺失为未知）、首条创建 → 末条完成的跨度、平均 / 最大耗时；
    非 ok 调用按「用途:状态」计数。``non_model_seconds`` = 客户端测得的上传 → 待审核 − 模型调用总跨度，
    是排队、解析、分块、融合、入库的**派生**值；赛题「解析 + 知识抽取」口径仍以客户端总耗时为准，不剔除模型时间。
    """
    with open_readonly(db_path) as con:
        task = con.execute("SELECT id, stage, created_at, updated_at, error_code FROM processing_tasks WHERE id = ?",
                           (task_id,)).fetchone()
        if task is None:
            raise ValueError(f"任务不存在：{task_id}")
        present = _columns(con, "model_calls")
        has_reasoning = set(REASONING_COLUMNS) <= present
        columns = (TASK_CALL_COLUMNS + tuple(c for c in BILLING_COLUMNS if c in present and c not in TASK_CALL_COLUMNS)
                   + (("usage_reasoning",) if has_reasoning else ()))
        calls = [dict(r) for r in con.execute(
            f"SELECT {', '.join(columns)} FROM model_calls WHERE task_id = ?", (task_id,))]
        chunks = con.execute("SELECT count(*) FROM chunks c JOIN task_revisions t ON c.revision_id = t.revision_id"
                             " WHERE t.task_id = ?", (task_id,)).fetchone()[0]
    calls.sort(key=lambda c: parse_utc(c["created_at"]))
    by_purpose: dict[str, Any] = {}
    for purpose in sorted({c["purpose"] for c in calls}):
        rows = [c for c in calls if c["purpose"] == purpose]
        latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
        by_purpose[purpose] = {
            **_group(rows), "repair_calls": sum(1 for r in rows if r["is_repair"]),
            "span_seconds": _span_seconds(rows),
            "latency_ms_avg": round(sum(latencies) / len(latencies)) if latencies else None,
            "latency_ms_max": max(latencies, default=None),
        }
    non_ok: dict[str, int] = {}
    for call in calls:
        if call["status"] != "ok":
            key = f"{call['purpose']}:{call['error_class'] or call['status']}"
            non_ok[key] = non_ok.get(key, 0) + 1
    span = _span_seconds(calls)
    return {
        "task": dict(task),
        "chunks": chunks,
        "calls": len(calls),
        "repair_calls": sum(1 for c in calls if c["is_repair"]),
        "by_purpose": by_purpose,
        "non_ok_calls": non_ok,
        "model_span_seconds": span,
        "client_elapsed_seconds": client_elapsed_seconds,
        "non_model_seconds": (None if span is None or client_elapsed_seconds is None
                              else round(client_elapsed_seconds - span, 3)),
        "ledger": ledger(calls, reasoning=has_reasoning),
    }


def budget_stop(generation: Mapping[str, Any], *, cap: int) -> tuple[bool, str | None]:
    """硬止损只按生成 token。usage 未知的调用按系统计费规则计为估算值（输入估算 + 输出上限，只会高估）；
    缺少估算列、无法估算时才停止（复核 ``docs/reviews/claude-deepseek-c02-4-c03-1.md`` §4）。"""
    unknown = generation.get("unknown_usage_calls", 0)
    billed = generation.get("billed_tokens")
    if unknown > 0 and billed is None:
        return True, f"存在 {unknown} 次 usage 未知且无法估算的生成调用，无法确认额度，停止"
    spent = billed if billed is not None else generation["tokens"]
    if spent >= cap:
        detail = f"（含 {unknown} 次未知 usage 的估算）" if unknown else ""
        return True, f"生成 token {spent}{detail} 达到增量止损 {cap}"
    return False, None


def nearest_rank(values: Sequence[float], q: float) -> float | None:
    """最近秩法：排序后取第 ⌈q·n⌉ 个（1 起）。"""
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(math.ceil(q * len(ordered)), 1) - 1]


def _stats(values: Sequence[float], denominator: str) -> dict[str, Any]:
    return {"denominator": denominator, "n": len(values), "min": min(values, default=None),
            "p50": nearest_rank(values, 0.5), "p95": nearest_rank(values, 0.95), "max": max(values, default=None)}


def summarize(records: Sequence[Mapping[str, Any]], report: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """逐题结局计数与耗时分位。首字三列口径分开：服务端首个 delta、客户端 SSE 首个 delta、浏览器（未测）。"""
    counts: dict[str, int] = {"answered": 0, "not_covered": 0, "error": 0, "no_response": 0}
    for record in records:
        counts[record["outcome"]] = counts.get(record["outcome"], 0) + 1
    counts["total"] = len(records)
    logs = {g["request_id"]: g for g in (report or {}).get("per_request", [])}
    answered = [r for r in records if r["outcome"] == "answered"]
    server_first = [logs[r["request_id"]]["first_delta_latency_ms"] for r in answered
                    if r["request_id"] in logs and logs[r["request_id"]]["first_delta_latency_ms"] is not None]
    server_latency = [logs[r["request_id"]]["latency_ms"] for r in records if r["request_id"] in logs]
    elapsed = [r["client_elapsed_seconds"] for r in records if r["client_elapsed_seconds"] is not None]
    sse_first = [r["client_sse_first_delta_ms"] for r in answered if r.get("client_sse_first_delta_ms") is not None]
    summary: dict[str, Any] = {
        "counts": counts,
        "all_answered": counts["total"] > 0 and counts["answered"] == counts["total"],
        "percentile_method": "nearest-rank",
        "client_elapsed_seconds": _stats(elapsed, f"all requests (n={len(elapsed)})"),
        "server_latency_ms": _stats(server_latency, f"requests with chat_logs (n={len(server_latency)})")
        if report else "未关联",
        "server_first_delta_ms": _stats(server_first, f"answered (n={len(server_first)})") if report else "未关联",
        "client_sse_first_delta_ms": _stats(sse_first, f"answered (n={len(sse_first)})") if sse_first else "未测",
        "browser_first_token_ms": "未测",
    }
    if report:
        summary["ledger"] = report["ledger"]
    return summary


def read_chat_sse(stream: BinaryIO, *, started: float,
                  clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """读问答 SSE（``events.v1.md`` §3）。每个带数据的事件到达时读一次时钟，第一条 ``delta`` 即客户端首字。"""
    result: dict[str, Any] = {"first_delta_ms": None, "total_ms": None, "terminal": None,
                              "meta": None, "final": None, "error": None}
    data: list[str] = []
    while True:
        raw = stream.readline()
        line = raw.decode("utf-8").rstrip("\r\n") if raw else None
        if line:
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            continue
        if data:
            now = clock()
            event = json.loads("\n".join(data))
            data = []
            kind = event.get("event")
            if kind == "delta" and result["first_delta_ms"] is None:
                result["first_delta_ms"] = round((now - started) * 1000)
            elif kind == "meta":
                result["meta"] = event
            elif kind in ("done", "error"):
                result.update(terminal=kind, total_ms=round((now - started) * 1000),
                              final=event.get("final"), error=event.get("error"))
                return result
        if line is None:
            return result


def login(base: str, username: str, password_env: str) -> str:
    password = os.environ.get(password_env)
    if not password:
        raise SystemExit(f"环境变量 {password_env} 未设置")
    status, body = call(base, "POST", "/api/v1/auth/login",
                        body=json.dumps({"username": username, "password": password}).encode())
    if status != 200 or not body:
        raise SystemExit(f"登录失败：HTTP {status}")
    return body["access_token"]


def cmd_extract(args: argparse.Namespace) -> int:
    token = login(args.base_url, args.username, args.password_env)
    status, course = call(args.base_url, "POST", "/api/v1/courses", token=token,
                          body=json.dumps({"name": args.course_name}).encode())
    if status != 201:
        raise SystemExit(f"建课失败：HTTP {status}")
    data = Path(args.file).read_bytes()
    content_type, body = encode_multipart(Path(args.file).name, data, boundary=BOUNDARY)
    started = time.monotonic()
    status, accepted = call(args.base_url, "POST", f"/api/v1/courses/{course['id']}/documents", token=token,
                            body=body, content_type=content_type)
    if status != 202:
        raise SystemExit(f"上传失败：HTTP {status} {(accepted or {}).get('code')}")
    stage, error_code = "queued", None
    while not is_terminal(stage) and time.monotonic() - started <= args.max_seconds:
        time.sleep(POLL_SECONDS)
        _, task = call(args.base_url, "GET", f"/api/v1/tasks/{accepted['task_id']}", token=token)
        stage = task["stage"]
        error_code = (task.get("error") or {}).get("code")
    print(json.dumps({"course_id": course["id"], "task_id": accepted["task_id"], "stage": stage,
                      "error_code": error_code, "elapsed_seconds": round(time.monotonic() - started, 2),
                      "file_bytes": len(data)}, ensure_ascii=False))
    return 0 if stage == "awaiting_review" else 1


def _ask_once(base: str, token: str, course_id: str, question: str, *, stream: bool) -> dict[str, Any]:
    path = f"/api/v1/courses/{course_id}/chat"
    body = json.dumps({"question": question}).encode()
    started = time.monotonic()
    if not stream:
        try:
            status, payload = call(base, "POST", path, token=token, body=body, timeout=60)
        except (urllib.error.URLError, TimeoutError):
            status, payload = None, None
        return normalize_ask_result(question=question, course_id=course_id, http_status=status, body=payload,
                                    client_elapsed_seconds=round(time.monotonic() - started, 2))
    request = urllib.request.Request(base.rstrip("/") + path, data=body, method="POST")
    request.add_header("Accept", "text/event-stream")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            sse = read_chat_sse(response, started=started)
        payload = sse["final"] if sse["terminal"] == "done" else sse["error"]
        status = 200 if sse["terminal"] is not None else None
        first = sse["first_delta_ms"]
    except urllib.error.HTTPError as error:          # 建流前的拒绝（鉴权、校验、限流）按 JSON 错误对象处理
        raw = error.read()
        status, first = error.code, None
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = None
    except (urllib.error.URLError, TimeoutError):
        status, payload, first = None, None, None
    return normalize_ask_result(question=question, course_id=course_id, http_status=status, body=payload,
                                client_elapsed_seconds=round(time.monotonic() - started, 2),
                                client_sse_first_delta_ms=first)


def cmd_ask(args: argparse.Namespace) -> int:
    token = login(args.base_url, args.username, args.password_env)
    questions = [line.strip() for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]
    # 一轮分多次调用时传同一个起点，止损按整轮累计
    started_at = args.round_started_at or utc_now_iso()
    parse_utc(started_at)
    out = Path(args.out) if args.out else None
    records: list[dict[str, Any]] = []
    stopped: str | None = None
    for question in questions:
        # A resumed round (or other calls in the same window) may already require a stop.
        # Check before issuing a paid request as well as after each completed question.
        if args.audit_db:
            report = audit(args.audit_db, started_at=started_at, ended_at=utc_now_iso())
            stop, why = budget_stop(report["ledger"]["generation"], cap=args.cap)
            if stop:
                stopped = why
                break
        record = {**_ask_once(args.base_url, token, args.course_id, question, stream=args.stream),
                  "round_started_at": started_at}
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
        if out is not None:
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        if record["outcome"] == "no_response":
            stopped = f"拿不到响应：{question}"
            break
        if args.audit_db:
            report = audit(args.audit_db, started_at=started_at, ended_at=utc_now_iso())
            stop, why = budget_stop(report["ledger"]["generation"], cap=args.cap)
            if stop:
                stopped = why
                break
    ended_at = utc_now_iso()
    report = audit(args.audit_db, started_at=started_at, ended_at=ended_at) if args.audit_db else None
    print(json.dumps({"round": {"started_at": started_at, "ended_at": ended_at, "stopped": stopped},
                      "summary": summarize(records, report)}, ensure_ascii=False))
    return 3 if stopped else 0


def _load_records(path: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def cmd_audit(args: argparse.Namespace) -> int:
    records = _load_records(args.records) if args.records else []
    if args.request_ids:
        ids: list[str] | None = [i for i in args.request_ids.split(",") if i]
    elif records and not (args.since or args.until):
        ids = [r["request_id"] for r in records if r["request_id"]]
    else:
        ids = None
    report = audit(args.db, started_at=args.since, ended_at=args.until, request_ids=ids)
    payload: dict[str, Any] = {"audit": report}
    if records:
        payload["summary"] = summarize(records, report)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="经 HTTP 接口测量抽取与问答耗时；只读核对调用账本")
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract")
    ask = sub.add_parser("ask")
    for command in (extract, ask):
        command.add_argument("--base-url", required=True)
        command.add_argument("--username", required=True)
        command.add_argument("--password-env", required=True)
    extract.add_argument("--course-name", required=True)
    extract.add_argument("--file", required=True)
    extract.add_argument("--max-seconds", type=float, default=900)
    ask.add_argument("--course-id", required=True)
    ask.add_argument("--questions", required=True)
    ask.add_argument("--stream", action="store_true", help="走 SSE，另记客户端 SSE 首个 delta")
    ask.add_argument("--out", help="逐题结果追加写入的 JSONL")
    ask.add_argument("--audit-db", help="只读 SQLite：每题后按生成 token 检查增量止损")
    ask.add_argument("--cap", type=int, default=45_000, help="本轮生成 token 增量止损（只计生成，不含向量）")
    ask.add_argument("--round-started-at", help="整轮起点（ISO 8601，带时区）；一轮分多次调用 ask 时共用")
    audit_cmd = sub.add_parser("audit")
    audit_cmd.add_argument("--db", required=True)
    audit_cmd.add_argument("--records", help="ask 写出的 JSONL；未给时间窗口时按其中的请求 ID 关联")
    audit_cmd.add_argument("--request-ids", help="逗号分隔的固定请求 ID")
    audit_cmd.add_argument("--since", help="窗口起点（含），ISO 8601 且带时区")
    audit_cmd.add_argument("--until", help="窗口终点（不含），ISO 8601 且带时区")
    task_cmd = sub.add_parser("audit-task")
    task_cmd.add_argument("--db", required=True)
    task_cmd.add_argument("--task-id", required=True)
    task_cmd.add_argument("--client-elapsed-seconds", type=float, help="extract 输出的 elapsed_seconds")
    args = parser.parse_args(argv)
    if args.command == "extract":
        return cmd_extract(args)
    if args.command == "audit-task":
        print(json.dumps(audit_task(args.db, task_id=args.task_id, client_elapsed_seconds=args.client_elapsed_seconds),
                         ensure_ascii=False, indent=2))
        return 0
    return cmd_ask(args) if args.command == "ask" else cmd_audit(args)

if __name__ == "__main__":
    sys.exit(main())
