#!/usr/bin/env bash
# Claude PreToolUse hook: reject destructive shell commands in the shared workspace.
set -euo pipefail
input="$(cat)"
deny() { printf '{"decision":"block","reason":"%s"}\n' "$1"; exit 0; }
# Decode the JSON instead of regex-matching it: quotes inside the command arrive as \" and a
# regex stops at the first one, leaving the rest of the command unchecked.
# Input that cannot be decoded is blocked, not allowed (fail closed).
command="$(printf '%s' "$input" | python3 -c '
import json, sys
tool_input = json.load(sys.stdin).get("tool_input") or {}
sys.stdout.buffer.write(str(tool_input.get("command", "")).encode("utf-8"))
' 2>/dev/null)" || deny "Shared-workspace protection: hook input could not be parsed, command not checked."
case "$command" in
  *"git reset --hard"*|*"git clean -f"*|*"rm -rf"*|*"DROP DATABASE"*|*"git push --force"*)
    deny "Shared-workspace protection: use a reviewed, scoped command instead." ;;
esac
exit 0
