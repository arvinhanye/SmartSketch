"""Validate the proposed atomic task catalog from any repository checkout."""

import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
LOGICAL_ROOT = PurePosixPath("/Users/arvinhan/Desktop/SmartSketch")
tasks = json.loads((ROOT / "docs/atomic-tasks.json").read_text(encoding="utf-8"))["tasks"]
lookup = {task["id"]: task for task in tasks}
assert len(tasks) == len(lookup), "duplicate task ID"

visited = set()
active = set()


def visit(task_id):
    assert task_id not in active, ("cycle", task_id)
    if task_id in visited:
        return
    active.add(task_id)
    for dependency in lookup[task_id]["depends_on"]:
        assert dependency in lookup, (task_id, dependency)
        visit(dependency)
    active.remove(task_id)
    visited.add(task_id)


for task in tasks:
    for field in ("input", "output", "allowed_files", "acceptance", "verification_command", "handoff", "risk", "rollback"):
        assert task[field], (task["id"], field)
    assert task["status"] == "PROPOSED" and task["verification_status"] == "NOT_RUN_PLANNED"
    for value in task["allowed_files"]:
        path = PurePosixPath(value)
        assert path.is_relative_to(LOGICAL_ROOT) and path != LOGICAL_ROOT, value
        assert ".." not in path.parts, value
    visit(task["id"])

plan = (ROOT / "docs/atomic-task-plan.md").read_text(encoding="utf-8")
markdown_ids = re.findall(r"\| \*\*([A-Z]\d{2}) ", plan)
assert len(markdown_ids) == len(tasks), "Markdown task count differs from JSON"
assert set(markdown_ids) == set(lookup), "Markdown/JSON task IDs differ"
assert f"共 **{len(tasks)} 个叶子任务**" in plan
optional_count = sum(task["group"] == "可选加分项" for task in tasks)
assert f"**{len(tasks) - optional_count} 个主线任务、{optional_count} 个条件性加分任务**" in plan

files = ["docs/architecture-review-2026-09-22.md", "docs/atomic-task-plan.md", "docs/claude-review-workflow.md", "docs/architecture.md", "docs/tasks.md", "docs/handoffs/README.md", "docs/reviews/codex-claude-initial-2026-09-22.md"]
link_count = 0
for name in files:
    document = ROOT / name
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
        if "://" in target or target.startswith("#"):
            continue
        destination = document.parent / target.split("#")[0]
        assert destination.exists(), (name, target)
        link_count += 1

print(f"PASS: {len(tasks)} unique leaf tasks = {len(tasks) - optional_count} core + {optional_count} optional; all required fields present.")
print("PASS: all dependency IDs exist; dependency graph is acyclic.")
print("PASS: JSON/Markdown ID sets and counts match; planned tests explicitly NOT_RUN_PLANNED.")
print(f"PASS: {link_count} local Markdown links resolve; allowed file paths stay inside the project.")
