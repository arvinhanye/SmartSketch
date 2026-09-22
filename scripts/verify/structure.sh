#!/usr/bin/env bash
# 仓库结构门禁：必需文件清单（数据驱动）+ 少量结构性断言。
#
# 加必需文件请改 scripts/verify/manifests/<领域>.txt，不要改本脚本。
set -euo pipefail
cd "$(dirname "$0")/../.."

fail=0
note() { echo "  ✗ $*" >&2; fail=1; }

# ── 1. 必需文件清单 ────────────────────────────────────
total=0
for manifest in scripts/verify/manifests/*.txt; do
  domain="$(basename "$manifest" .txt)"
  count=0
  while IFS= read -r path; do
    path="${path%%#*}"; path="$(echo "$path" | xargs)"   # 去注释与首尾空白
    [[ -z $path ]] && continue
    count=$((count + 1)); total=$((total + 1))
    [[ -f $path ]] || note "缺少必需文件（$domain 清单）：$path"
  done < "$manifest"
  echo "  · $domain 清单：$count 项"
done
echo "  · 必需文件合计：$total 项"

# ── 2. JSON 可解析 ────────────────────────────────────
for json_file in .mcp.json .claude/settings.json; do
  python3 -m json.tool "$json_file" >/dev/null 2>&1 || note "JSON 无法解析：$json_file"
done

# ── 3. 个人配置不得入库 ────────────────────────────────
# 用 git check-ignore 判断实际效果，而不是 grep .gitignore 的某一行——
# 后者会因为规则换写法（目录形式、通配符、排序）而误报。
for private in .claude/settings.local.json .env; do
  git check-ignore -q "$private" || note "$private 未被 .gitignore 忽略"
done

# ── 4. 架构文档必须说明 PREREQUISITE 的 DAG 约束 ─────────
# 整文件不区分大小写地找两个独立标记，不锚定行首、行号或表格格式，
# 这样重排版或换行不会让门禁红掉（旧版 grep 'M0-01 | DONE' 就栽在这上面）。
arch=docs/architecture.md
grep -qiE 'PREREQUISITE' "$arch" || note "$arch 未提及 PREREQUISITE 关系"
grep -qiE 'DAG|无环|成环|有向无环' "$arch" || note "$arch 未说明 PREREQUISITE 的无环约束"

((fail == 0)) && echo "  ✓ 结构检查通过"
exit "$fail"
