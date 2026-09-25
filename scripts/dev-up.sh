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

echo "→ 启动 Neo4j"
"${COMPOSE[@]}" up -d neo4j
echo "→ 等待健康检查通过（最多 ${wait_seconds} 秒；首次启动要初始化数据目录，较慢）"
deadline=$((SECONDS + wait_seconds))
while :; do
  health="$(neo4j_health)"
  case "$health" in
    healthy) echo "✓ Neo4j 已就绪"; break ;;
    unhealthy) die "Neo4j 健康检查失败。查看日志：${COMPOSE[*]} logs neo4j" ;;
    missing) die "neo4j 容器不存在或已退出。查看日志：${COMPOSE[*]} logs neo4j" ;;
  esac
  ((SECONDS < deadline)) || die "Neo4j 在 ${wait_seconds} 秒内未就绪（当前：${health}）。查看日志：${COMPOSE[*]} logs neo4j"
  sleep 3
done

"$REPO_ROOT/scripts/check-apoc.sh"

echo
echo "Neo4j Browser： http://localhost:$(env_setting NEO4J_HTTP_PORT 7474)"
echo "Bolt 地址    ： bolt://localhost:$(env_setting NEO4J_BOLT_PORT 7687)（后端读 .env 的 NEO4J_URI）"
echo "停止（保留数据）：$REPO_ROOT/scripts/dev-down.sh"
