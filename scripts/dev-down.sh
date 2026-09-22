#!/usr/bin/env bash
# 停止本地依赖。默认保留数据；销毁数据必须显式加参数并二次确认。
set -euo pipefail
# shellcheck source=scripts/_dev-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_dev-common.sh"

MODE=stop
case "${1:-}" in
  "")                 MODE=stop ;;
  --destroy)          MODE=destroy ;;
  --destroy-storage)  MODE=destroy-storage ;;
  -h|--help)
    cat <<'USAGE'
用法：
  ./scripts/dev-down.sh                    停止容器，保留 Neo4j 数据与 storage/
  ./scripts/dev-down.sh --destroy          停止并删除 Neo4j 数据卷与 neo4j/data、neo4j/logs
  ./scripts/dev-down.sh --destroy-storage  在 --destroy 基础上再删除 STORAGE_DIR（SQLite 与已上传资料）

--destroy 系列不可恢复：图谱、任务、进度与已上传的课程资料都会消失，
且本仓库不备份这些目录。只在需要干净重建时使用。
USAGE
    exit 0 ;;
  *) die "未知参数：$1（用 --help 查看用法）" ;;
esac

resolve_compose
require_env_file

if [[ $MODE == stop ]]; then
  "${COMPOSE[@]}" down
  echo "✓ 已停止，数据保留。重新启动：./scripts/dev-up.sh"
  exit 0
fi

echo "即将永久删除："
echo "  - Neo4j 容器与匿名卷"
echo "  - $REPO_ROOT/neo4j/data 、 $REPO_ROOT/neo4j/logs"
[[ $MODE == destroy-storage ]] && echo "  - $REPO_ROOT/$STORAGE_DIR （SQLite 业务库与已上传资料）"
echo "此操作不可恢复，且没有备份。"
read -r -p '确认请输入大写 DESTROY：' answer
[[ $answer == DESTROY ]] || die "未确认，已取消，未删除任何内容。"

"${COMPOSE[@]}" down -v
# 只删仓库内的固定相对路径，避免变量为空时误删其他位置。
rm -rf "$REPO_ROOT/neo4j/data" "$REPO_ROOT/neo4j/logs"
if [[ $MODE == destroy-storage ]]; then
  target="$(cd "$REPO_ROOT" && cd "$STORAGE_DIR" 2>/dev/null && pwd || true)"
  if [[ -n $target && $target == "$REPO_ROOT"/* ]]; then
    rm -rf "$target"
  else
    echo "跳过 STORAGE_DIR：$STORAGE_DIR 不在仓库内或不存在，请手工确认。" >&2
  fi
fi
echo "✓ 已销毁。下次 ./scripts/dev-up.sh 会重建空实例（需重新下载 APOC）。"
