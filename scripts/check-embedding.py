#!/usr/bin/env python3
"""发 1 次真实向量请求，确认在线向量可用（L09，ADR-081）。只打印模型、维度与耗时，不打印 key 与向量。

用法（仓库根目录）：.venv/bin/python scripts/check-embedding.py
仓库根目录有 .env 时按字面值读入（不覆盖已在环境中的变量，不当 shell 脚本执行）。
退出码：0 成功；2 配置非法或不是 online；3 调用失败。
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from app.config import SettingsError, embedding_model_id, load_settings  # noqa: E402
from app.services.ai.client import EmbeddingRequest, ModelCallError  # noqa: E402
from app.services.ai.factory import build_embedding_client  # noqa: E402

_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _environment() -> dict[str, str]:
    values = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            match = _LINE.match(line.rstrip("\r"))
            if match and match.group(2).strip() and match.group(1) not in values:
                values[match.group(1)] = match.group(2).strip()
    return values


def main() -> int:
    if not os.environ.get("SSL_CERT_FILE"):
        try:  # python.org 的 macOS Python 常找不到根证书
            import certifi

            os.environ["SSL_CERT_FILE"] = certifi.where()
        except ImportError:
            pass
    try:
        settings = load_settings(_environment())
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 2
    if settings.EMBEDDING_MODE != "online":
        print(f"EMBEDDING_MODE={settings.EMBEDDING_MODE}，不是 online，未发请求", file=sys.stderr)
        return 2
    client = build_embedding_client(settings)
    started = time.monotonic()
    try:
        result = client.embed(EmbeddingRequest(model=embedding_model_id(settings), texts=("栈是后进先出的线性表",),
                                               dimensions=settings.EMBEDDING_DIMENSIONS))
    except ModelCallError as error:
        print(f"向量调用失败：{error.error_class.value}", file=sys.stderr)
        return 3
    print(f"ok model={result.model_responded or result.model_requested} "
          f"dimensions={len(result.vectors[0])} seconds={time.monotonic() - started:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
