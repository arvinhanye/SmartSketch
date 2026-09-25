# Claude 交接：B11 合并收尾

- 日期：2026-09-25
- 分支 / base：`claude/b11-closeout` / `origin/main@2de97ba`（PR #194 的合并提交）
- 角色：协调方（ArvinHan 要求「#196、#194 审完就合并」，并授权执行合并）

## 审查与合并

| PR | 审查结论 | 结果 |
| --- | --- | --- |
| #194 B11 图谱编辑与版本契约 | 通过。`Relation`、`GraphVersion` 拆成的两个分支互斥（`additionalProperties: false` 加上各自的必填或常量字段）；`KnowledgePointUpdate` 必须带 `expected_revision` 和至少一个修改字段；`PUBLISH_BLOCKED` 返回结构化原因；草稿写入端点和回滚端点声明了 409 | 已合并，`2de97ba` |
| #196 REQ-01 补登抽取硬指标 | 通过（只改文档） | **未合并**：合并前 PR #199 抢先入 main，占用了决策编号 D-14，#196 与 main 在 `docs/tasks.md` 冲突。解决方案见下 |

合并前验证：把 #196、#194 依次临时合到 `a08bd5b` 上（scratchpad 独立副本，已包含 D05）：

| 命令 | 结果 |
| --- | --- |
| `./scripts/gen-contracts.sh --check` | 生成物与真源一致 |
| `pytest tests/contracts tests/tooling -q` | 176 passed（其中 `test_b11.py` 30 passed） |
| `pytest tests/backend -q` | 720 passed |
| `./scripts/verify.sh` | exit 0 |
| `python3 docs/reviews/validate_atomic_plan.py` | PASS |
| `git diff --check` | 通过 |

`a08bd5b` 之后 main 只多了 #199（仅改 `docs/tasks.md`、`docs/integrations.md`），合并 #194 时 GitHub 判定 `MERGEABLE CLEAN`，所以上述结果仍然适用。

## 本分支改动

- `docs/tasks.md`：B11 → `DONE（PR #194 2de97ba）`，补协调方复核证据和合并后遗留事项；「A02-R01 → B11」标为已完成。B11 这一节仍在文件开头（Codex 放的位置），为了不和 #196 在文件末尾再冲突，这次不挪。
- GitHub：关闭 issue #53（B11）；关闭 PR #198（内容已被 #199 完整取代）。

## #196 待办（需人工决定）

冲突解决方案已在 scratchpad 做好，但推送到 #196 的分支 `claude/pdf-course-model-training-0b0f46` 时被权限拦下（该分支正被另一个工作目录 `worktree-meaning-7a61bc` 检出）：

1. 合并 `origin/main` 到 #196，`docs/tasks.md` 两处冲突都保留双方内容：main 的内容在前，REQ-01 的在后。
2. REQ-01 的决策从 D-14 改号为 **D-15**，同步修改 `docs/tasks.md` 的决策表行和 REQ-01 节，`specs/course-knowledge-graph.md` 验收 7，以及 `docs/handoffs/claude-req-01.md`。

## 风险

- `downgrade_cycle`、`PUBLISH_BLOCKED.cycle` 的首尾同 ID 约束无法用 JSON Schema 表达，F13、G04 必须在服务层校验并补负例。
- B11 新增的必填响应字段（`revision`、`unchanged`、`excluded`、`kind` 等）会约束后续 F08、F13、G04、G06 的实现。

## 回滚

- B11：`git revert -m 1 2de97ba`，然后重跑 `./scripts/gen-contracts.sh --check` 和 `./scripts/verify.sh`。
- 本分支只改文档，还原即可；重开 issue 用 `gh issue reopen 53`。
