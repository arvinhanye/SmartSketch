#!/usr/bin/env bash
# 默认只停止 Neo4j 并保留数据；--destroy 会删除 Compose 管理的卷，必须在终端精确确认。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"

case "${1:-}" in
  "") [[ $# -eq 0 ]] || die "用法：$0 [--destroy]" ;;
  --destroy) [[ $# -eq 1 ]] || die "用法：$0 [--destroy]" ;;
  *) die "未知选项。用法：$0 [--destroy]" ;;
esac

require_env_file
resolve_compose

if [[ ${1:-} == --destroy ]]; then
  [[ -t 0 ]] || die "--destroy 需要交互式终端确认；未删除任何卷。"
  echo "将停止服务并删除 Compose 管理的卷。绑定目录 neo4j/data、neo4j/logs 不由 -v 删除。" >&2
  printf '输入 DELETE NEO4J DATA 以确认：' >&2
  IFS= read -r confirmation || die "未收到确认；未删除任何卷。"
  [[ $confirmation == 'DELETE NEO4J DATA' ]] || die "确认不匹配；未删除任何卷。"
  "${COMPOSE[@]}" down -v
  echo "Compose 管理的卷已删除；绑定目录 neo4j/data、neo4j/logs 仍保留。"
else
  "${COMPOSE[@]}" stop neo4j
  echo "Neo4j 已停止；数据与卷保留。"
fi
