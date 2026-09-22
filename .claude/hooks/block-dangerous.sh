#!/usr/bin/env bash
# Claude PreToolUse hook: reject destructive shell commands in the shared workspace.
set -euo pipefail
input="$(cat)"
command="$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
case "$command" in
  *"git reset --hard"*|*"git clean -f"*|*"rm -rf"*|*"DROP DATABASE"*|*"git push --force"*)
    printf '%s\n' '{"decision":"block","reason":"Shared-workspace protection: use a reviewed, scoped command instead."}' ;;
  *) exit 0 ;;
esac
