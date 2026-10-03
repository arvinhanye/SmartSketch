#!/usr/bin/env bash
# 一键启动演示环境（方式 B 的自动化版本，docs/runbook.md §2）：
#   依赖检查/安装 → .env → Neo4j → 迁移 → 演示账号 → API + worker → 演示课程导入 → 前端。
# 缺省用演示模型（LLM_MODE=demo、EMBEDDING_MODE=demo，ADR-076）：不联网、不产生费用。
# --live 改用 .env 里配置的真实大模型（LLM_MODE=live，D-02a DeepSeek）抽取与问答：按量计费。
#
# 可重复执行：已装的依赖、已有的 .env、已建的账号与已导入的课程都会复用，不会重复或覆盖。
# Ctrl+C 停止 API、worker 与前端；Neo4j 保持运行以免下次冷启动，停止用 scripts/dev-down.sh。
#
# 用法：scripts/start-demo.sh [--live | --personal] [--no-import] [--no-open]
#   --live       真实大模型：须在 .env 填 LLM_API_KEY；向量沿用演示向量（.env 为 online 时用真实向量）。
#                不导入演示课程（首次导入会付费抽取整套示例资料），教师上传资料时才调用模型
#   --personal   正式模式：LLM_MODE=personal（个人模型 API，ADR-080）+ 在线向量；不导入演示课程
#   --no-import  不执行演示课程导入（scripts/import-demo.py）
#   --no-open    启动后不自动打开浏览器
# 环境变量：SEED_DEMO_PASSWORD（首次建演示账号用的口令，缺省 smartsketch-demo）、
#           DEMO_WEB_PORT（前端端口，缺省 5173）、DEMO_QA_SIMILARITY_THRESHOLD（缺省 0.58）。
# 日志：.demo/logs/{api,worker,web,import}.log
#
# 兼容 macOS 自带的 bash 3.2：不用 wait -n、关联数组，空数组展开前先判断长度。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"   # 切到仓库根目录，提供 die / env_setting

do_import=1
open_browser=1
live=0
personal=0
for arg in "$@"; do
  case "$arg" in
    --live) live=1 ;;
    --personal) personal=1 ;;
    --no-import) do_import=0 ;;
    --no-open) open_browser=0 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "未知选项 ${arg}。用法：$0 [--live | --personal] [--no-import] [--no-open]" ;;
  esac
done
if ((live)) && ((personal)); then
  die "--live 与 --personal 不能同时使用"
fi
((live)) && do_import=0
((personal)) && do_import=0

LOG_DIR="$REPO_ROOT/.demo/logs"
mkdir -p "$LOG_DIR"
step() { printf '\n→ %s\n' "$*"; }

# ---------------------------------------------------------------- 1. Python 与前端依赖
PY="$REPO_ROOT/.venv/bin/python"
if [[ ! -x $PY ]]; then
  base=""
  for candidate in python3.12 python3.11 python3; do
    path="$(command -v "$candidate" 2>/dev/null || true)"
    [[ -n $path ]] || continue
    case "$path" in *conda*) continue ;; esac   # anaconda 的 Python 证书与编译环境常出问题，跳过
    if "$path" -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)' 2>/dev/null; then
      base="$path"; break
    fi
  done
  [[ -n $base ]] || die "找不到 Python 3.11 或 3.12（anaconda 的除外）。macOS 可用 brew install python@3.12 安装后重试。"
  step "创建 .venv（${base}）"
  "$base" -m venv .venv
fi
if ! (cd /tmp && "$PY" -c 'import app, fastapi' 2>/dev/null); then
  step "安装后端依赖（首次较慢）"
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -e src/backend
fi

command -v npm >/dev/null 2>&1 || die "找不到 npm。安装 Node.js 22.22+ 或 24.15+ 后重试（macOS：brew install node@22）。"
if [[ ! -d src/frontend/node_modules ]]; then
  step "安装前端依赖（首次较慢）"
  npm ci --prefix src/frontend
fi

# ---------------------------------------------------------------- 2. .env
if [[ ! -f .env ]]; then
  step "未找到 .env，按 .env.example 生成演示配置（随机生成 Neo4j 口令与登录签名密钥）"
  "$PY" - <<'PY'
import re, secrets
from pathlib import Path
text = Path(".env.example").read_text(encoding="utf-8")
values = {
    "NEO4J_PASSWORD": secrets.token_urlsafe(18),
    "AUTH_JWT_SECRET": secrets.token_urlsafe(48),
    "LLM_MODE": "demo",
    "EMBEDDING_MODE": "demo",
    "QA_SIMILARITY_THRESHOLD": "0.58",
}
for key, value in values.items():
    text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, count=1, flags=re.M)
Path(".env").write_text(text, encoding="utf-8")
PY
elif secret="$(env_setting AUTH_JWT_SECRET "")"; ((${#secret} < 32)); then
  # 只补空着或过短的签名密钥这一行；其余配置（尤其 NEO4J_PASSWORD，已有库依赖它）一律不动
  step ".env 的 AUTH_JWT_SECRET 为空或短于 32 位，写入随机值"
  "$PY" - <<'PY'
import re, secrets
from pathlib import Path
path = Path(".env")
text = path.read_text(encoding="utf-8")
line = f"AUTH_JWT_SECRET={secrets.token_urlsafe(48)}"
text, n = re.subn(r"^AUTH_JWT_SECRET=.*$", line, text, count=1, flags=re.M)
if n == 0:
    text = text.rstrip("\n") + "\n" + line + "\n"
path.write_text(text, encoding="utf-8")
PY
fi

# 正式模式的根密钥（ADR-080）：必须在下面对 .env 的逐行导入之前补齐，否则本次进程读不到新写入的值。
if ((personal)) && [[ -z "$(env_setting MODEL_CREDENTIAL_KEY "")" ]]; then
  step ".env 的 MODEL_CREDENTIAL_KEY 为空，写入随机值（更换它会使已保存的个人模型配置失效）"
  "$PY" - <<'PY'
import base64, re, secrets
from pathlib import Path
path = Path(".env")
text = path.read_text(encoding="utf-8")
line = "MODEL_CREDENTIAL_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
text, n = re.subn(r"^MODEL_CREDENTIAL_KEY=.*$", line, text, count=1, flags=re.M)
if n == 0:
    text = text.rstrip("\n") + "\n" + line + "\n"
path.write_text(text, encoding="utf-8")
PY
fi

# 把 .env 按字面值导入（与 Compose 一致，不当 shell 脚本执行）；已在 shell 里设置的变量优先。
while IFS= read -r line || [[ -n $line ]]; do
  line="${line%$'\r'}"
  [[ $line =~ ^[A-Z_][A-Z0-9_]*= ]] || continue
  key="${line%%=*}"
  value="$(env_setting "$key" "")"
  [[ -n $value ]] && export "$key=$value"
done < .env
if ((personal)); then
  # 正式模式（ADR-080/081）：生成模型用各人的个人配置，向量必须是在线向量；任一缺失都直接退出，
  # 不静默落到演示模型或演示向量——否则教师与学生会以为在用真实模型。
  [[ "${EMBEDDING_MODE:-}" == online ]] || die "--personal 需要在 .env 设 EMBEDDING_MODE=online 并填写 EMBEDDING_BASE_URL、EMBEDDING_API_KEY、EMBEDDING_MODEL（ADR-081）。"
  for key in EMBEDDING_BASE_URL EMBEDDING_API_KEY EMBEDDING_MODEL MODEL_CREDENTIAL_KEY; do
    [[ -n ${!key:-} ]] || die "--personal 需要在 .env 填写 ${key}。"
  done
  export LLM_MODE=personal APP_ENV=development
  if [[ -z ${SSL_CERT_FILE:-} && $(uname -s) == Darwin ]]; then
    (cd /tmp && "$PY" -c 'import certifi' 2>/dev/null) || "$PY" -m pip install -q certifi
    SSL_CERT_FILE="$(cd /tmp && "$PY" -c 'import certifi; print(certifi.where())')" || die "取不到 certifi 根证书，手动 export SSL_CERT_FILE 后重试。"
    export SSL_CERT_FILE
  fi
elif ((live)); then
  # 真实大模型：主用四项缺一即退出，免得 API 启动后才报 Invalid configuration
  for key in LLM_BASE_URL LLM_API_KEY LLM_EXTRACTION_MODEL LLM_CHAT_MODEL; do
    [[ -n ${!key:-} ]] || die "--live 需要在 .env 填写 ${key}（DeepSeek 的 API Key 填 LLM_API_KEY，见 docs/runbook.md 第 3 节）。"
  done
  export LLM_MODE=live APP_ENV=development
  # 向量：.env 配了 online 就用；否则沿用演示向量，与演示课程同一向量空间，不必换库或重新向量化
  # （local 不在此列：它会被配置校验拒绝并指出 EMBEDDING_MODE，见 ADR-081。）
  case "${EMBEDDING_MODE:-}" in
    online|local) ;;
    *) export EMBEDDING_MODE=demo ;;
  esac
  if [[ $EMBEDDING_MODE == demo ]]; then
    export QA_SIMILARITY_THRESHOLD="${DEMO_QA_SIMILARITY_THRESHOLD:-0.58}"
  fi
  # macOS 上 python.org / Homebrew 的 Python 常找不到根证书，HTTPS 调模型会报证书错误；未设置时用 certifi 的
  if [[ -z ${SSL_CERT_FILE:-} && $(uname -s) == Darwin ]]; then
    (cd /tmp && "$PY" -c 'import certifi' 2>/dev/null) || "$PY" -m pip install -q certifi
    SSL_CERT_FILE="$(cd /tmp && "$PY" -c 'import certifi; print(certifi.where())')" || die "取不到 certifi 根证书，手动 export SSL_CERT_FILE 后重试。"
    export SSL_CERT_FILE
  fi
else
  # 演示入口：无论 .env 写的是什么模式，本次进程一律用演示模型，不产生付费调用。
  export LLM_MODE=demo EMBEDDING_MODE=demo APP_ENV=development
  export QA_SIMILARITY_THRESHOLD="${DEMO_QA_SIMILARITY_THRESHOLD:-0.58}"
fi
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${DEMO_WEB_PORT:-5173}"
DEMO_PASSWORD="${SEED_DEMO_PASSWORD:-smartsketch-demo}"

port_busy() {
  "$PY" -c 'import socket,sys; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try: s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError: sys.exit(0)
sys.exit(1)' "$1"
}
port_busy "$API_PORT" && die "端口 $API_PORT 已被占用（可能上次的 API 还在运行）。关掉占用进程后重试（macOS：lsof -i :${API_PORT}）。"
port_busy "$WEB_PORT" && die "端口 $WEB_PORT 已被占用。关掉占用进程，或用 DEMO_WEB_PORT=其他端口 重试。"

# ---------------------------------------------------------------- 3. Neo4j、迁移、账号
step "启动 Neo4j"
"$REPO_ROOT/scripts/dev-up.sh"

# 后端进程都从 src/backend 启动（与运行手册一致），相对的 SQLITE_URL / STORAGE_DIR 因此指向同一处。
step "迁移 SQLite 与 Neo4j"
(cd src/backend && "$PY" -m app.repositories.sqlite && "$PY" -m app.repositories.graph_migrations) \
  > "$LOG_DIR/migrate.log" 2>&1 || { tail -n 30 "$LOG_DIR/migrate.log" >&2; die "迁移失败，完整日志：$LOG_DIR/migrate.log"; }
echo "✓ 迁移完成"

step "预置演示账号"
(cd src/backend && SEED_DEMO_PASSWORD="$DEMO_PASSWORD" "$PY" ../../scripts/seed-demo-accounts.py) \
  | tee "$LOG_DIR/seed.log" || die "预置演示账号失败，见上方输出。"
grep -q 'exists, unchanged' "$LOG_DIR/seed.log" && accounts_existed=1 || accounts_existed=0

# ---------------------------------------------------------------- 4. 常驻服务
set -m   # 每个后台服务在自己的进程组里，退出时整组结束，避免 npm/vite 子进程残留占端口
pids=()
names=()
cleanup() {
  trap - EXIT INT TERM
  if ((${#pids[@]} > 0)); then
    echo
    echo "→ 停止 API、worker 与前端…"
    for pid in "${pids[@]}"; do kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
    echo "✓ 已停止。Neo4j 仍在运行（数据保留），停止用 scripts/dev-down.sh"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

start_bg() {  # start_bg <名字> <日志> <命令…>；命令在 src/backend 或指定目录里运行
  local name="$1" log="$2"; shift 2
  "$@" > "$log" 2>&1 &
  pids+=($!); names+=("$name")
}
wait_http() {  # wait_http <url> <名字> <日志> <秒>
  local url="$1" name="$2" log="$3" deadline=$((SECONDS + $4)) i
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    for i in "${!pids[@]}"; do
      kill -0 "${pids[$i]}" 2>/dev/null || { tail -n 30 "$LOG_DIR/${names[$i]}.log" >&2; die "${names[$i]} 启动后退出，完整日志：$LOG_DIR/${names[$i]}.log"; }
    done
    ((SECONDS < deadline)) || { tail -n 30 "$log" >&2; die "$name 未在规定时间内就绪：$url"; }
    sleep 1
  done
}

step "启动 API 与 worker"
start_bg api "$LOG_DIR/api.log" sh -c 'cd src/backend && exec "$0" -m app' "$PY"
start_bg worker "$LOG_DIR/worker.log" sh -c 'cd src/backend && exec "$0" -m app.workers' "$PY"
wait_http "http://127.0.0.1:$API_PORT/health" API "$LOG_DIR/api.log" 60
echo "✓ API 就绪：http://127.0.0.1:$API_PORT"

if ((do_import)); then
  step "导入演示课程（已导入时直接复用，不重复上传）"
  if (cd src/backend && "$PY" ../../scripts/import-demo.py) > "$LOG_DIR/import.log" 2>&1; then
    echo "✓ 演示课程已就绪：【示例】数据结构：栈与队列"
  else
    tail -n 20 "$LOG_DIR/import.log" >&2
    echo "⚠ 演示课程导入失败（服务继续运行），完整日志：$LOG_DIR/import.log" >&2
  fi
fi

step "启动前端"
start_bg web "$LOG_DIR/web.log" env SMARTSKETCH_API_TARGET="http://127.0.0.1:$API_PORT" \
  npm run dev --prefix src/frontend -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort
WEB_URL="http://localhost:$WEB_PORT"
wait_http "http://127.0.0.1:$WEB_PORT/" 前端 "$LOG_DIR/web.log" 60

if ((personal)); then
  cat <<EOF

✓ 正式模式已启动：$WEB_URL
  教师与学生登录后先在「模型 API 设置」保存自己的模型 API（ADR-080）：未保存前上传资料与提问会返回「需要配置模型」，不会回退到演示模型。
  账号：demo_teacher（教师）、demo_student、demo_student2（学生）
EOF
else
  cat <<EOF

✓ 演示环境已启动：$WEB_URL
  账号：demo_teacher（教师）、demo_student、demo_student2（学生）
EOF
fi
if ((accounts_existed)); then
  echo "  口令：账号早已存在，沿用当初设置的口令（本脚本不会重置口令）"
else
  echo "  口令：$DEMO_PASSWORD"
fi
if ((personal)); then
  echo "  模型：个人模型 API（各人自填，按各人自己的额度计费）；向量：$EMBEDDING_MODE ${EMBEDDING_MODEL} ${EMBEDDING_DIMENSIONS} 维"
  echo "  用法：教师登录 → 课程 → 资料 → 上传 PDF，处理完成后到「审核」查看草稿图谱"
elif ((live)); then
  echo "  模型：真实大模型 ${LLM_EXTRACTION_MODEL}（${LLM_BASE_URL}，按量计费）；向量：$EMBEDDING_MODE"
  echo "  用法：教师登录 → 课程 → 资料 → 上传 PDF，处理完成后到「审核」查看草稿图谱"
else
  echo "  模型：演示模式（不联网、不计费）；用真实大模型：scripts/start-demo.sh --live"
  echo "  正式模式（个人模型 API）：scripts/start.sh"
fi
cat <<EOF
  日志：$LOG_DIR
  按 Ctrl+C 停止。
EOF
if ((open_browser)); then
  if command -v open >/dev/null 2>&1; then open "$WEB_URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$WEB_URL" >/dev/null 2>&1 || true
  fi
fi

# 任何一个服务退出就整体收尾，免得留下半套环境
while :; do
  for i in "${!pids[@]}"; do
    if ! kill -0 "${pids[$i]}" 2>/dev/null; then
      tail -n 20 "$LOG_DIR/${names[$i]}.log" >&2
      die "${names[$i]} 已退出，完整日志：$LOG_DIR/${names[$i]}.log"
    fi
  done
  sleep 2
done
