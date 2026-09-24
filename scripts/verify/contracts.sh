#!/usr/bin/env bash
# 契约门禁。由后端 Agent 维护（src/contracts/ 单一写入方，见 ADR-004）。
#
# 两道检查：
#   1. check_contracts.py —— 真源自身的结构与不变量。缺依赖时**失败**，不跳过。
#   2. gen-contracts.sh --check —— 生成物与真源是否同步。
#
# 为什么不再有「没初始化就 SKIP」分支：契约真源已经冻结，静默跳过就是假绿
# （codex 审查 R02）。
set -euo pipefail
cd "$(dirname "$0")/../.."

fail=0

# ── 1. 真源结构与不变量 ────────────────────────────────
python3 scripts/check_contracts.py || fail=1

# ── 2. 生成物与真源同步 ────────────────────────────────
# 缺生成器直接失败；契约已导入，不能再用骨架降级模式。
if [[ -x scripts/gen-contracts.sh ]]; then
  scripts/gen-contracts.sh --check || fail=1
else
  echo "  ✗ 缺少可执行的 scripts/gen-contracts.sh；按 ADR-004，生成物必须可重现校验" >&2
  fail=1
fi

# ── 3. 门禁自身的负向测试 ──────────────────────────────
# 门禁曾经在缺依赖时静默 exit 0（R02）。没有负向测试就察觉不到同类回归。
log="$(mktemp)"
trap 'rm -f -- "$log"' EXIT
if python3 tests/contracts/test_contracts.py > "$log" 2>&1; then
  echo "  ✓ 门禁负向测试 $(grep -c '✓' "$log") 项通过"
else
  echo "  ✗ 契约门禁负向测试未全绿：" >&2
  cat "$log" >&2
  fail=1
fi

# B08 公共错误、来源和身份安全契约回归。
if python3 -m pytest tests/contracts/test_b08.py -q; then
  echo '  ✓ B08 契约回归通过'
else
  echo '  ✗ B08 契约回归失败' >&2
  fail=1
fi

# B09 课程、资料和成员管理契约回归。
if python3 -m pytest tests/contracts/test_b09.py -q; then
  echo '  ✓ B09 契约回归通过'
else
  echo '  ✗ B09 契约回归失败' >&2
  fail=1
fi

exit "$fail"
