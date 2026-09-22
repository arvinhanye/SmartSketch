#!/usr/bin/env bash
# 前端门禁。由前端 Agent 维护——其他人请改自己领域的脚本。
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -f src/frontend/package.json ]]; then
  echo "  SKIP：前端尚未初始化（M0-02），没有 package.json"
  exit 0
fi

# ── 预留调用点：M0-02 落地后把下面几行换成真实命令（S-04 预留）──
# npm --prefix src/frontend run type-check     # vue-tsc
# npm --prefix src/frontend run test -- tests/frontend
# npm --prefix src/frontend run lint

echo "  ! 前端已初始化，但门禁仍是占位实现。"
echo "    前端 Agent 请启用本文件的预留调用点：vue-tsc、单元测试、lint。"
