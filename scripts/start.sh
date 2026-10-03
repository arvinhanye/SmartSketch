#!/usr/bin/env bash
# 正式入口：个人模型 API（LLM_MODE=personal，ADR-080）+ 在线向量（ADR-081）。
# 演示入口见 scripts/start-demo.sh（不联网的演示模型）。用法：scripts/start.sh [--no-open]
set -euo pipefail
exec "$(dirname "$0")/start-demo.sh" --personal "$@"
