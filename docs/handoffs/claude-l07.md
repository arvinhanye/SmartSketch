# L07 上传绑定密钥快照与 worker 按任务取模型

```text
task_id: L07
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: d2e97c0
head_commit: 本任务提交
changed_files:
  - src/backend/app/repositories/tasks.py（created_by、bind_model_config、ModelConfigMissing）
  - src/backend/app/services/materials.py（uploaded_by、model_config_ready）
  - src/backend/app/api/materials.py（personal 模式未配置 409，读文件体前先检查）
  - src/backend/app/services/ai/policy.py（CallAttribution.user_id 写入调用记录）
  - src/backend/app/repositories/model_calls.py（CallRecord.user_id 与列写入）
  - src/backend/app/workers/extract_task.py（工具包 user_id/guard/model、尝试前检查、fail_for_credential）
  - src/backend/app/workers/persist_graph.py（ToolkitSource，按租约解析工具包）
  - src/backend/app/workers/toolkits.py（新增 TaskToolkits）
  - src/backend/app/workers/runner.py（personal 模式按任务构建、BindingScrub 维护钩子）
  - src/backend/app/services/ai/factory.py（personal 模式无全站客户端）
  - tests/backend/test_l07.py（新增 11 例）、tests/backend/test_e12.py（追加 2 例）
  - docs/tasks.md、docs/handoffs/claude-l07.md
```

## 交付与语义（与 ADR-080 决定 3 一致）

| 场景 | 实测行为（用例） |
| --- | --- |
| 上传时已配置 | 资料、任务、快照同一事务写入，`created_by` 记录上传者（`test_create_task_records_creator_and_snapshot`） |
| 上传时未配置 | 读文件体前即 409 `MODEL_CONFIG_REQUIRED`；事务内竞态再兜一次，资料、任务、落盘文件都不留（`test_upload_requires_config_then_binds`、`test_create_task_without_config_writes_nothing`） |
| 两位教师不同 key 与模型 | 各自的地址、密钥、模型名，`model_calls.user_id` 各归本人（`test_two_teachers_use_their_own_key_and_model`） |
| 建任务后改配置 | 已建任务仍用旧快照（`test_changing_config_does_not_change_a_queued_task`） |
| worker 重启/接管 | 重新解析得到同一快照（`test_restart_resolves_the_same_snapshot`） |
| 清除配置 | 未开始的任务在解析时、进行中的任务在下一个块或小节尝试开始前终止，`LLM_UNAVAILABLE` + `credential_revoked`，不再发请求（`test_clearing_config_revokes_before_and_during_a_task`、`test_e12` 两例） |
| 无快照 / 根密钥已换 | `credential_missing` / `credential_unreadable`（两例） |
| 任务结束 | 维护钩子把快照密文置空（`test_binding_scrub_hook`） |
| 非 personal 模式 | 仍用全局工具包，既有测试不变（`test_build_toolkit_by_mode`） |

任务失败的线上形状：`stage = failed`、`error_code = LLM_UNAVAILABLE`、`error_details = {"reason": "credential_revoked"}`、`error_message` 提示检查「模型 API 设置」后重新上传；租约已释放。

## verification

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_l07.py` | 先收集失败；实现后 11 passed（与 test_l04 合计 22） |
| `pytest tests/backend/test_e12.py` | 39 passed（含新增 2 例） |
| 后端全量（第一次） | exit 1：38 个失败，均在 `test_d10`（35）与 `test_c09`（3），`table processing_tasks has no column named created_by` |
| 修复后 `pytest test_d10.py test_c09.py test_l07.py test_l04.py` | 111 passed |
| 后端全量（修复后） | 与 L08 一起运行，结果记在 `claude-l08.md` |
| 集成（不含端到端） | 未运行成功：Docker 守护进程未运行，无法启动一次性 Neo4j |
| `./scripts/verify.sh` | exit 0（基础档） |

## 执行中发现并修复的问题

- 现象：后端全量 38 个失败，`sqlite3.OperationalError: table processing_tasks has no column named created_by`。
- 根因：`test_d10`、`test_c09` 有意只执行到较早的迁移，在不含 015 新列的表上创建任务；`_insert_task` 无条件写入 `created_by`。
- 修复：只有提供了 `created_by` 才写该列；未提供时 SQL 与改动前完全相同。非 personal 模式与旧库的行为因此不变。

## unverified

- personal 模式下真实网页上传到 `awaiting_review`：在 L10 走查中验证。
- 运行中的 worker 进程级维护钩子：只在单元层面验证了 `BindingScrub`。
- 集成测试（真实 Neo4j 上的流水线）：本轮因 Docker 未运行未执行；Docker 恢复后补跑。

## api_and_data_changes

- 上传接口在 personal 模式下新增 409（契约 L03 已定义）。
- 写入新列：`processing_tasks.created_by`、`model_calls.user_id`、`task_model_bindings`（迁移 015 已在 L04）。

## rollback

回退本提交；已写入的快照行可保留（旧代码不读该表），或按 L04 的回滚步骤处理。

## next_action

L08（问答按用户取模型与按用户日预算）。
