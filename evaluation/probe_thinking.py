#!/usr/bin/env python3
"""C02 方案 B 前置：探测 OpenAI 兼容供应商接受哪种「关闭 / 降低思考」参数（只用标准库）。

背景：C03-1 实测抽取输出 80% 是推理，推理还会用满输出上限导致截断与 repair（`docs/reviews/claude-deepseek-c02-4-c03-1.md`）。
不同供应商关闭思考的字段不同，不猜：逐个变体发同一个小请求，记录是否被接受、usage（含
``completion_tokens_details.reasoning_tokens``）、推理字数（``reasoning_content`` / ``reasoning``）、可见字数与耗时。

边界：
- 直连供应商，不经应用，调用**不进** ``model_calls``；预算由本工具自管：每次发出前按「已用 + 输入估算 + 输出上限」检查，
  超过 ``--cap`` 即停（退出码 3）。usage 缺失按最坏情况（输入估算 + 输出上限）计；生成前被拒（400/401/403/404/413/422/429）
  按系统规则计 0（``docs/integrations.md``「调用记录」第 5 条）。
- 密钥只从 ``--key-env`` 指定的环境变量读取，不出现在命令行、输出或错误里；只允许 https（``--allow-http`` 仅供本机测试）。
- 非流式、不重试；提示词固定、很短，结果只说明参数是否生效，不代表抽取质量。

用法::

    PROBE_KEY=... python evaluation/probe_thinking.py --base-url https://<供应商>/v1 --model <模型> \\
        --key-env PROBE_KEY --cap 5000 > evaluation/raw/c02b/probe.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

#: 变体名 → 追加到请求体的字段。``baseline`` 不加任何字段，作为对照。
VARIANTS: dict[str, dict[str, Any]] = {
    "baseline": {},
    "thinking_disabled": {"thinking": {"type": "disabled"}},
    "enable_thinking_false": {"enable_thinking": False},
    "chat_template_enable_thinking_false": {"chat_template_kwargs": {"enable_thinking": False}},
    "reasoning_effort_low": {"reasoning_effort": "low"},
}
DEFAULT_VARIANTS = tuple(VARIANTS)

PROMPT = (
    "从下面这句课程资料中抽取知识点，只输出 JSON，格式为 {\"entities\": [{\"name\": 名称, \"type\": 类型}]}，"
    "类型取 concept、method、example 之一。\n资料：栈是只允许在一端进行插入和删除操作的线性表，具有后进先出的特点。"
)
REJECTED_BEFORE_GENERATION = frozenset({400, 401, 403, 404, 413, 422, 429})
MESSAGE_OVERHEAD = 32


def input_estimate() -> int:
    """与应用 E03 同口径的偏大估算：UTF-8 字节数 + 固定开销。"""
    return len(PROMPT.encode("utf-8")) + MESSAGE_OVERHEAD


def charge(used: int, row: dict[str, Any], *, input_estimate: int, max_tokens: int) -> int:
    """把一次调用计入已用：有 usage 计真实值；生成前被拒计 0；其余（无 usage、无响应、5xx）按最坏情况计。"""
    if row.get("usage_input") is not None and row.get("usage_output") is not None:
        return used + row["usage_input"] + row["usage_output"]
    if row.get("http_status") in REJECTED_BEFORE_GENERATION:
        return used
    return used + input_estimate + max_tokens


def _reasoning_chars(message: dict[str, Any]) -> int:
    return sum(len(text) for name in ("reasoning_content", "reasoning")
               if isinstance(text := message.get(name), str))


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def call_variant(base_url: str, key: str, model: str, variant: str, *, max_tokens: int, timeout: float) -> dict[str, Any]:
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": max_tokens,
            "stream": False, **VARIANTS[variant]}
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {key}")
    row: dict[str, Any] = {"variant": variant, "fields": VARIANTS[variant], "http_status": None, "accepted": False,
                           "error_code": None, "error_type": None, "usage_input": None, "usage_output": None,
                           "reasoning_tokens": None, "reasoning_chars": None, "content_chars": None,
                           "finish_reason": None, "latency_ms": None}
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read() or b"{}")
            row["http_status"] = response.status
    except urllib.error.HTTPError as error:
        row["http_status"] = error.code
        try:
            detail = (json.loads(error.read() or b"{}").get("error") or {})
        except ValueError:
            detail = {}
        # 只留错误码与类型，不回显供应商原文（可能夹带请求内容）
        row["error_code"] = detail.get("code") if isinstance(detail, dict) else None
        row["error_type"] = detail.get("type") if isinstance(detail, dict) else None
        row["latency_ms"] = round((time.monotonic() - started) * 1000)
        return row
    except (urllib.error.URLError, TimeoutError) as error:
        row["error_type"] = type(error).__name__
        row["latency_ms"] = round((time.monotonic() - started) * 1000)
        return row
    row["latency_ms"] = round((time.monotonic() - started) * 1000)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    first = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    row.update(accepted=True, usage_input=_count(usage.get("prompt_tokens")), usage_output=_count(usage.get("completion_tokens")),
               reasoning_tokens=_count(details.get("reasoning_tokens")), reasoning_chars=_reasoning_chars(message),
               content_chars=len(content) if isinstance(content, str) else None, finish_reason=first.get("finish_reason"))
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="探测供应商接受的思考控制参数（直连，自管预算）")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--key-env", required=True, help="保存密钥的环境变量名")
    parser.add_argument("--variants", default=",".join(DEFAULT_VARIANTS), help="逗号分隔；可选：" + ",".join(VARIANTS))
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--cap", type=int, default=5000, help="本轮 token 上限（输入 + 输出，含推理）")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--allow-http", action="store_true", help="仅供本机测试")
    args = parser.parse_args(argv)

    variants = [v for v in args.variants.split(",") if v]
    unknown = [v for v in variants if v not in VARIANTS]
    if unknown:
        raise SystemExit(f"未知变体：{', '.join(unknown)}")
    if not args.base_url.startswith("https://") and not args.allow_http:
        raise SystemExit("只允许 https 供应商地址")
    key = os.environ.get(args.key_env, "")
    if not key:
        raise SystemExit(f"环境变量 {args.key_env} 未设置")

    estimate = input_estimate()
    used, stopped = 0, None
    for variant in variants:
        if used + estimate + args.max_tokens > args.cap:
            stopped = f"预算：已用 {used}，再发一次最坏 {estimate + args.max_tokens}，将超过上限 {args.cap}"
            break
        row = call_variant(args.base_url, key, args.model, variant, max_tokens=args.max_tokens, timeout=args.timeout)
        used = charge(used, row, input_estimate=estimate, max_tokens=args.max_tokens)
        print(json.dumps(row, ensure_ascii=False))
    print(json.dumps({"summary": {"model": args.model, "tokens_used": used, "cap": args.cap, "stopped": stopped,
                                  "note": "直连供应商，未计入 model_calls；请手工计入预算台账"}}, ensure_ascii=False))
    return 3 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
