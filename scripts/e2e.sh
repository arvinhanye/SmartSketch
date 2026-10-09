#!/usr/bin/env bash
# K05/K06 端到端：用真实后端服务（API + worker）、真实 Neo4j 与 Vite 前端跑 Playwright 用例。
#
# 前置：Docker 可用（缺省起一次性 Neo4j），或设 E2E_NEO4J_URI 指向演示向量空间的实例；
#       .venv 已安装后端（pip install -e 'src/backend[test]'），根目录与 src/frontend 均已 npm ci。
# 隔离：每次运行在 .e2e/<时间戳>/ 下新建 SQLite 与存储目录，端口默认 18000/15173，
#       不碰开发库；Neo4j 缺省为一次性容器，结束即删除。
# 模型：缺省 LLM_MODE=demo、EMBEDDING_MODE=demo（确定性规则模型，不联网、不产生费用）。
#       E2E_LLM_MODE=personal（L11）：再起本机假供应商 scripts/fake_provider.py（包装演示模型），
#       导出测试专用根密钥与 MODEL_ENDPOINT_ALLOW_PRIVATE=1；用户在设置页填写 E2E_PROVIDER_URL。
# 用法：scripts/e2e.sh [playwright 参数…]，例如 scripts/e2e.sh tests/e2e/teacher.spec.ts
#       浏览器与 @playwright/test 版本不符时设 PLAYWRIGHT_CHROMIUM_EXECUTABLE。
# 失败证据：.e2e/<时间戳>/ 下的 api.log、worker.log、web.log 与 playwright/（截图与 trace）。
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

. "$REPO_ROOT/scripts/_stop-procs.sh"
die() { echo "错误：$*" >&2; exit 1; }
PY="${E2E_PYTHON:-$REPO_ROOT/.venv/bin/python}"
PY="$(command -v -- "$PY" || true)"   # 允许传 PATH 上的名字（CI 用 python）
[[ -n $PY && -x $PY ]] || die "找不到 ${E2E_PYTHON:-.venv/bin/python}；先创建 .venv 并安装后端，或用 E2E_PYTHON 指定解释器。"
[[ -d node_modules/@playwright/test ]] || die "缺 @playwright/test；先在仓库根目录 npm ci。"
[[ -d src/frontend/node_modules ]] || die "缺前端依赖；先 npm ci --prefix src/frontend。"

RUN_DIR="$REPO_ROOT/.e2e/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR/storage"
API_PORT="${E2E_API_PORT:-18000}"
WEB_PORT="${E2E_WEB_PORT:-15173}"

# 只导出后端需要的变量；.env 按字面值读取（同 Compose），不当 shell 脚本执行。
while IFS= read -r line || [[ -n $line ]]; do
  line="${line%$'\r'}"
  [[ $line =~ ^[A-Z_][A-Z0-9_]*= ]] || continue
  key="${line%%=*}"
  [[ -n ${!key:-} ]] || export "$key=${line#*=}"
done < <([[ -f .env ]] && cat .env)
export APP_ENV=development API_HOST=127.0.0.1 API_PORT="$API_PORT"
export SQLITE_URL="sqlite:///$RUN_DIR/smartsketch.sqlite3" STORAGE_DIR="$RUN_DIR/storage"
export LLM_MODE="${E2E_LLM_MODE:-demo}" EMBEDDING_MODE="${E2E_EMBEDDING_MODE:-demo}"
export AUTH_JWT_SECRET="${AUTH_JWT_SECRET:-e2e-only-signing-key-0123456789abcdefghij}"
export WORKER_HEARTBEAT_FILE="$RUN_DIR/worker.heartbeat"
export E2E_PASSWORD="${E2E_PASSWORD:-e2e-demo-pass-1}"
export E2E_TEACHER_PASSWORD="$E2E_PASSWORD" E2E_STUDENT_PASSWORD="$E2E_PASSWORD"
# 演示向量下的相似度闸门（ADR-076 实测：覆盖问题 ≥ 0.63、无关问题 ≤ 0.54）
export QA_SIMILARITY_THRESHOLD="${E2E_QA_SIMILARITY_THRESHOLD:-0.58}"
if [[ $LLM_MODE == personal ]]; then
  # 个人模式（L11，ADR-080）：测试专用随机根密钥（迁移与启动前就要有）；放行回环才能连本机假供应商
  # （仅开发环境，APP_ENV=production 下拒绝启动）。
  PROVIDER_PORT="${E2E_PROVIDER_PORT:-18900}"
  [[ -n ${MODEL_CREDENTIAL_KEY:-} ]] || export MODEL_CREDENTIAL_KEY="$("$PY" -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  export MODEL_ENDPOINT_ALLOW_PRIVATE=1 E2E_PROVIDER_URL="http://127.0.0.1:$PROVIDER_PORT/v1"
fi

set -m  # 后台任务各自成组，便于清理
pids=()
neo4j_container=""
cleanup() {
  # 每个服务在自己的进程组里（set -m），整组结束，避免 npx 的子进程残留占用端口；
  # 10 秒内没退出的强制结束，不能无限 wait（CI 上曾因某个服务不响应 SIGTERM 而卡到作业超时）
  ((${#pids[@]})) && stop_process_groups 10 "${pids[@]}"
  [[ -z $neo4j_container ]] || docker rm -f "$neo4j_container" >> "$RUN_DIR/cleanup.log" 2>&1 \
    || echo "未能删除一次性 Neo4j 容器 ${neo4j_container}，请手动 docker rm -f" >&2
}
trap cleanup EXIT INT TERM

# Neo4j：缺省起一个一次性容器（演示向量空间与开发库的 fake 空间不同，启动门禁不允许混用）；
# 设 E2E_NEO4J_URI（及 E2E_NEO4J_USER/E2E_NEO4J_PASSWORD）则改用已有实例。
if [[ -n ${E2E_NEO4J_URI:-} ]]; then
  export NEO4J_URI="$E2E_NEO4J_URI" NEO4J_USER="${E2E_NEO4J_USER:-neo4j}" NEO4J_PASSWORD="${E2E_NEO4J_PASSWORD:?设置 E2E_NEO4J_URI 时须同时设置 E2E_NEO4J_PASSWORD}"
else
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 \
    || die "未设置 E2E_NEO4J_URI，且 Docker 不可用，无法启动一次性 Neo4j。"
  neo4j_port="${E2E_NEO4J_PORT:-17688}"
  neo4j_container="smartsketch-e2e-neo4j-$$"
  export NEO4J_URI="bolt://127.0.0.1:$neo4j_port" NEO4J_USER=neo4j NEO4J_PASSWORD="e2e-neo4j-$$-pass"
  echo "→ 启动一次性 Neo4j（${neo4j_container}，端口 ${neo4j_port}）"
  docker run -d --rm --name "$neo4j_container" -e NEO4J_AUTH="neo4j/$NEO4J_PASSWORD" \
    -e NEO4J_PLUGINS='["apoc"]' -e NEO4J_dbms_security_procedures_unrestricted='apoc.*' \
    -p "127.0.0.1:$neo4j_port:7687" "neo4j:${NEO4J_IMAGE_TAG:-5.26-community}" >/dev/null
  deadline=$((SECONDS + 180))
  until docker exec "$neo4j_container" cypher-shell -u neo4j -p "$NEO4J_PASSWORD" 'RETURN 1' >/dev/null 2>&1; do
    ((SECONDS < deadline)) || die "一次性 Neo4j 在 180 秒内未就绪"
    sleep 2
  done
fi

echo "→ 运行目录 $RUN_DIR"
(cd src/backend && "$PY" -m app.repositories.sqlite && "$PY" -m app.repositories.graph_migrations) > "$RUN_DIR/migrate.log" 2>&1 \
  || { cat "$RUN_DIR/migrate.log" >&2; die "迁移失败（Neo4j 是否已启动？）"; }
SEED_DEMO_PASSWORD="$E2E_PASSWORD" "$PY" scripts/seed-demo-accounts.py > "$RUN_DIR/seed.log" 2>&1 \
  || { cat "$RUN_DIR/seed.log" >&2; die "预置演示账号失败"; }

if [[ $LLM_MODE == personal ]]; then
  PYTHONPATH="$REPO_ROOT/src/backend" "$PY" scripts/fake_provider.py --port "$PROVIDER_PORT" \
    > "$RUN_DIR/provider.log" 2>&1 & pids+=($!)
fi
(cd src/backend && exec "$PY" -m app) > "$RUN_DIR/api.log" 2>&1 & pids+=($!)
(cd src/backend && exec "$PY" -m app.workers) > "$RUN_DIR/worker.log" 2>&1 & pids+=($!)
# 用构建产物 + vite preview（与 nginx 同源反代一致，避免 dev server 按需编译的抖动）
(cd src/frontend && npx vite build --outDir "$RUN_DIR/web-dist" --emptyOutDir) > "$RUN_DIR/web-build.log" 2>&1 \
  || { tail -n 40 "$RUN_DIR/web-build.log" >&2; die "前端构建失败"; }
(cd src/frontend && SMARTSKETCH_API_TARGET="http://127.0.0.1:$API_PORT" \
  exec npx vite preview --outDir "$RUN_DIR/web-dist" --host 127.0.0.1 --port "$WEB_PORT" --strictPort) \
  > "$RUN_DIR/web.log" 2>&1 & pids+=($!)

wait_for() {
  local url="$1" name="$2" deadline=$((SECONDS + 60))
  until curl -fsS "$url" >/dev/null 2>&1; do
    ((SECONDS < deadline)) || { tail -n 40 "$RUN_DIR"/*.log >&2; die "$name 在 60 秒内未就绪：$url"; }
    sleep 1
  done
}
wait_for "http://127.0.0.1:$API_PORT/health" "API"
wait_for "http://127.0.0.1:$WEB_PORT/" "前端"
if [[ $LLM_MODE == personal ]]; then
  # 个人模式（L11）：用户在设置页填写本机假供应商（scripts/fake_provider.py，包装演示模型）的地址。
  # 根密钥与放行回环已在启动 API/worker 前导出（见上）。
  wait_for "http://127.0.0.1:$PROVIDER_PORT/health" "假供应商"
fi
echo "→ 服务就绪：前端 http://127.0.0.1:$WEB_PORT ，API http://127.0.0.1:$API_PORT"

set +e
E2E_BASE_URL="http://127.0.0.1:$WEB_PORT" E2E_OUTPUT_DIR="$RUN_DIR/playwright" npx playwright test "$@"
status=$?
set -e
if ((status != 0)); then
  echo "✗ 端到端失败（exit ${status}）；证据：$RUN_DIR" >&2
else
  echo "✓ 端到端通过；日志：$RUN_DIR"
fi
exit "$status"
