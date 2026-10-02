#!/usr/bin/env python3
"""经真实 HTTP 接口测量抽取与问答耗时（L02、L16）。只用标准库；不读也不打印任何密钥。

计时边界（docs/superpowers/specs/2026-10-02-contest-sprint-design.md 第 5 节）：

- ``extract``：发出上传请求 → 任务快照 ``stage`` 进入 ``awaiting_review`` / ``failed`` / ``cancelled``。
  含排队、解析、分块、抽取、直通融合与入库。每 0.5 秒轮询一次，读数误差不超过一个轮询间隔。
- ``ask``：发出问答请求 → 收到完整 JSON 响应；同时记录服务端 ``latency_ms``。首字耗时在
  ``chat_logs.first_delta_latency_ms``，由调用方另行查询。

口令从 ``--password-env`` 指定的环境变量读取，不出现在命令行参数里。

用法（仓库根目录）::

    python evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:8001 \\
        --username demo_teacher --password-env MEASURE_PASSWORD --course-name "基线" --file path/to/chapter.md
    python evaluation/measure_web_flow.py ask --base-url http://127.0.0.1:8001 \\
        --username demo_student --password-env MEASURE_PASSWORD --course-id <cid> --questions questions.txt

``extract`` 输出一行 JSON，任务到达 ``awaiting_review`` 时退出码为 0，否则为 1；``ask`` 每题输出一行 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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


def cmd_ask(args: argparse.Namespace) -> int:
    token = login(args.base_url, args.username, args.password_env)
    questions = [line.strip() for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]
    for question in questions:
        started = time.monotonic()
        status, body = call(args.base_url, "POST", f"/api/v1/courses/{args.course_id}/chat", token=token,
                            body=json.dumps({"question": question}).encode(), timeout=60)
        elapsed = round(time.monotonic() - started, 2)
        body = body or {}
        reason = body.get("reason") or (body.get("details") or {}).get("reason")
        print(json.dumps({"question": question, "http_status": status,
                          "status": body.get("status") or body.get("code"), "reason": reason,
                          "elapsed_seconds": elapsed, "latency_ms": body.get("latency_ms"),
                          "citations": len(body.get("citations") or [])}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="经 HTTP 接口测量抽取与问答耗时")
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
    args = parser.parse_args(argv)
    return cmd_extract(args) if args.command == "extract" else cmd_ask(args)


if __name__ == "__main__":
    sys.exit(main())
