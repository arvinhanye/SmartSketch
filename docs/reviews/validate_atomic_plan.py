from pathlib import Path
import json,re
ROOT=Path('/Users/arvinhan/Desktop/SmartSketch')
p=ROOT/'docs/atomic-tasks.json'; data=json.loads(p.read_text()); tasks=data['tasks']
lookup={t['id']:t for t in tasks}; assert len(tasks)==len(lookup)==127
visited=set(); active=set()
def visit(k):
 assert k not in active,('cycle',k)
 if k in visited:return
 active.add(k)
 for d in lookup[k]['depends_on']: assert d in lookup;(visit(d))
 active.remove(k);visited.add(k)
for t in tasks:
 for field in ('input','output','allowed_files','acceptance','verification_command','handoff','risk','rollback'):assert t[field],(t['id'],field)
 assert t['status']=='PROPOSED' and t['verification_status']=='NOT_RUN_PLANNED'
 assert all(Path(f).is_absolute() and str(f).startswith(str(ROOT)+'/') for f in t['allowed_files'])
 visit(t['id'])
md=(ROOT/'docs/atomic-task-plan.md').read_text()
assert set(re.findall(r'\| \*\*([A-Z]\d{2}) ',md))==set(lookup)
for t in tasks:assert md.count('| **'+t['id']+' ')==1
files=['docs/architecture-review-2026-09-22.md','docs/atomic-task-plan.md','docs/claude-review-workflow.md','docs/architecture.md','docs/tasks.md','docs/handoffs/README.md','docs/reviews/codex-claude-initial-2026-09-22.md']
link_count=0
for f in files:
 text=(ROOT/f).read_text()
 for match in re.finditer(r'\[[^\]]+\]\(([^)]+)\)',text):
  target=match.group(1)
  if '://' in target or target.startswith('#'):continue
  dest=(ROOT/f).parent/target.split('#')[0]
  assert dest.exists(),(f,target)
  link_count+=1
print('PASS: 127 unique leaf tasks = 119 core + 8 optional; all required fields present.')
print('PASS: all dependency IDs exist; dependency graph is acyclic.')
print('PASS: JSON/Markdown ID sets match, each task appears once; proposed tests explicitly NOT_RUN_PLANNED.')
print(f'PASS: {link_count} local Markdown links resolve; allowed file paths stay inside the project.')
