#!/usr/bin/env bash
# 本地依赖脚本的共用部分，仅供 scripts/dev-*.sh 与 scripts/check-apoc.sh source。
# 不要直接执行；也不要在这里加任何会改动数据的逻辑。

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

die() { echo "错误：$*" >&2; exit 1; }

# 解析可用的 compose 命令；缺失时给出可执行的下一步，而不是让后续命令报 command not found。
resolve_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  elif command -v podman-compose >/dev/null 2>&1; then
    COMPOSE=(podman-compose)
  else
    die "本机没有可用的容器编排命令（docker compose / docker-compose / podman-compose）。
      安装 Docker Desktop、OrbStack 或 Podman 后重试。
      本仓库不依赖任何具体产品，只要求命令行能跑 compose 文件。"
  fi
  # 命令存在不代表守护进程在跑；提前说清楚，别让后续命令抛难懂的连接错误。
  if [[ ${COMPOSE[0]} == docker ]] && ! docker info >/dev/null 2>&1; then
    die "docker 命令可用，但守护进程没有响应。请先启动 Docker Desktop / OrbStack 再重试。"
  fi
}

require_env_file() {
  [[ -f .env ]] || die "缺少 .env。先执行：cp .env.example .env，再按 docs/integrations.md 填写 NEO4J_PASSWORD。"
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
  : "${NEO4J_USER:?.env 缺少 NEO4J_USER}"
  : "${NEO4J_PASSWORD:?.env 缺少 NEO4J_PASSWORD}"
  : "${NEO4J_DATABASE:=neo4j}"
  : "${STORAGE_DIR:=./storage}"
}
