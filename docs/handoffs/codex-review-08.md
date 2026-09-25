# REVIEW-08 交接：A05 身份边界与 A07 模型配置

- 范围：固定提交 A05 `e0b7ccd`（base `931361d`）和 A07 `af9ff7d`（base `ab04053`）各四文件文档差异；两次稳定观察、停止后无会话活动。
- 交付：`docs/reviews/codex-claude-a05-a07-2026-09-23-0804z.md`。A05 无新问题；A07-R01 P2：`model_calls` 的物理调用与问答去重身份未明确，预算可能少计。
- 验证：两提交 `git diff --check` exit 0；目标各自 `./scripts/verify.sh` exit 0，仅骨架/hook。无运行时身份或预算实现、自动测试；D-02a～f 取值未签收。
- 接口/数据变更：本交接仅记录审查；建议 E04/C01 实现前修订 `model_calls` 每次物理调用的稳定 ID，并支持无任务 ID 的问答请求。
- 风险/下一步：A07-R01 需先修订 A06/ADR-011/A07 协议，再补重试、备用、问答的计费回归。A04 worktree 有新活动和新 HEAD，本批未审；S-07 旧待审范围保留。
