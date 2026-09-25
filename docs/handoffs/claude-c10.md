# Claude 交接：C10 实现任务取消服务与 API

- review_status: ready_for_review
- task_id: C10
- 目标 worktree：`/home/user/wt-c10-task-cancel`，分支 `claude/c10-task-cancel`
- base：认领提交 `f0814cc`；head：本交接所在提交
- 状态：DONE（待 PR 审查/合并）；未 push、未开 PR

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/task_cancel.py` | `cancel_task(sqlite_url, task_id, *, course_id) -> CancelOutcome`；异常 `TaskNotFound`、`TaskNotCancellable(stage, reason)`（`.details == {stage, reason}`）；数据类 `TaskSnapshot`、`CancelOutcome(task, changed, sse_event)` |
| `src/backend/app/api/task_cancel.py` | `POST /api/v1/tasks/{tid}/cancel`，`operation_id="cancelTask"`，授权复用 C03 的 `task_teacher`；本地响应模型 `CancelledTaskSnapshot`、`TaskNotCancellableError`（见待决 1） |
| `src/backend/app/main.py` | 范围扩展：仅新增路由 import 与 `include_router` 两行 |
| `tests/backend/test_c10.py` | 33 个用例 |

### 行为（`specs/task-processing.md` §4）

- 一次调用 = 一个 `BEGIN IMMEDIATE` 事务：按 `id AND course_id` 读行 → 用 C08 `apply_event(state, TransitionEvent("cancel_request"))` 判定 → 比较并交换写入：
  `UPDATE … SET stage = ?, cancel_requested = 1, updated_at = now WHERE id = ? AND course_id = ? AND stage = <读到的 stage> AND cancel_requested = 0 AND stage IN (queued, parsing, extracting, merging)`。
  条件写落空时在同一事务内重读、重判一次；再落空抛 `RuntimeError`（行不一致，不掩盖）。
- `queued` → `cancelled`，`cancel_requested = true`（T3），`sse_event = "cancelled"`。
- `parsing` / `extracting` / `merging` 且标志为 false → 只置标志，`stage`、`progress` 与**租约列全部不动**（不强杀；worker 的令牌写入仍然成功），`sse_event = "stage"`。
- 标志已为 true → 幂等：不写任何数据（测试用 `PRAGMA data_version` 验证无提交），`changed = False`、`sse_event = None`。
- `persisting` → 409 `persisting_uninterruptible`；`awaiting_review` → 409 `processing_finished`；`completed` / `failed` / `cancelled` → 409 `already_terminal`，`details.stage` 为实际终态。均不写（I3）。**终态不是幂等 200**：规格 §4 与 TASK-5 明确「已 cancelled 后再取消 → 409」。
- 跨课程或不存在：服务抛 `TaskNotFound`；端点侧 `task_teacher` 已先按 §4.1 给出 404，服务再按 `course_id` 过滤一次（纵深防御）。

### 竞争（与 C09 同一写入序列）

C09 的 `claim_next`、`leased_transaction` / `fence` 都用 `BEGIN IMMEDIATE`，取消也是，所以同一行上的取消与 worker 写入被 SQLite 写锁串行，先提交者赢：

| 竞争 | 测试 | 结论 |
| --- | --- | --- |
| 取消 vs 领取（TASK-8） | 两线程 + `Barrier` 并发 12 轮；另有两种固定顺序 | 取消赢 → `cancelled`、`attempt = 0`、领取返回 `None`；领取赢 → 取消走置标志分支，`stage = parsing`、`cancel_requested = true`、令牌不变 |
| 取消 vs T5（TASK-6） | 两种顺序各一条 | 取消先 → worker 的 T5（`stage = merging AND cancel_requested = 0 AND lease_token = ?`）影响 0 行，随后 T8 → `cancelled`；T5 先 → 取消 409 `persisting_uninterruptible` |
| 交错：worker 事务已写 T5 未提交 | 取消线程被阻塞（`join(0.5)` 后仍存活），worker 提交后取消得 409 | 取消读不到提交前的 `merging` |
| 交错：取消事务已写标志未提交 | worker 的 `leased_transaction` 被阻塞，取消提交后 T5 影响 0 行、T8 成功 | 标志先写者赢 |
| 判定用的读过期 | monkeypatch 在判定后改写行 | 比较并交换落空 → 重读 → 409，标志未落到 `persisting` 行 |
| 标志已置、worker 失败（TASK-7） | `release_after_transient_failure` 最后一次尝试 | `failed` 且 `cancel_requested = 1`；再取消 409 `already_terminal` |
| 标志已置、租约过期（LEASE-8） | `reclaim_expired` | 回收者转 `cancelled`，此后领不到 |

## 接口 / 数据变更

- 新增端点实现 `cancelTask`（契约 B10 已有，未改契约、未改生成物、无迁移）。
- 200 响应体：`id, course_id, document_id, stage, progress, cancel_requested, created_at, updated_at`；`cancel_requested` 必然显式出现。测试用 `api.v1.yaml` 的 JSON Schema `Task` 与生成的 `Task` Pydantic 模型双重校验。
- 409 响应体：`{code: "TASK_NOT_CANCELLABLE", message, details: {stage, reason}}`，按 JSON Schema `TaskNotCancellableError` 与生成模型校验；`details` 只有两个键。
- 401 / 403 / 404 走 C03 的 `access_error_response`，只含 `code`、`message`，不含任何快照字段。
- 回滚：删除 `main.py` 中的两行路由注册即可下线端点；服务无持久结构变化。

## 验证（实际命令与结果）

均在 worktree 根目录，`V=/tmp/claude-0/-home-user-SmartSketch/f5e8fe9b-ebac-5377-b10c-8bfbef53bfde/scratchpad/venv`，每次运行使用新的 `PYTHONPYCACHEPREFIX=…/scratchpad/pyc-c10-$RANDOM`；未向 venv 安装任何包。

| 命令 | 结果 |
| --- | --- |
| 红灯：`PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_c10.py -q -p no:cacheprovider`（仅有测试时） | 收集错误 `ImportError: cannot import name 'task_cancel' from 'app.services'` |
| 首次绿灯 | `1 failed, 32 passed`：过期读用例的断言写错（拒绝会回滚同一事务内的模拟写入），修正断言后 `33 passed`，连跑 3 次均 `33 passed` |
| `… pytest tests/backend -q -p no:cacheprovider` | `1709 passed`（基线 1676 + 33） |
| `… pytest tests/contracts tests/tooling -q -p no:cacheprovider`，PATH 含 `b15-tools/node_modules/.bin` | `305 passed`（不含该 PATH 时 `3 failed, 302 passed`，均为缺 `openapi-typescript` 的环境原因，与本任务无关） |
| `PATH=$V/bin:…/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh` | 退出码 0，`PASS contracts gate`、`Scaffold verification passed.` |
| `git diff --check`（含暂存后 `git diff --cached --check`） | 无输出 |

## 反向篡改（改前 `cp` 备份，改回后 `cmp` 一致，每次新的 PYTHONPYCACHEPREFIX）

| # | 篡改 | 结果 |
| --- | --- | --- |
| 1 | 比较并交换去掉 `stage = ? AND cancel_requested = 0 AND stage IN (…)` 条件 | 1 failed（过期读用例） |
| 2 | 终态可再取消（`already_terminal` 改为幂等成功） | 9 failed |
| 3 | 跳过授权（`task_teacher` 换成 `current_user`，课程按任务回查） | 1 failed（授权矩阵：学生得 200） |
| 4 | 取消时清空租约（等同强杀 worker） | 9 failed |
| 5 | `BEGIN IMMEDIATE` 改为延迟 `BEGIN` | 2 failed（交错用例、并发领取用例） |
| 6 | 读行去掉 `course_id` 条件 | 1 failed（课程隔离用例） |

六处改回后 `cmp` 均一致，复跑 `33 passed`。

## 风险

- 服务层直接执行 SQL（见待决 2），与后端规则「持久化放 repositories」不一致。
- SSE 推送尚未实现：`CancelOutcome.sse_event` 只是给 C11 的指示；在 C11 合入前，已订阅的客户端收不到取消引起的事件（只能靠 GET 快照或 200 响应体）。
- `test_cancel_and_claim_race_on_two_connections_has_exactly_one_winner` 不保证每次都覆盖两种赢家（线程调度决定）；两种赢家各有一条固定顺序用例兜底。
- 交错用例用 `thread.join(0.5)` 判断「被阻塞」，依赖 `BUSY_TIMEOUT_MS` 远大于 0.5 秒；若将来把忙等超时调到极小，这两条会误报。

## 待决（未擅自拍板）

1. **响应模型位置**：`app.schemas.contracts` 只导出了 Course 相关生成类，没有 `Task` / `TaskNotCancellableError`，而 `schemas/` 不在文件锁内，所以本地定义在 `api/task_cancel.py`（与 C16 的 `EventTicket` 同一先例）。建议后续小任务在 `app/schemas/contracts.py` 导出生成的 `Task`、`TaskNotCancellableError`，路由改用它们（届时需注意 B10F-R01）。
2. **SQL 所在层**：比较并交换与读行在 `services/task_cancel.py` 的 `_read_task` / `_write_cancel`，因为 `repositories/tasks.py` 不在文件锁内。建议移到 `repositories/tasks.py`（如 `read_task_for_update(database, …)`、`cas_cancel(database, …)`），服务只保留判定与事务边界。
3. **B10F-R01**：生成的 `TaskCancelled.cancel_requested` 为 `Literal[True] = True`（非必填）。本端点不受影响：本地模型该字段无默认值，测试断言响应体显式含该键并同时过 JSON Schema。但若按待决 1 改用生成模型并开启 `exclude_unset`/`exclude_defaults`，可能漏发该字段——应先修 B10F-R01。B10F-R02（details 分支缺 `additionalProperties: false`）同样不影响本端点：本地 `TaskNotCancellableDetails` 只输出两个键，测试断言键集合。
4. **200 快照的可选字段**：`counts`、`failed_chunks`、`timings_ms` 目前无存储列，响应中缺省（契约允许）。由 E12/C11 落列后，取消响应是否也要带上，待 GET 快照端点（C11）统一决定。
5. **SSE 事件投递方式**：规格要求 T3 推 `cancelled` 并关流、置标志推同阶段 `stage` 事件；推送通道归 C11。C11 可选择在路由里消费 `sse_event`，或由事件流轮询 `updated_at`/`cancel_requested` 变化，需 C11 决定。

## 下一步（C11 / D11 worker 如何响应取消意图）

- **worker 检查点**（阶段边界与 `extracting` 块间）：在 `leased_transaction(url, tid, token)` 内读 `cancel_requested`；为 1 时执行 T8：`UPDATE … SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL WHERE id = ? AND lease_token = ? AND stage IN (parsing, extracting, merging) AND cancel_requested = 1`，并推 `cancelled` 事件后停止；不得再写 Neo4j。
- **T5 必须带条件**：`WHERE id = ? AND lease_token = ? AND stage = 'merging' AND cancel_requested = 0`；影响 0 行时重读，若标志为 1 走 T8，否则视为租约已丢（`LeaseLost`）。
- 阶段推进（T4）同理带 `cancel_requested = 0`，否则转 T8；在途模型调用不打断，其结果不写检查点。
- 崩溃后由 `reclaim_expired` 代行检查点（C09 已实现），C11 负责为其返回的 `cancelled` 推事件。
- 事件流：C11 在取消 200 后按 `CancelOutcome.sse_event` 推送（重复取消为 `None`，不推）。
