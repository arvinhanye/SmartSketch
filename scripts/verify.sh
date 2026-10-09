#!/usr/bin/env bash
# 单一质量门禁入口（K11）。模式由参数或 VERIFY_MODE 指定：
#   basic（缺省）：仓库骨架、钩子回归、契约门禁——快，CI「Repository scaffold」任务运行它。
#   full：basic + scripts/verify/backend.sh + scripts/verify/frontend.sh（全量测试并判定报告：
#         零测试、失败、未登记的 SKIP 都判失败，登记表见 scripts/verify/allowed-skips.txt）。
#   integration：full + scripts/verify/integration.sh（一次性 Neo4j 上的集成用例 + K05/K06 端到端）。
# 任一步失败都以非 0 退出；不存在「跳过也算过」的分支。
# 用法：scripts/verify.sh [basic|full|integration]
set -euo pipefail
mode="${1:-${VERIFY_MODE:-basic}}"
case "$mode" in
  basic|full|integration) ;;
  *) echo "Unknown verify mode: $mode (expected basic, full or integration)" >&2; exit 2 ;;
esac
required=(
  AGENTS.md CLAUDE.md README.md .gitignore .mcp.json .env.example
  .claude/settings.json .claude/rules/frontend.md .claude/rules/backend.md .claude/rules/testing.md
  .claude/hooks/notify-macos.sh .claude/hooks/block-dangerous.sh
  docs/product.md docs/architecture.md docs/decisions.md docs/tasks.md docs/integrations.md docs/handoffs/README.md
  specs/course-knowledge-graph.md
  src/README.md src/frontend/README.md src/backend/README.md src/backend/app/__init__.py src/contracts/README.md
)
for path in "${required[@]}"; do [[ -f "$path" ]] || { echo "Missing required file: $path" >&2; exit 1; }; done
for json_file in .mcp.json .claude/settings.json; do python3 -m json.tool "$json_file" >/dev/null || { echo "Invalid JSON: $json_file" >&2; exit 1; }; done
grep -qxF '.claude/settings.local.json' .gitignore || { echo 'settings.local.json is not ignored' >&2; exit 1; }
grep -q 'M0-01 | DONE' docs/tasks.md || { echo 'M0-01 task status is not recorded' >&2; exit 1; }
grep -q 'PREREQUISITE' docs/architecture.md || { echo 'Graph prerequisite constraint is undocumented' >&2; exit 1; }
hook_tests="$(tests/hooks/test_block_dangerous.sh 2>&1)" || { printf '%s\n' "$hook_tests" >&2; echo 'block-dangerous hook regression tests failed' >&2; exit 1; }
tail -n 1 <<<"$hook_tests"
scripts/verify/contracts.sh
echo 'Scaffold verification passed.'
[[ $mode == basic ]] && exit 0

failed=()
scripts/verify/startup.sh || failed+=(startup)
# integration 档的图库用例由 integration.sh 在一次性 Neo4j 上执行，这里按 full 判定后端报告。
scripts/verify/backend.sh full || failed+=(backend)
scripts/verify/frontend.sh "$mode" || failed+=(frontend)
if [[ $mode == integration ]]; then
  scripts/verify/integration.sh || failed+=(integration)
fi
if ((${#failed[@]})); then
  echo "Verification ($mode) FAILED: ${failed[*]}" >&2
  exit 1
fi
echo "Verification ($mode) passed."
