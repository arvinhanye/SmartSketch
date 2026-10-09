#!/usr/bin/env bash
# 结束一组后台服务（每个在自己的进程组里，调用方需 `set -m`）：先礼貌结束整组，等待 grace 秒，
# 仍存活的强制结束，最后才 wait。不会因为某个服务忽略 SIGTERM 而无限挂住（CI 上曾因此卡到作业超时）。
# 用法：stop_process_groups <grace 秒> <pid>...    兼容 macOS 自带的 bash 3.2。
stop_process_groups() {
  local grace="$1"; shift
  local pid alive
  for pid in "$@"; do kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done
  local deadline=$((SECONDS + grace))
  while ((SECONDS < deadline)); do
    alive=0
    for pid in "$@"; do kill -0 "$pid" 2>/dev/null && alive=1; done
    ((alive)) || break
    sleep 0.2
  done
  for pid in "$@"; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "进程 ${pid} 在 ${grace} 秒内没有退出，强制结束" >&2
      kill -9 -- "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
