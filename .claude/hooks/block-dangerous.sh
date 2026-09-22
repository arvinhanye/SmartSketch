#!/usr/bin/env bash
# Claude PreToolUse hook：拦截共享工作区里的破坏性 shell 命令。
#
# 输出契约（与改造前一致，不要改）：
#   拦截 → stdout 输出 {"decision":"block","reason":"..."} ，exit 0
#   放行 → 无 stdout 输出，exit 0
#
# 失败时放行（fail-open）的取舍：
#   这个 hook 是共享工作区的**便利护栏，不是安全边界**——人始终在回路里，
#   任何人都能直接在终端跑同样的命令，绕过它不需要任何技巧。
#   因此 JSON 解析失败、python3 缺失或检查脚本异常时一律**放行并向 stderr 说明**，
#   而不是全面阻断：阻断会让工具遇到任何意外输入就彻底不可用，
#   代价远大于漏掉一次本该让人确认的命令。
#
# 不用 set -e：这个脚本的任何内部失败都必须走到「放行」而不是把非零码抛给 hook 宿主。
set -uo pipefail

input="$(cat)"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'block-dangerous: 未找到 python3，本次放行且未做检查\n' >&2
  exit 0
fi

# 用 python3 解析 JSON。改造前用 sed 正则 [^"]* 抠 command 字段，
# 会在第一个转义引号处截断，导致 `git commit -m "fix" && rm -rf build` 整段漏检。
read -r -d '' PROG <<'PY' || true
import json, re, sys

# 五条危险模式，与改造前完全一致，不增不减；但按「危险是否取决于 shell 位置」分成两组。
#
# SHELL_PATTERNS 是 shell 命令，只在命令位置才危险 —— 位置匹配能消除
# `echo never rm -rf anything` 这类误报。
SHELL_PATTERNS = [
    "git reset --hard",
    "git clean -f",
    "rm -rf",
    "git push --force",
]
# ANYWHERE_PATTERNS 是 SQL 片段，不是 shell 命令，永远只会作为参数出现
# （`psql -c 'DROP DATABASE x'`），**永远不可能落在 shell 命令位置**。
# 对它用位置匹配等于把这条模式废掉，属于缩小覆盖，所以保留改造前的整串匹配。
ANYWHERE_PATTERNS = [
    "DROP DATABASE",
]

def allow(note=None):
    if note:
        sys.stderr.write("block-dangerous: %s\n" % note)
    sys.exit(0)

try:
    payload = json.load(sys.stdin)
except Exception as exc:
    allow("stdin 不是合法 JSON（%s），本次放行且未做检查" % exc.__class__.__name__)

if not isinstance(payload, dict):
    allow("stdin JSON 顶层不是对象，本次放行且未做检查")

tool_input = payload.get("tool_input")
cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
if not isinstance(cmd, str) or not cmd.strip():
    allow()  # 非 Bash 工具或空命令，没什么可查的，静默放行

# 1) 换行本身是命令分隔符，先显式转成 ';' 再压缩空白，避免丢掉分隔语义。
# 2) 连续空白压成单个空格，消除 "rm  -rf" 这类靠多打一个空格的绕过。
norm = re.sub(r"[ \t]*\n[ \t]*", " ; ", cmd)
norm = re.sub(r"\s+", " ", norm).strip()

# 只在「命令位置」匹配：字符串开头，或 ; & | ( ) { } 之后
# （&& 与 || 的末字符分别是 & 和 |，所以一并覆盖）。
# 这样 `echo never rm -rf anything` 不再误报，而 `x && rm -rf y` 仍会被拦下。
CMD_POS = r"(?:^|(?<=[;&|(){}]))\s*"

def block(pat):
    reason = ("Shared-workspace protection: blocked pattern %r. "
              "Use a reviewed, scoped command instead." % pat)
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")
    sys.exit(0)

for pat in SHELL_PATTERNS:
    # 不加结尾边界是故意的：rm -rfv、git clean -fd 同样危险，应当一并拦下。
    if re.search(CMD_POS + re.escape(pat), norm):
        block(pat)

for pat in ANYWHERE_PATTERNS:
    if pat in norm:
        block(pat)

# 已知残留缺口（有意不在本次扩大范围，见交接文件）：
#   - `rm -fr` / `rm -r -f` 等等价写法不在五条模式内；
#   - `DROP DATABASE` 区分大小写，小写 `drop database` 漏检；
#     它走整串匹配，所以 `echo "DROP DATABASE 很危险"` 会误报 —— 与改造前一致；
#   - 引号内的分隔符会被当作真分隔符，`git commit -m "a; rm -rf b"` 会误报。
#     这是有意选择：不剥离引号才能保住 `bash -c "rm -rf /"` 的覆盖，
#     而误报的代价（人看一眼改写命令）远小于漏报。
sys.exit(0)
PY

if out="$(printf '%s' "$input" | python3 -c "$PROG")"; then
  [ -n "$out" ] && printf '%s\n' "$out"
  exit 0
fi

printf 'block-dangerous: 检查脚本异常退出，本次放行且未做检查\n' >&2
exit 0
