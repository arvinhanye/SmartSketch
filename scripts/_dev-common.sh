#!/usr/bin/env bash
# 本地依赖脚本的共用部分，仅供 scripts/dev-*.sh 与 scripts/check-apoc.sh source。
# 不要直接执行；也不要在这里加任何会改动数据的逻辑。

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

die() { echo "错误：$*" >&2; exit 1; }

# 解析可用的 compose 命令与对应的容器引擎；缺失时给出可执行的下一步，
# 而不是让后续命令报 command not found。
resolve_compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose); ENGINE=docker
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose); ENGINE=docker
  elif command -v podman-compose >/dev/null 2>&1; then
    COMPOSE=(podman-compose); ENGINE=podman
  else
    die "本机没有可用的容器编排命令（docker compose / docker-compose / podman-compose）。
      安装 Docker Desktop、OrbStack 或 Podman 后重试；Docker Desktop 装好后如仍找不到 docker，
      把 ~/.docker/bin 加进 PATH 或重开终端。"
  fi
  # 命令存在不代表守护进程在跑；提前说清楚，别让后续命令抛难懂的连接错误。
  if ! "$ENGINE" info >/dev/null 2>&1; then
    die "$ENGINE 命令可用，但守护进程没有响应。请先启动 Docker Desktop / OrbStack / Podman 再重试。"
  fi
}

require_env_file() {
  [[ -f .env ]] || die "缺少 .env。先执行：cp .env.example .env，再按 docs/integrations.md 填写 NEO4J_PASSWORD。"
  # Compose 自行读取 .env；绝不把它当 shell 脚本执行（值可能含 $、空格或命令替换）。
}

# 仅供本机目录/提示读取非敏感设置。环境变量优先级与 Compose 一致；不导出、不改写 .env。
# 值按字面量读取，支持完整单/双引号和 CRLF；密码由 Compose 自己解析，绝不经此函数读取。
env_setting() {
  local key="$1" fallback="$2" line value
  if [[ -n ${!key:-} ]]; then printf '%s\n' "${!key}"; return; fi
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line == "$key="* ]] || continue
    value="${line#*=}"
    value="${value%$'\r'}"
    if [[ ${#value} -ge 2 ]]; then
      if [[ $value == \"*\" || $value == \'*\' ]]; then value="${value:1:${#value}-2}"; fi
    fi
    [[ -n $value ]] && { printf '%s\n' "$value"; return; }
  done < .env
  printf '%s\n' "$fallback"
}

# 输出 neo4j 服务容器的健康状态：healthy / starting / unhealthy / none（无健康检查）/ missing（未创建）。
# 必须精确比较整个单词：旧实现用 *healthy* 匹配，会把 unhealthy 也当成就绪。
neo4j_health() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q neo4j 2>/dev/null | head -1)"
  if [[ -z $cid ]]; then echo missing; return; fi
  "$ENGINE" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$cid" 2>/dev/null || echo missing
}

# 在容器内执行一条 Cypher。凭据从容器自己的 NEO4J_AUTH 取出，经 cypher-shell 认识的环境变量传入：
# 口令既不出现在宿主机的命令行（ps 可见），也不出现在容器内的命令行。
run_cypher() {
  "${COMPOSE[@]}" exec -T neo4j sh -c \
    'NEO4J_USERNAME="${NEO4J_AUTH%%/*}" NEO4J_PASSWORD="${NEO4J_AUTH#*/}" exec cypher-shell --format plain "$1"' \
    cypher "$1"
}
