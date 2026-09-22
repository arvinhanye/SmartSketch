#!/usr/bin/env bash
# 前端门禁。由前端 Agent 维护——其他人请改自己领域的脚本。
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -f src/frontend/package.json ]]; then
  echo "  SKIP：前端尚未初始化（M0-02），没有 package.json"
  exit 0
fi

echo "  ! 前端已初始化，但门禁仍是占位实现。"
echo "    前端 Agent 请在本文件补上：vue-tsc 类型检查、单元测试、lint。"
