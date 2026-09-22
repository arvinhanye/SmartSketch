#!/usr/bin/env bash
# 后端门禁。由后端 Agent 维护——其他人请改自己领域的脚本。
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -f src/backend/pyproject.toml && ! -f src/backend/requirements.txt ]]; then
  echo "  SKIP：后端尚未初始化（M0-03），没有 pyproject.toml / requirements.txt"
  exit 0
fi

echo "  ! 后端已初始化，但门禁仍是占位实现。"
echo "    后端 Agent 请在本文件补上：pytest、类型检查、lint。"
