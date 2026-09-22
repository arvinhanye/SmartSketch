#!/usr/bin/env bash
# 质量门禁分发器：只负责依次调用 scripts/verify/ 下的子脚本。
#
# 不要把具体检查写进本文件——各领域 Agent 应该只改自己的子脚本和清单，
# 避免所有人抢改同一个文件（AGENTS.md §3「写争用规则」）。
set -euo pipefail
cd "$(dirname "$0")/.."

CHECKS=(structure backend frontend contracts)
failed=()

for check in "${CHECKS[@]}"; do
  script="scripts/verify/${check}.sh"
  [[ -f $script ]] || { echo "缺少子脚本：$script" >&2; exit 1; }
  printf '\n──── verify: %s ────\n' "$check"
  # 跑完全部再汇总，而不是首错即停：一次就能看到所有问题。
  if ! bash "$script"; then
    failed+=("$check")
  fi
done

printf '\n────────────────────\n'
if ((${#failed[@]})); then
  printf '验证失败：%s\n' "${failed[*]}" >&2
  exit 1
fi
echo 'All verification checks passed.'
