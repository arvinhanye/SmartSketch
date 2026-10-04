"""L11-2：本机 OpenAI 兼容假供应商——个人模式端到端用它证明接线（不证明模型质量）。

它包装演示模型 ``DemoModelClient``：HTTP 请求不带用途，按提示词中的判别标记推断。密钥 ``sk-fake-bad``
返回 401，用于「供应商拒绝密钥」用例；请求头 ``X-Fake-Delay`` 让响应先等待，用于超时用例。
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "fake_provider.py"


def _load():
    sys.path.insert(0, str(ROOT / "src" / "backend"))
    spec = importlib.util.spec_from_file_location("fake_provider", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def provider():
    port = _free_port()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src" / "backend"), "FAKE_PROVIDER_SLOW_SECONDS": "0.4"}
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}/health", timeout=0.2)
            break
        except OSError:
            time.sleep(0.05)
    else:
        proc.kill()
        pytest.fail("fake provider did not start")
    yield f"{base}/v1"
    proc.terminate()
    proc.wait(5)


def _post(base, key, body, headers=None):
    request = urllib.request.Request(
        f"{base}/chat/completions", json.dumps(body).encode(),
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **(headers or {})})
    return urllib.request.urlopen(request, timeout=10)


@pytest.mark.parametrize("prompt, purpose", [
    ("……<<资料 1>>（第 1 页）\n栈是……\n<<学生问题>>\n什么是栈？", "answer_with_context"),
    ("你是课程问答系统的检索问题改写器。请结合对话历史……", "rewrite_query"),
    ("实体表（JSON，每项含 id、name、type）：\n[]", "extract_relations"),
    ("已抽取知识点（JSON 数组，每项含 name 与 type）：\n[]", "extract_entities_gleaning"),
    ("知识点 A：栈\n知识点 B：堆栈", "judge_duplicate"),
    ("原文定义：\n[]", "summarize_definition"),
    ("请从下面的课程资料中抽取知识点……", "extract_entities"),
])
def test_infer_purpose_matches_prompt_marks(prompt, purpose):
    assert _load().infer_purpose(prompt) == purpose


def test_good_key_returns_a_compatible_completion(provider):
    reply = json.loads(_post(provider, "sk-fake-good", {
        "model": "fake-model", "max_tokens": 64, "stream": False,
        "messages": [{"role": "user", "content": "请从下面的课程资料中抽取知识点：栈是一种线性表。"}]}).read())
    choice = reply["choices"][0]
    assert choice["finish_reason"] in ("stop", "length") and isinstance(choice["message"]["content"], str)
    assert set(reply["usage"]) >= {"prompt_tokens", "completion_tokens"}


def test_stream_ends_with_usage_and_done(provider):
    raw = _post(provider, "sk-fake-good", {
        "model": "fake-model", "max_tokens": 64, "stream": True, "stream_options": {"include_usage": True},
        "messages": [{"role": "user", "content": "<<资料 1>>（第 1 页）\n栈是后进先出的线性表。\n<<学生问题>>\n什么是栈？"}]}).read()
    events = [line[len("data: "):] for line in raw.decode().splitlines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(event) for event in events[:-1]]
    assert any(chunk.get("usage") for chunk in chunks)
    assert any(choice.get("finish_reason") for chunk in chunks for choice in chunk.get("choices", []))


def test_bad_key_is_rejected_with_401(provider):
    with pytest.raises(urllib.error.HTTPError) as caught:
        _post(provider, "sk-fake-bad", {"model": "fake-model", "max_tokens": 8,
                                         "messages": [{"role": "user", "content": "x"}]})
    assert caught.value.code == 401


def test_slow_key_holds_every_response(provider):
    """sk-fake-slow：每次调用先等待 FAKE_PROVIDER_SLOW_SECONDS，供端到端在处理中点「取消」。"""
    started = time.monotonic()
    _post(provider, "sk-fake-slow", {"model": "fake-model", "max_tokens": 8,
                                      "messages": [{"role": "user", "content": "x"}]}).read()
    assert time.monotonic() - started >= 0.4


def test_delay_header_holds_the_response(provider):
    started = time.monotonic()
    _post(provider, "sk-fake-good", {"model": "fake-model", "max_tokens": 8, "messages": [{"role": "user", "content": "x"}]},
          headers={"X-Fake-Delay": "0.4"}).read()
    assert time.monotonic() - started >= 0.4


def test_project_client_streams_through_the_guarded_transport(provider):
    """项目自己的兼容客户端 + 个人模式的受控传输（放行回环）能完整读到流与 usage。"""
    from app.services.ai.client import Message, ModelAuthError, ModelRequest, StreamDone
    from app.services.ai.compatible import CompatibleModelClient
    from app.services.ai.outbound import GuardedTransport

    transport = GuardedTransport(allow_private=True)
    request = ModelRequest(purpose="answer_with_context", model="fake-model", max_output_tokens=256,
                           messages=(Message("user", "<<资料 1>>（第 1 页）\n栈是后进先出的线性表。\n<<学生问题>>\n什么是栈？"),))
    events = list(CompatibleModelClient(provider, "sk-fake-good", transport=transport).stream(request))
    done = events[-1]
    assert isinstance(done, StreamDone) and done.result.usage is not None and done.result.text
    with pytest.raises(ModelAuthError):
        CompatibleModelClient(provider, BAD, transport=transport).complete(request)


BAD = "sk-fake-bad"
