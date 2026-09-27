#!/usr/bin/env bash
# K11 集成门禁：真实 Neo4j 上的 tests/integration + 依赖图库的后端用例（F11 等），报告判定同 gate.py，
# 然后跑 K05/K06 端到端（scripts/e2e.sh，演示模型）。
#
# Neo4j：缺省起一次性容器（结束即删，F14 会清库，所以绝不连开发库）；
#        也可设 VERIFY_NEO4J_URI / VERIFY_NEO4J_USER / VERIFY_NEO4J_PASSWORD 指向一个可清空的实例。
# 需要 Docker 的重型用例（dev-up、镜像构建）固定以 SMARTSKETCH_SKIP_DOCKER=1 跳过，已在 allowed-skips.txt 登记。
# 用法：scripts/verify/integration.sh [--no-e2e]
set -euo pipefail
cd "$(dirname "$0")/../.."
run_e2e=1
[[ ${1:-} == "--no-e2e" ]] && run_e2e=0
py="${PYTHON:-}"
if [[ -z $py ]]; then
  if [[ -x .venv/bin/python ]]; then py=.venv/bin/python; else py=python3; fi
fi
out="$(mktemp -d)"
container=""
cleanup() {
  [[ -z $container ]] || docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf -- "$out"
}
trap cleanup EXIT INT TERM

if [[ -n ${VERIFY_NEO4J_URI:-} ]]; then
  uri="$VERIFY_NEO4J_URI" user="${VERIFY_NEO4J_USER:-neo4j}" password="${VERIFY_NEO4J_PASSWORD:?设置 VERIFY_NEO4J_URI 时须同时设置 VERIFY_NEO4J_PASSWORD}"
else
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "FAIL integration gate: 未设置 VERIFY_NEO4J_URI，且 Docker 不可用，无法启动一次性 Neo4j" >&2
    exit 1
  fi
  port="${VERIFY_NEO4J_PORT:-17689}"
  container="smartsketch-verify-neo4j-$$"
  user=neo4j password="verify-neo4j-$$-pass" uri="bolt://127.0.0.1:$port"
  echo "→ 启动一次性 Neo4j（${container}，端口 ${port}）"
  docker run -d --rm --name "$container" -e NEO4J_AUTH="neo4j/$password" \
    -e NEO4J_PLUGINS='["apoc"]' -e NEO4J_dbms_security_procedures_unrestricted='apoc.*' \
    -p "127.0.0.1:$port:7687" "neo4j:${NEO4J_IMAGE_TAG:-5.26-community}" >/dev/null
  deadline=$((SECONDS + 180))
  until docker exec "$container" cypher-shell -u neo4j -p "$password" 'RETURN 1' >/dev/null 2>&1; do
    if ((SECONDS >= deadline)); then echo "FAIL integration gate: 一次性 Neo4j 180 秒内未就绪" >&2; exit 1; fi
    sleep 2
  done
fi

# 各集成用例历史上用了不同的环境变量名，这里统一指向同一个可清空的实例。
for prefix in SMARTSKETCH_TEST_NEO4J SMARTSKETCH_F03 SMARTSKETCH_F14; do
  export "${prefix}_URI=$uri" "${prefix}_USER=$user" "${prefix}_PASSWORD=$password"
done
export SMARTSKETCH_SKIP_DOCKER=1

status=0
PYTHONPATH="$PWD/src/backend${PYTHONPATH:+:$PYTHONPATH}" "$py" -m pytest tests/integration -q -p no:cacheprovider \
  --junitxml="$out/integration.xml" || status=$?
"$py" scripts/verify/gate.py integration integration "$out/integration.xml" --min-tests 100 || status=1
# 依赖图库的后端用例在 full 模式下允许跳过；这里必须执行
PYTHONPATH="$PWD/src/backend${PYTHONPATH:+:$PYTHONPATH}" "$py" -m pytest tests/backend/test_f11.py -q -p no:cacheprovider \
  --junitxml="$out/backend-live.xml" || status=$?
"$py" scripts/verify/gate.py backend-live integration "$out/backend-live.xml" --min-tests 10 || status=1

if ((run_e2e)); then
  scripts/e2e.sh || status=$?
fi
exit "$status"
