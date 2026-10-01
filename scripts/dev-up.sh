#!/usr/bin/env bash
# 启动本地依赖（当前只有 Neo4j；SQLite 是嵌入式文件，只需目录存在），等待健康后验证 APOC。
# 可重复执行：已在运行时只做健康与 APOC 检查。等待上限可用 NEO4J_WAIT_SECONDS 调整（默认 180）。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"

require_env_file
storage_dir="$(env_setting STORAGE_DIR ./storage)"
wait_seconds="$(env_setting NEO4J_WAIT_SECONDS 180)"
[[ $wait_seconds =~ ^[0-9]+$ ]] || die "NEO4J_WAIT_SECONDS 必须是非负整数。"
resolve_compose

echo "→ 创建本地数据目录（均在 .gitignore 忽略范围内）"
mkdir -p "$storage_dir" neo4j/data neo4j/logs

# 容器还没在运行时先查端口：被其他程序占着的话 compose 会把容器留在 created 状态，健康检查永远等不到。
http_port="$(env_setting NEO4J_HTTP_PORT 7474)"
bolt_port="$(env_setting NEO4J_BOLT_PORT 7687)"
read -r health status restarts <<<"$(neo4j_state)"
if [[ $health == missing || $status == created || $status == exited || $status == dead ]]; then
  for port in "$http_port" "$bolt_port"; do
    port_listening "$port" || continue
    # Docker Desktop 上 lsof 只能看到 com.docker 进程，所以直接列出发布了这个端口的容器。
    holders="$("$ENGINE" ps --filter "publish=${port}" --format '{{.Names}}' 2>/dev/null | paste -sd ' ' - || true)"
    if [[ -n $holders ]]; then
      die "本机端口 ${port} 已被容器 ${holders} 占用（常见：另一个目录里的 SmartSketch 副本），Neo4j 无法启动。
      停掉它再重试：$ENGINE stop ${holders}（只是停止，不删数据；以后可用 $ENGINE start 恢复）"
    fi
    die "本机端口 ${port} 已被其他程序占用，Neo4j 无法启动（常见：Neo4j Desktop、Homebrew 的 neo4j）。
      查占用者：lsof -nP -iTCP:${port} -sTCP:LISTEN，关掉后重试；
      或在 .env 设 NEO4J_HTTP_PORT / NEO4J_BOLT_PORT 换端口（改 Bolt 端口时同步改 NEO4J_URI）。"
  done
fi

echo "→ 启动 Neo4j"
"${COMPOSE[@]}" up -d neo4j
echo "→ 等待健康检查通过（最多 ${wait_seconds} 秒；首次启动要初始化数据目录，较慢）"
read -r health status restarts <<<"$(neo4j_state)"
initial_restarts="${restarts:-0}"
[[ $initial_restarts =~ ^[0-9]+$ ]] || initial_restarts=0
deadline=$((SECONDS + wait_seconds))
probe=""
last_probe=$SECONDS
while :; do
  read -r health status restarts <<<"$(neo4j_state)"
  [[ $health == healthy ]] && { echo "✓ Neo4j 已就绪"; break; }
  [[ $health == missing ]] && { neo4j_diagnose; die "neo4j 容器不存在。查看日志：${COMPOSE[*]} logs neo4j"; }
  case "$status" in
    created|exited|dead)
      neo4j_diagnose
      die "neo4j 容器没有在运行（状态：${status}），原因见上方容器状态与日志。" ;;
  esac
  # Neo4j 启动后退出、被 restart 策略反复拉起：再等也不会好，立即报告。
  if [[ $status == restarting ]] || { [[ ${restarts:-} =~ ^[0-9]+$ ]] && ((restarts > initial_restarts)); }; then
    neo4j_diagnose
    die "Neo4j 启动后退出并被反复重启，原因见上方容器状态与日志。"
  fi
  # unhealthy 只表示连续若干次探测失败；慢机器上 Neo4j 之后仍会就绪，所以等到截止时间为止。
  # 但口令错误不会自愈：库首次初始化时的口令与 .env 的 NEO4J_PASSWORD 不一致。每 15 秒自己连一次，
  # 一旦认证被拒就立即报告，不必等 compose 判 unhealthy（约 160 秒）。
  if [[ $health == unhealthy ]] || ((SECONDS - last_probe >= 15)); then
    last_probe=$SECONDS
    probe="$(run_cypher "RETURN 1" 2>&1)" && probe="" || true
  fi
  if [[ -n $probe ]]; then
    case "$probe" in
      *nauthorized*|*uthentication*)
        die "Neo4j 拒绝了 .env 里的 NEO4J_PASSWORD：neo4j/data 首次初始化时用的是另一个口令，之后改 .env 不会生效。
      把 .env 改回当初的口令；或在没有要保留的数据时挪开旧库重建：
        ${COMPOSE[*]} down && mv neo4j/data neo4j/data.bak-\$(date +%s)" ;;
    esac
  fi
  if ((SECONDS >= deadline)); then
    neo4j_diagnose
    [[ -z $probe ]] || printf '最后一次连接尝试的输出：\n%s\n' "$probe" >&2
    die "Neo4j 在 ${wait_seconds} 秒内未就绪（当前：${health}）。完整日志：${COMPOSE[*]} logs neo4j；慢机器可在 .env 调大 NEO4J_WAIT_SECONDS 后重试。"
  fi
  sleep 3
done

"$REPO_ROOT/scripts/check-apoc.sh"

echo
echo "Neo4j Browser： http://localhost:$(env_setting NEO4J_HTTP_PORT 7474)"
echo "Bolt 地址    ： bolt://localhost:$(env_setting NEO4J_BOLT_PORT 7687)（后端读 .env 的 NEO4J_URI）"
echo "停止（保留数据）：$REPO_ROOT/scripts/dev-down.sh"
