#!/usr/bin/env bash
# Claude Stop hook: best-effort local completion notification.
set -euo pipefail
cat >/dev/null || true
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'display notification "请查看任务输出与交接文件。" with title "SmartSketch · Claude"' >/dev/null 2>&1 || true
fi
