# Agent 交接记录

文件名：`<agent>-<task>.md`，例如 `codex-m0-project-scaffold.md`。仅由对应 Agent 写入：Codex 使用 `codex-`，Claude 使用 `claude-`。

每份记录必须包含：任务与状态、改动文件和关键决定、已运行命令及实际结果、API/数据/配置变更、未完成项/风险/下一位 Agent 的首个动作，以及回滚方式（若有破坏性修改）。

交接记录不放密钥、隐私资料或大段命令输出。

## 请求完成后审查

Claude 交接可增加 `review_status: ready_for_review`、`task_id`、目标 worktree、base/head、本轮文件、实际 PASS/SKIP/FAIL 和未验证范围。Codex 审查报告存 `docs/reviews/`，不代写 Claude 的交接；完成标记与代码稳定性需同时验证。完整流程见 [Claude → Codex 审查](../claude-review-workflow.md)。
