# L04 迁移 015、凭据加密与仓储

```text
task_id: L04
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 5e1f96e
head_commit: 本任务提交
changed_files:
  - src/backend/migrations/015_user_model_configs.sql（新增）
  - src/backend/app/repositories/model_configs.py（新增；含 SealedKey）
  - src/backend/app/services/credentials.py（新增）
  - src/backend/app/config.py（personal 模式、MODEL_CREDENTIAL_KEY、MODEL_ENDPOINT_ALLOW_PRIVATE）
  - src/backend/pyproject.toml（cryptography==50.0.2）
  - .env.example（两个新变量及注释，从 L03 挪来）
  - tests/backend/test_l04.py（新增 11 例）
  - tests/backend/test_j10.py（最新迁移断言 014 → 015）
  - docs/tasks.md、docs/handoffs/claude-l04.md
```

## 交付

- 迁移 015：`user_model_configs`、`task_model_bindings` 两张表；`processing_tasks.created_by`、`model_calls.user_id` 两个可空列与索引。文件头写有 `ROLLBACK` 语句。
- `CredentialCipher`：AES-256-GCM，12 字节随机 nonce，关联数据为 `user_id`；`from_settings` 在根密钥缺失或非法时抛 `CredentialError`，不回退。
- 仓储：保存（首次或改地址必须带新密钥，否则 `KeyRequired`）、只改模型名保留密钥、清除时同事务作废本人未结束任务快照、记录测试结果、在调用方事务内复制快照、按任务读快照、终态清理。仓储只接触密文。
- 设置：`LLM_MODE` 接受 `personal`；`personal` 或已填根密钥时必须是 32 字节 URL 安全 base64；生产环境禁止 `MODEL_ENDPOINT_ALLOW_PRIVATE`；`.env` 中留空的布尔变量按未设置处理。
- `cryptography==50.0.2`：原本已是 `pdfminer.six` 的传递依赖，版本即当前环境已装版本，现为直接锁定依赖。

## verification

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_l04.py` | 先收集失败（模块不存在），实现后 11 passed |
| 后端全量 `pytest tests/backend tests/tooling` | exit 0，3572 通过、27 跳过 |
| `./scripts/verify.sh` | exit 0（基础档） |

## unverified

- 迁移在既有大库上的执行与备份恢复：只在测试用的新库上执行过。冲刺工作区的本地库会在下一次启动脚本运行迁移时升级（迁移前自动备份到 `src/backend/storage/backups/`）。

## api_and_data_changes

- 数据：迁移 015（见上）。新列可空，旧代码可读新库。
- 配置：新增 `MODEL_CREDENTIAL_KEY`、`MODEL_ENDPOINT_ALLOW_PRIVATE`；`LLM_MODE` 新增 `personal`。
- 依赖：`cryptography==50.0.2`。

## rollback

停 API 与 worker，恢复 `src/backend/storage/backups/*-before-015.sqlite`（或执行迁移文件中的 `ROLLBACK` 语句），再回退本提交。

## next_action

L05（出站地址校验与钉 IP）。
