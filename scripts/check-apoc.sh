#!/usr/bin/env bash
# 验证 Neo4j 已装载 APOC。M1-03 的知识融合依赖 apoc.refactor.mergeNodes，
# 社区版不自带 APOC，所以这是 M1-03 的硬前置：本脚本不过，M1-03 不能开工。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"

resolve_compose
require_env_file

echo "→ 在 Neo4j 中执行：RETURN apoc.version()"
if ! out="$("${COMPOSE[@]}" exec -T neo4j cypher-shell \
      -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d "$NEO4J_DATABASE" \
      --format plain "RETURN apoc.version() AS apoc_version" 2>&1)"; then
  echo "$out" >&2
  die "APOC 未装载或 Neo4j 未就绪。
      先确认容器健康：${COMPOSE[*]} ps
      再看启动日志是否下载插件失败：${COMPOSE[*]} logs neo4j | grep -i apoc
      首次启动需要网络，镜像会拉取与自身版本匹配的 APOC Core。"
fi

echo "$out"
echo "✓ APOC 可用，M1-03 的前置条件满足。"
