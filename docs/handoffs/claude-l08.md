# L08 问答按用户取模型与按用户日预算

```text
task_id: L08
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: bce4979
head_commit: 本任务提交
changed_files:
  - src/backend/app/repositories/model_calls.py（_day_billed 可按用户统计；预写检查用记录的 user_id）
  - src/backend/app/services/qa/rewrite.py、generate.py（构造参数 user_id，写入调用归属）
  - src/backend/app/services/qa/user_models.py（新增 UserChatModels）
  - src/backend/app/services/qa/chat.py（with_models；MODEL_CONFIG_REQUIRED 映射 409）
  - src/backend/app/api/chat.py（personal 模式基础服务不带模型；user_chat_service）
  - tests/backend/test_l08.py（新增 9 例）
  - docs/tasks.md、docs/handoffs/claude-l08.md
```

## 交付

- `UserChatModels.for_user`：按「用户 + 配置版本」缓存改写器与生成器，每个用户一份独立的 `ModelCallPolicy`，熔断状态互不影响；配置版本变化即重建；清除配置后抛 `ModelConfigRequired`；容量有界（默认 64），最久未用先淘汰。
- 问答路由：非 personal 模式完全沿用原 `chat_service`（既有测试替换该函数的方式仍然有效）；personal 模式下未配置返回 409 `MODEL_CONFIG_REQUIRED` 并写入问答日志，不发任何模型调用；密文无法解密按 `LLM_UNAVAILABLE` + `auth` 返回，提示检查个人配置。
- 日预算：调用记录带 `user_id` 时只统计该用户当天用量；不带时沿用全站合计（全局模式行为不变）。

## verification

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_l08.py` | 先收集失败；实现后 9 passed |
| 后端全量 `pytest tests/backend tests/tooling`（含 L07 修复与 L08） | exit 0，3645 通过、27 跳过 |
| `./scripts/verify.sh` | exit 0（基础档） |
| 集成（不含端到端，覆盖 L07、L08） | 提交时仍在运行，结果补记在 `claude-l09-handoff.md` |

用例覆盖：未配置被拒；两用户各用自己的地址、密钥、模型且调用记录各归本人；一人密钥被拒（熔断只落在本人）时另一人照常回答、两人策略对象不同；配置换版本后用新密钥、清除后被拒；缓存容量；按用户日预算与全局日预算；`ChatFailure` 409；问答路由未配置返回 409 且日志一行、模型调用为零。

## unverified

- 真实问答（需要向量服务）：等向量服务可达后在 L02 补测与 L10 走查。

## api_and_data_changes

问答接口在 personal 模式下新增 409（契约 L03 已定义）；`model_calls.user_id` 开始写入问答调用。

## rollback

回退本提交。

## next_action

L09（在线向量、拒绝 local、正式启动入口）与 L10（前端设置页）。
