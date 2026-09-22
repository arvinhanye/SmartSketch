#!/usr/bin/env bash
# 契约门禁。由后端 Agent 维护（src/contracts/ 单一写入方，见 ADR-004）。
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ ! -d src/contracts/v1 ]]; then
  echo "  SKIP：契约真源尚未创建（M0-04a），没有 src/contracts/v1/"
  exit 0
fi

if [[ -x scripts/gen-contracts.sh ]]; then
  # ADR-004 强制规则：生成物必须与真源同步，重新生成后不得有 diff。
  scripts/gen-contracts.sh --check
else
  echo "  ! src/contracts/v1/ 已存在但缺少可执行的 scripts/gen-contracts.sh"
  echo "    按 ADR-004，生成物必须可重现校验；请补上该脚本。"
  exit 1
fi
