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
  local double_quoted='^"([^"]*)"[[:space:]]*(#.*)?$'
  local single_quoted="^'([^']*)'[[:space:]]*(#.*)?$"
  if [[ -n ${!key:-} ]]; then printf '%s\n' "${!key}"; return; fi
  while IFS= read -r line || [[ -n $line ]]; do
    [[ $line == "$key="* ]] || continue
    value="${line#*=}"
    value="${value%$'\r'}"
    value="${value#"${value%%[![:space:]]*}"}"
    if [[ $value =~ $double_quoted || $value =~ $single_quoted ]]; then
      value="${BASH_REMATCH[1]}"
    else
      # Compose: 未加引号的值仅在空白后遇到 # 才把余下部分视为注释。
      value="${value%% \#*}"
      value="${value%%$'\t'\#*}"
      value="${value%"${value##*[![:space:]]}"}"
    fi
    [[ -n $value ]] && { printf '%s\n' "$value"; return; }
  done < .env
  printf '%s\n' "$fallback"
}

# neo4j 服务容器的 ID：优先取运行中的；没有时再找已创建或已退出的（compose ps -a），以便报告它为什么没在运行。
neo4j_container_id() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q neo4j 2>/dev/null | head -1)"
  [[ -n $cid ]] || cid="$("${COMPOSE[@]}" ps -aq neo4j 2>/dev/null | head -1)"
  printf '%s\n' "$cid"
}

# 输出一行「健康 状态 重启次数」：健康为 healthy / starting / unhealthy / none（无健康检查）/ missing（未创建）；
# 状态为容器的 running / restarting / created / exited / dead，取不到时留空。
# 健康必须精确比较整个单词：旧实现用 *healthy* 匹配，会把 unhealthy 也当成就绪。
neo4j_state() {
  local cid
  cid="$(neo4j_container_id)"
  if [[ -z $cid ]]; then echo missing; return; fi
  "$ENGINE" inspect --format \
    '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} {{.State.Status}} {{.RestartCount}}' \
    "$cid" 2>/dev/null || echo missing
}

# 本机回环地址上的端口是否已有程序在监听（bash 自带的 /dev/tcp，macOS 的 bash 3.2 也支持）。
port_listening() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# Neo4j 起不来时打印容器状态、最近日志和对症提示，全部写到 stderr。只读，不改动容器或数据。
neo4j_diagnose() {
  local cid info logs
  cid="$(neo4j_container_id)"
  {
    if [[ -z $cid ]]; then
      echo "（找不到 neo4j 容器）"
    else
      info="$("$ENGINE" inspect --format \
        'Status={{.State.Status}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} RestartCount={{.RestartCount}} Error={{.State.Error}}' \
        "$cid" 2>/dev/null || true)"
      logs="$("${COMPOSE[@]}" logs --tail 40 neo4j 2>&1 || true)"
      echo "---- 容器状态 ----"
      echo "$info"
      echo "---- 最近 40 行日志（${COMPOSE[*]} logs --tail 40 neo4j）----"
      echo "$logs"
      echo "----"
      # 反复重启时容器正在运行，ExitCode 已被重置为 0，所以提示同时依据日志内容。
      case "$info" in
        *"port is already allocated"*|*"address already in use"*)
          echo "提示：Neo4j 的端口被本机其他程序占用（常见：Neo4j Desktop、Homebrew 的 neo4j、另一个目录起的 SmartSketch）。"
          echo "      查占用者：lsof -nP -iTCP:$(env_setting NEO4J_HTTP_PORT 7474) -iTCP:$(env_setting NEO4J_BOLT_PORT 7687) -sTCP:LISTEN" ;;
      esac
      if [[ $info == *"OOMKilled=true"* || $info == *"ExitCode=137 "* || $logs == *"Invalid memory configuration"* ]]; then
        echo "提示：内存不够。调大 Docker 可用内存（Docker Desktop：设置 → Resources），或在 .env 设 NEO4J_HEAP_MAX=512M、NEO4J_PAGECACHE=256M。"
      elif [[ $logs == *"password"*"minimum"* || $logs == *"Invalid value for password"* ]]; then
        echo "提示：.env 的 NEO4J_PASSWORD 不符合 Neo4j 要求（至少 8 位）。"
      elif [[ $info == *"ExitCode=3 "* || ( $logs == *"shutdown initiated by request"* && $logs != *" ERROR "* ) ]]; then
        echo "提示：Neo4j 在读取配置或初始化日志时出错（退出码 3），日志里却没有 ERROR。"
        echo "      已知情形：之前反复崩溃后，neo4j/data、neo4j/logs 留下了坏状态，换成全新目录即可启动。"
        echo "      库里没有要保留的数据时：${COMPOSE[*]} down && mv neo4j/data neo4j/data.bak-\$(date +%s) && mv neo4j/logs neo4j/logs.bak-\$(date +%s)"
        echo "      （用 docker-compose.override.yml 改存 Docker 卷的，改用 ${COMPOSE[*]} down -v），然后重试。"
      fi
    fi
  } >&2
}

# 在容器内执行一条 Cypher。凭据从容器自己的 NEO4J_AUTH 取出，经 cypher-shell 认识的环境变量传入：
# 口令既不出现在宿主机的命令行（ps 可见），也不出现在容器内的命令行。
run_cypher() {
  "${COMPOSE[@]}" exec -T neo4j sh -c \
    'NEO4J_USERNAME="${NEO4J_AUTH%%/*}" NEO4J_PASSWORD="${NEO4J_AUTH#*/}" exec cypher-shell --format plain "$1"' \
    cypher "$1"
}
