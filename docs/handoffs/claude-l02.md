# L02 真实基线测量

```text
task_id: L02
review_status: in_progress（抽取已测并提交；问答等向量服务可达后补测）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 52aa4db
head_commit: 本任务提交
changed_files:
  - evaluation/measure_web_flow.py（新增）
  - tests/backend/test_l02_measure.py（新增）
  - evaluation/reports/l02-baseline-2026-10.md（新增）
  - docs/tasks.md、docs/handoffs/claude-l02.md
```

## 结果

- 抽取（上传 → `awaiting_review`）实测 **141.72 秒**，目标 60 秒，未达标。分段：解析约 1.4 秒、抽取约 94.4 秒（34 次调用，并发 4）、融合与入库约 45.7 秒。
- 草稿图谱 82 个知识点、73 条关系、4 种关系类型（`PREREQUISITE` 仅 2 条）。未做人工准确率判定。
- 条件、数据来源与复现命令见 `evaluation/reports/l02-baseline-2026-10.md`。

## verification

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l02_measure.py -q -p no:cacheprovider` | 先 FAIL（脚本不存在），实现后 2 passed |
| `scripts/start-demo.sh --live --no-open` | API 8001、前端 5174 就绪；测完后用中断信号停止，主检出的 8000/5173 未受影响 |
| `evaluation/measure_web_flow.py extract …` | exit 0，`stage = awaiting_review`，`elapsed_seconds = 141.72` |
| `./scripts/verify.sh` | exit 0（基础档） |

## unverified

- 问答完整耗时与首字耗时、发布：未测。原因是向量服务不可达（`claude-l01.md` 发现 3）。
- PDF 格式的抽取耗时：未测，留给 L11。
- 抽取准确率：本次没有人工判定。

## 用量

本次计费 101054 token；冲刺累计 101054 / 5000000。

## api_and_data_changes

无。新增的是评测脚本与报告。

## open_questions

向量服务如何解决（恢复到北京地域的网络路径、改用国际站 key，或换本机可达的向量服务）。

## rollback

回退本提交即可；本地库里的测试课程在冲刺工作区的独立 SQLite/Neo4j 中，不影响主检出。

## next_action

向量服务可达后：发布该课程、添加学生、运行 `measure_web_flow.py ask`，把问答数字追加到报告并把 L02 置 DONE。期间继续 L03。
