#!/usr/bin/env bash
# K11 前端门禁：类型检查 → vitest 全量（JUnit 报告判定：零测试、失败、skip/todo 均失败）→ 构建。
# 用法：scripts/verify/frontend.sh [模式，缺省 full]；需先 npm ci --prefix src/frontend。
set -euo pipefail
cd "$(dirname "$0")/../.."
mode="${1:-full}"
py="${PYTHON:-}"
if [[ -z $py ]]; then
  if [[ -x .venv/bin/python ]]; then py=.venv/bin/python; else py=python3; fi
fi
if [[ ! -d src/frontend/node_modules ]]; then
  echo "FAIL frontend gate: 缺 src/frontend/node_modules，先 npm ci --prefix src/frontend" >&2
  exit 1
fi
out="$(mktemp -d)"
trap 'rm -rf -- "$out"' EXIT

status=0
npm --prefix src/frontend run type-check || status=$?
# B02 的嵌套进程用例在慢机器上会超过缺省 5 秒（已知，见 docs/tasks.md 集成批次记录）
npm --prefix src/frontend run test -- --run --testTimeout 30000 \
  --reporter=default --reporter=junit --outputFile.junit="$out/frontend.xml" || status=$?
"$py" scripts/verify/gate.py frontend "$mode" "$out/frontend.xml" --min-tests 100 || status=1
npm --prefix src/frontend run build || status=$?
exit "$status"
