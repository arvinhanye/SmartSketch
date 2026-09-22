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
  prompts/README.md evals/README.md
)
for path in "${required[@]}"; do [[ -f "$path" ]] || { echo "Missing required file: $path" >&2; exit 1; }; done
for json_file in .mcp.json .claude/settings.json; do python3 -m json.tool "$json_file" >/dev/null || { echo "Invalid JSON: $json_file" >&2; exit 1; }; done
grep -qxF '.claude/settings.local.json' .gitignore || { echo 'settings.local.json is not ignored' >&2; exit 1; }
grep -q 'M0-01 | DONE' docs/tasks.md || { echo 'M0-01 task status is not recorded' >&2; exit 1; }
grep -q 'PREREQUISITE' docs/architecture.md || { echo 'Graph prerequisite constraint is undocumented' >&2; exit 1; }

# ADR-004 naming baseline:契约文档中不得出现同义别名
contract_docs=(AGENTS.md docs/architecture.md specs/course-knowledge-graph.md)
banned=('\bRELATED\b:use RELATED_TO' 'APPLIES_TO:use EXAMPLE_OF' 'SourceChunk:use Chunk')
for entry in "${banned[@]}"; do
  pattern="${entry%%:*}"; hint="${entry#*:}"
  if grep -lE "$pattern" "${contract_docs[@]}" 2>/dev/null | grep -q .; then
    echo "Naming drift (ADR-004): '$pattern' found, $hint" >&2
    grep -nE "$pattern" "${contract_docs[@]}" >&2
    exit 1
  fi
done

# 任务状态机必须包含合并后新增的两个状态
for state in persisting cancelled; do
  grep -q "$state" specs/course-knowledge-graph.md \
    || { echo "Task state machine misses '$state' (ADR-004)" >&2; exit 1; }
done

echo 'Scaffold verification passed.'
