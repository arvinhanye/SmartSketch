#!/usr/bin/env bash
# 验证 Neo4j 已装载 APOC。知识融合依赖 apoc.refactor.mergeNodes，社区版不自带启用的 APOC，
# 所以这是融合相关任务的硬前置：本脚本不过，那些任务不能开工。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"

resolve_compose
require_env_file

echo "→ 在 Neo4j 中执行：RETURN apoc.version()"
if ! out="$(run_cypher "RETURN apoc.version() AS apoc_version" 2>&1)"; then
  echo "$out" >&2
  die "APOC 未装载或 Neo4j 未就绪。
      先确认容器健康：${COMPOSE[*]} ps
      再看启动日志里的插件信息：${COMPOSE[*]} logs neo4j | grep -i apoc"
fi

echo "$out"
echo "✓ APOC 可用。"
