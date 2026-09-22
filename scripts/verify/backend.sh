#!/usr/bin/env bash
# 后端门禁。由后端 Agent 维护——其他人请改自己领域的脚本。
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -f src/backend/pyproject.toml && ! -f src/backend/requirements.txt ]]; then
  echo "  SKIP：后端尚未初始化（M0-03），没有 pyproject.toml / requirements.txt"
  exit 0
fi

# ── 预留调用点：M0-03 落地后把下面几行换成真实命令（S-04 预留）──
# pytest tests/backend -q            # 用例见 tests/backend/README.md
# ruff check src/backend
# mypy src/backend

echo "  ! 后端已初始化，但门禁仍是占位实现。"
echo "    后端 Agent 请启用本文件的预留调用点：pytest tests/backend、ruff、mypy。"
