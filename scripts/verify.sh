#!/usr/bin/env bash
# Single lightweight quality gate for the project scaffold.
set -euo pipefail
required=(
  AGENTS.md CLAUDE.md README.md .gitignore .mcp.json .env.example
  .claude/settings.json .claude/rules/frontend.md .claude/rules/backend.md .claude/rules/testing.md
  .claude/hooks/notify-macos.sh .claude/hooks/block-dangerous.sh
  docs/product.md docs/architecture.md docs/decisions.md docs/tasks.md docs/integrations.md docs/handoffs/README.md
  specs/course-knowledge-graph.md
  src/README.md src/frontend/README.md src/backend/README.md src/backend/app/__init__.py src/contracts/README.md
)
for path in "${required[@]}"; do [[ -f "$path" ]] || { echo "Missing required file: $path" >&2; exit 1; }; done
for json_file in .mcp.json .claude/settings.json; do python3 -m json.tool "$json_file" >/dev/null || { echo "Invalid JSON: $json_file" >&2; exit 1; }; done
grep -qxF '.claude/settings.local.json' .gitignore || { echo 'settings.local.json is not ignored' >&2; exit 1; }
grep -q 'M0-01 | DONE' docs/tasks.md || { echo 'M0-01 task status is not recorded' >&2; exit 1; }
grep -q 'PREREQUISITE' docs/architecture.md || { echo 'Graph prerequisite constraint is undocumented' >&2; exit 1; }
hook_tests="$(tests/hooks/test_block_dangerous.sh 2>&1)" || { printf '%s\n' "$hook_tests" >&2; echo 'block-dangerous hook regression tests failed' >&2; exit 1; }
tail -n 1 <<<"$hook_tests"
echo 'Scaffold verification passed.'
