#!/usr/bin/env bash
# 启动本地依赖（当前只有 Neo4j；SQLite 是嵌入式文件，只需目录存在）。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"

resolve_compose
require_env_file

echo "→ 创建本地数据目录（均在 .gitignore 忽略范围内）"
mkdir -p "$STORAGE_DIR" neo4j/data neo4j/logs

echo "→ 启动 Neo4j"
"${COMPOSE[@]}" up -d neo4j

echo "→ 等待健康检查通过（最多 180 秒）"
for i in $(seq 1 60); do
  status="$("${COMPOSE[@]}" ps --format json neo4j 2>/dev/null | tr ',' '\n' | grep -i '"Health"' | head -1 || true)"
  case "$status" in
    *healthy*) echo "✓ Neo4j 已就绪（第 ${i} 次探测）"; break ;;
  esac
  [[ $i -eq 60 ]] && die "Neo4j 在 180 秒内未就绪。查看日志：${COMPOSE[*]} logs neo4j"
  sleep 3
done

"$REPO_ROOT/scripts/check-apoc.sh"

echo
echo "Neo4j Browser： http://localhost:${NEO4J_HTTP_PORT:-7474}"
echo "Bolt 地址    ： ${NEO4J_URI:-bolt://localhost:7687}"
echo "停止         ： ./scripts/dev-down.sh"
