"""C02 方案 B 前置：思考控制参数探测工具（`evaluation/probe_thinking.py`），全部离线。

探测直连供应商，不经应用，所以调用**不会**进入 `model_calls`：工具必须自带预算——发出前按「已用 + 输入估算 +
输出上限」判断，超出即停；并逐变体记录 HTTP 状态、是否被接受、usage（含推理 token）、推理字数、可见字数、耗时。
密钥只从环境变量读取，永不写进输出或报错。
"""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("probe_thinking", ROOT / "evaluation/probe_thinking.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

KEY = "sk-PROBE-SECRET-DO-NOT-PRINT"


class _Provider:
    """假供应商：`enable_thinking=false` 关闭推理；`reasoning_effort` 不认识，返回 400；其余照常推理。"""

    def __init__(self):
        self.bodies: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.bodies.append({"auth": self.headers.get("Authorization"), **body})
                if "reasoning_effort" in body:
                    return self._send(400, {"error": {"code": "invalid_parameter", "type": "invalid_request_error",
                                                      "message": f"unknown field reasoning_effort {KEY[:3]}"}})
                thinking = body.get("enable_thinking", True) is not False
                message = {"role": "assistant", "content": '{"entities":["栈"]}'}
                details = {}
                if thinking:
                    message["reasoning_content"] = "先想一想" * 50
                    details = {"reasoning_tokens": 180}
                usage = {"prompt_tokens": 60, "completion_tokens": (200 if thinking else 20),
                         "completion_tokens_details": details}
                self._send(200, {"model": body["model"], "usage": usage,
                                 "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]})

            def _send(self, status, payload):
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("PROBE_KEY", KEY)
    fake = _Provider()
    yield fake
    fake.server.shutdown()


def _run(provider, capsys, *extra):
    code = probe.main(["--base-url", provider.base, "--model", "m1", "--key-env", "PROBE_KEY", "--allow-http", *extra])
    out = capsys.readouterr().out
    return code, [json.loads(line) for line in out.splitlines() if line.strip()], out


def test_each_variant_is_recorded_with_acceptance_usage_and_reasoning(provider, capsys):
    code, lines, out = _run(provider, capsys, "--variants", "baseline,enable_thinking_false,reasoning_effort_low")
    assert code == 0
    rows = {row["variant"]: row for row in lines if "variant" in row}
    assert rows["baseline"]["accepted"] is True
    assert (rows["baseline"]["usage_output"], rows["baseline"]["reasoning_tokens"]) == (200, 180)
    assert rows["baseline"]["reasoning_chars"] == 200 and rows["baseline"]["content_chars"] > 0
    assert rows["enable_thinking_false"]["accepted"] is True
    assert (rows["enable_thinking_false"]["reasoning_tokens"], rows["enable_thinking_false"]["reasoning_chars"]) == (None, 0)
    assert rows["reasoning_effort_low"]["accepted"] is False and rows["reasoning_effort_low"]["http_status"] == 400
    assert rows["reasoning_effort_low"]["error_code"] == "invalid_parameter"
    summary = lines[-1]["summary"]
    assert summary["tokens_used"] == 260 + 80              # 被拒的请求没有 usage，不计
    assert KEY not in out                                  # 密钥不出现在任何输出里


def test_requests_carry_the_variant_fields_and_a_bounded_max_tokens(provider, capsys):
    _run(provider, capsys, "--variants", "thinking_disabled,chat_template_enable_thinking_false", "--max-tokens", "256")
    first, second = provider.bodies
    assert first["thinking"] == {"type": "disabled"} and first["max_tokens"] == 256
    assert second["chat_template_kwargs"] == {"enable_thinking": False}
    assert first["auth"] == f"Bearer {KEY}" and first["stream"] is False


def test_budget_is_checked_before_each_call_with_the_worst_case(provider, capsys):
    # 每次最坏 = 输入估算 + 512；上限只够第一次（第一次实际用 260，再加一次最坏就超）
    cap = probe.input_estimate() + 512 + 100
    code, lines, _ = _run(provider, capsys, "--variants", "baseline,enable_thinking_false", "--cap", str(cap))
    assert code == 3
    assert [row["variant"] for row in lines if "variant" in row] == ["baseline"]
    assert "预算" in lines[-1]["summary"]["stopped"]
    assert len(provider.bodies) == 1


def test_unknown_usage_counts_as_worst_case(monkeypatch):
    used = probe.charge(0, {"usage_input": None, "usage_output": None}, input_estimate=100, max_tokens=512)
    assert used == 612
    assert probe.charge(10, {"usage_input": 60, "usage_output": 200}, input_estimate=100, max_tokens=512) == 270


def test_plain_http_is_refused_without_the_test_flag(provider, capsys):
    with pytest.raises(SystemExit):
        probe.main(["--base-url", provider.base, "--model", "m1", "--key-env", "PROBE_KEY"])
    assert provider.bodies == []


def test_missing_key_env_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("PROBE_KEY", raising=False)
    with pytest.raises(SystemExit):
        probe.main(["--base-url", "https://example.invalid/v1", "--model", "m1", "--key-env", "PROBE_KEY"])


def test_unknown_variant_is_rejected(provider):
    with pytest.raises(SystemExit):
        probe.main(["--base-url", provider.base, "--model", "m1", "--key-env", "PROBE_KEY", "--allow-http",
                    "--variants", "nope"])
