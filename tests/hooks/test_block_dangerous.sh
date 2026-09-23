#!/usr/bin/env bash
# 回归测试：.claude/hooks/block-dangerous.sh 必须检查完整命令，且无法解析输入时拒绝。
# 背景：钩子曾用正则从原始 JSON 截取 command，遇到命令里第一个双引号（JSON 中是 \"）就截断，
# 引号之后的危险命令全部放行；解析失败时 command 为空，同样放行。
# 用法：tests/hooks/test_block_dangerous.sh；退出码 0 = 全部通过。依赖：bash、python3。
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
hook="$root/.claude/hooks/block-dangerous.sh"
fail=0

# 按 Claude Code 的 PreToolUse 输入格式编码；$2 = compact（与 JSON.stringify 一致）或 spaced
payload() {
  python3 - "$1" "${2:-compact}" <<'PY'
import json, sys
command, style = sys.argv[1], sys.argv[2]
data = {"session_id": "t", "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": command, "description": "t"}}
separators = (",", ":") if style == "compact" else (", ", ": ")
print(json.dumps(data, ensure_ascii=(style != "compact"), separators=separators))
PY
}

# stdin = 钩子输入；打印钩子的决定：block / allow；钩子输出不是合法 JSON 时打印 invalid-output
decision() {
  local out
  out="$("$hook")" || { echo "hook-exit-$?"; return 0; }
  python3 -c '
import json, sys
s = sys.stdin.read().strip()
try:
    print(json.loads(s).get("decision", "allow") if s else "allow")
except ValueError:
    print("invalid-output")
' <<<"$out"
}

# 注意：expect 必须在当前 shell 执行（用重定向喂输入，不能放在管道右侧），
# 否则 fail=1 只改了子 shell 的变量，脚本会在有 FAIL 时仍然 exit 0。
expect() { # $1 = 期望 block|allow，$2 = 用例名；stdin = 钩子输入
  local got
  got="$(decision)"
  if [[ "$got" == "$1" ]]; then
    echo "PASS  $2"
  else
    echo "FAIL  $2（期望 $1，实际 $got）"
    fail=1
  fi
}

must_block() { local input; input="$(payload "$2" "${3:-compact}")"; expect block "$1" <<<"$input"; }
must_allow() { local input; input="$(payload "$2" "${3:-compact}")"; expect allow "$1" <<<"$input"; }

# 基线：危险命令在最前面（修复前也能拦住）
must_block "rm -rf 在开头"                  'rm -rf /tmp/smartsketch-hook-test'
# 回归：危险命令前出现双引号（修复前全部放行）
must_block "引号之后的 rm -rf"              'echo "hi" && rm -rf /tmp/smartsketch-hook-test'
must_block "引号之后的 git reset --hard"    'git commit -m "wip" && git reset --hard HEAD~1'
must_block "引号之后的 git clean -f"        'echo "x" && git clean -fd'
must_block "引号之后的 git push --force"    'echo "x"; git push --force origin main'
must_block "引号内的 DROP DATABASE"         'sqlite3 dev.db "DROP DATABASE demo"'
must_block "中文引号内容之后的 reset"       'git commit -m "中文说明" && git reset --hard'
must_block "多行命令的后续行"               $'echo "step 1"\nrm -rf /tmp/smartsketch-hook-test'
must_block "带空格的 JSON 格式"             'echo "x" && rm -rf /tmp/smartsketch-hook-test' spaced
# 输入无法解析时必须拒绝（fail-closed），不能因为看不懂输入就放行
expect block "输入不是 JSON" <<<'not json'
expect block "输入为空" </dev/null
# 正常命令不得误拦
must_allow "普通命令"                       'git status'
must_allow "含引号的普通命令"               'git commit -m "docs: 更新交接"'
expect allow "没有 command 字段" <<<'{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}'

if [[ "$fail" -ne 0 ]]; then
  echo "block-dangerous hook tests FAILED" >&2
  exit 1
fi
echo "block-dangerous hook tests passed."
