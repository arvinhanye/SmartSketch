#!/usr/bin/env python3
"""L11-2：本机 OpenAI 兼容假供应商（只用于测试与端到端接线，不证明模型质量）。

包装演示模型 ``DemoModelClient``（确定性、无网络），以 ``POST /v1/chat/completions`` 提供兼容接口，
流式与非流式都支持。HTTP 请求不带用途，``infer_purpose`` 按提示词中的判别标记推断——标记取自
``prompts/*.yaml`` 与 ``app.services.ai.demo`` 本身，保证与演示规则一致。

测试约定：
- ``Authorization: Bearer sk-fake-bad`` → 401（供应商拒绝密钥）；其他非空 key 一律接受；
- ``Bearer sk-fake-slow`` → 每次调用先等待 ``FAKE_PROVIDER_SLOW_SECONDS``（缺省 3 秒），供端到端在处理中取消；
- 请求头 ``X-Fake-Delay: <秒>`` → 先等待再响应（链路超时用例）。

只监听 127.0.0.1；个人模式下须设 ``MODEL_ENDPOINT_ALLOW_PRIVATE=1`` 才能连到它（APP_ENV=production 禁止）。
用法：PYTHONPATH=src/backend python scripts/fake_provider.py --port 18900
"""

from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.services.ai.client import Message, ModelRequest, StreamDelta, StreamDone
from app.services.ai.demo import _KNOWN_MARK, _TABLE_MARK, DemoModelClient

BAD_KEY = "sk-fake-bad"
SLOW_KEY = "sk-fake-slow"
MAX_BODY_BYTES = 4 * 1024 * 1024


def infer_purpose(prompt: str) -> str:
    """提示词 → 用途（与 ``demo_respond`` 的分派键一致）。"""
    if "<<学生问题>>" in prompt:
        return "answer_with_context"
    if "检索问题改写器" in prompt:
        return "rewrite_query"
    if _TABLE_MARK in prompt:
        return "extract_relations"
    if _KNOWN_MARK in prompt:
        return "extract_entities_gleaning"
    if "知识点 A：" in prompt:
        return "judge_duplicate"
    if "原文定义：" in prompt:
        return "summarize_definition"
    return "extract_entities"


_client = DemoModelClient()


def _request_from(body: dict) -> ModelRequest:
    messages = tuple(Message(m["role"], m["content"]) for m in body["messages"])
    prompt = "\n".join(message.content for message in messages)
    limit = body.get("max_tokens") or body.get("max_completion_tokens") or 1024
    response_format = "json" if (body.get("response_format") or {}).get("type") == "json_object" else "text"
    return ModelRequest(purpose=infer_purpose(prompt), model=str(body.get("model") or "fake-model"),
                        messages=messages, max_output_tokens=int(limit), response_format=response_format)


def _usage(result) -> dict:
    usage = result.usage
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0}
    return {"prompt_tokens": usage.input_tokens, "completion_tokens": usage.output_tokens}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # noqa: D401 - 安静，避免刷屏
        pass

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body_bytes = self.rfile.read(min(length, MAX_BODY_BYTES))
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        key = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if not key or key == BAD_KEY:
            self._json(401, {"error": {"message": "invalid api key", "type": "authentication_error"}})
            return
        delay = float(self.headers.get("X-Fake-Delay") or 0)
        if key == SLOW_KEY:
            delay = max(delay, float(os.environ.get("FAKE_PROVIDER_SLOW_SECONDS") or 3))
        if delay > 0:
            time.sleep(min(delay, 120))
        try:
            body = json.loads(body_bytes)
            request = _request_from(body)
        except (ValueError, KeyError, TypeError):
            self._json(400, {"error": {"message": "bad request"}})
            return
        if body.get("stream"):
            self._stream(request)
        else:
            result = _client.complete(request)
            self._json(200, {"id": "fake", "object": "chat.completion", "model": request.model,
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": result.text},
                                          "finish_reason": result.finish_reason}],
                             "usage": _usage(result)})

    def _stream(self, request: ModelRequest) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def send(payload) -> None:
            text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            self.wfile.write(f"data: {text}\n\n".encode())
            self.wfile.flush()

        for event in _client.stream(request):
            if isinstance(event, StreamDelta):
                send({"model": request.model, "choices": [{"index": 0, "delta": {"content": event.text}}]})
            elif isinstance(event, StreamDone):
                result = event.result
                send({"model": request.model,
                      "choices": [{"index": 0, "delta": {}, "finish_reason": result.finish_reason}]})
                send({"model": request.model, "choices": [], "usage": _usage(result)})
        send("[DONE]")
        self.close_connection = True


def main() -> None:
    parser = argparse.ArgumentParser(description="本机 OpenAI 兼容假供应商（测试用）")
    parser.add_argument("--port", type=int, default=18900)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
