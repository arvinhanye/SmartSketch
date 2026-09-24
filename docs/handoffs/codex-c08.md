# C08 状态迁移纯函数交接（2026-09-24）

- **任务与状态**：C08「实现状态迁移纯函数」，实现和本地验证完成；PR #176 与 issue #65 均待审，issue 已标 `status:in-review`，合入前保持开放。
- **基线与分支**：始于 `origin/main@62cbbc7`（含 PR #175 的 Claude 交接），随后同步 `origin/main@248b895`（B13/C01 已合入）；`codex/c08-task-state`，隔离 worktree `/Users/arvinhan/.codex/worktrees/c08-task-state/SmartSketch`。
- **所有权**：仅新增 `src/backend/app/services/task_state.py` 和 `tests/backend/test_c08.py`；协调状态更新 `docs/tasks.md` 与本交接文件。未编辑 B10/B13 契约或 C01/B11 文件。

## 输入、交付与边界

- 输入：`specs/task-processing.md` §1～§4、TASK-16；`src/contracts/events.v1.md` 阶段进度区间；B10 Task 形状。A03/B10 均已合入。
- 输出：不可变 `TaskState`、`TaskError`、`TransitionEvent`，以及 `apply_event(state, event) -> Applied | Rejected`。`Applied.changed=false` 明确表示重复取消、无取消标志的 checkpoint 或同值进度无需写入；`Rejected` 保留原状态对象和原因。
- 覆盖 T2～T9：领取、阶段边界、检查点、阶段内进度、持久化完成、失败、取消、发布；T1 创建任务归 C06 API 事务，不在事件词表。阶段进度区间、固定进度、单调性、终态不可变、`failed ⇔ error`、取消标志只增不减均由纯函数检查。
- 无 API、数据库、wire DTO、配置、依赖、迁移或已签收规范改动；C09 负责 CAS/租约持久化，C11/F13 等消费结果前必须通过条件写提交，提交成功后才能推送事件。纯函数本身不裁决并发。

## 验证证据

- TDD：首个定向测试先因模块缺失失败；一次扩展测试发现「取消挂起时进度上报丢失标志」，修复并复测。独立代码复核又发现终态错误详情的可变别名和畸形输入异常，先加四个失败用例再修复。
- `PYTHONPATH=src/backend PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' /private/tmp/smartsketch-c08-venv/bin/python -m pytest tests/backend/test_c08.py -q`：67 passed。
- 初始基线后端 125 passed；同步 `origin/main@248b895` 后同一解释器运行 `tests/backend`：143 passed，1 条来自 FastAPI TestClient/httpx 的现有弃用警告。
- `PATH=/private/tmp/smartsketch-c08-venv/bin:$PATH PYTHONPATH=src/backend PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' ./scripts/verify.sh`：同步后通过；契约门禁负例 24 项、B08 5、B09 5、B10 45、B13 52 全通过。
- `git diff --check`：通过。隔离 venv 使用锁定 Python 依赖，不写入仓库。

## 风险、协作、回滚

- 后续 C09/C11 集成需把 `Rejected.reason` 映射到仓储竞争/HTTP 409；本函数只处理已取得的当前状态，不替代数据库行条件更新。`progress(p)` 在取消请求挂起、检查点到来之前仍按规范允许单调更新，并保留取消标志。
- B10 生成类型对固定进度约束的表达不足，C08 检查内部状态；C11 从数据库生成快照时仍应确保固定进度和 `failed ⇔ error`。`TaskError.details` 在构造时递归复制为只读 JSON-like 结构；后续 wire 序列化方需转换成普通 dict/list。
- 回滚：仅撤销本分支的两个新增 Python 文件及本交接/任务板增量，不触碰其他成员分支或任务数据；无数据迁移。
- 下一步：审核 PR #176、运行 CI；合入后将 #65 和任务板转 DONE，再解除 C09/C11/F13 对 C08 的依赖标记。B13 #32、C01 #174 已合入，#55/#58 已关闭；B13 R09 由 [#178](https://github.com/arvinhanye/SmartSketch/issues/178) 独立跟踪。
