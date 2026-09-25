# Claude 交接：C11 实现任务查询与 GET SSE

- review_status: ready_for_review
- task_id: C11
- 目标 worktree：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-ad8a4f552685621be`，分支 `claude/c11-task-events`
- base：认领提交 `6c50d2c`；head：本交接所在提交
- 状态：DONE（待 PR 审查/合并）；已 push，未开 PR、未改 issue（由协调方处理）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/task_events.py` | `load_task`（按 `id AND course_id` 读行，见待决 1）、`task_body`（契约 `Task` JSON）、`snapshot_event` / `EventDiffer` / `TaskStreamEvent`（帧构造与差分）、`TaskEventStreams`（轮询 + 心跳的异步生成器与订阅计数）、`authorize_ticket`（§5.2 核销 + 重新授权） |
| `src/backend/app/api/tasks.py` | `GET /api/v1/tasks/{tid}`（`getTask`，授权复用 C03 `task_teacher`）；`GET /api/v1/tasks/{tid}/events`（`streamTaskEvents`，只认 `?ticket=`）；本地响应模型 `TaskSnapshotBody`；`_EventStreamResponse`（结束时必 `aclose()` 生成器） |
| `src/backend/app/main.py` | 范围扩展：仅新增路由 import 与 `include_router` 两行 |
| `tests/backend/test_c11.py` | 46 个用例 |
| `docs/tasks.md` | 仅 C11 表的「状态」「证据」两列 |

## 行为规则

### `GET /api/v1/tasks/{tid}`

- 授权即 C03 `task_teacher`：无/坏令牌 401；学生成员 403 `ROLE_FORBIDDEN`；非成员、任务不存在、跨课程三者同形 404 `NOT_FOUND`，只含 `code`、`message`（TASK-19）。
- 读行再按 `course_id` 过滤一次（纵深防御，I7）。返回 `id, course_id, document_id, stage, progress, cancel_requested, created_at, updated_at`；只有 `failed` 带 `error {code, message, details?}`，仍是 200。`cancel_requested` 必然显式出现（本地模型无默认值，规避 B10F-R01）。

### `GET /api/v1/tasks/{tid}/events`

- 鉴权（`specs/identity-access.md` §5.2）：不读 `Authorization` 头；`ticket` 缺失/空 → 401；`redeem_ticket`（C16 条件 UPDATE，核销即作废、过期或与任务不符影响 0 行）→ 401；票据所属账号不存在或已停用 → 401；再以该账号执行 `AccessService.require_task`（非成员/不存在 404，非教师 403）。全部通过才构造流响应。票据在第 1 步已核销，后续 403/404 也不退还（按 §5.2 顺序）。
- 响应头：`text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。帧为 `event: <name>\ndata: <单行紧凑 JSON>\n\n`，心跳为 `:ping\n\n`。
- 事件来源：**轮询 SQLite 任务行**（默认 1 秒，见待决 4），不依赖进程内总线（API 与 worker 不同进程，§8.1）。读行在 `anyio.to_thread` 中执行，不阻塞事件循环。
- 建连先补快照：非终态 `stage`；`completed` → `done`（`{task_id, stage, progress: 1}`）；`failed` → `error`（含 `error`、`cancel_requested`）；`cancelled` → `cancelled`（`cancel_requested: true`）。`awaiting_review` 快照与三种终态事件都是结束事件，发出后立即结束生成器（关流）。
- 差分（`EventDiffer`，每连接一个）：阶段前进、同阶段 `progress` 上升、`cancel_requested` 由 false 变 true 才推 `stage`；只改 `updated_at`、重复取消、`progress` 回退、阶段回退都不推（I1/I2）；推出的 `progress` 取已推最大值，按连接单调。进入 `awaiting_review` 推 `progress 0.95` 后关流；进入 `failed`/`cancelled` 推 `error`/`cancelled` 后关流。每个连接恰好一条结束事件。
- 两次轮询之间任务已被发布（直接看到 `completed`）时，处理期连接仍以 `stage = awaiting_review`（0.95）收尾，不发 `done`（§7：`done` 只作为发布后新建连接的首条快照）。见待决 5。
- 心跳：从建连起每 `heartbeat_seconds`（默认 15）发一次 `:ping`，与事件无关；worker 崩溃时任务停在原阶段，连接只收心跳。
- 多订阅者：每个连接独立轮询、各自先收快照，此后变化各自推出（等效广播）。
- 断开释放：`TaskEventStreams` 以 `try/finally` 维护每任务订阅计数；Starlette 两条断开路径都覆盖——ASGI spec < 2.4 由 `http.disconnect` 取消流；≥ 2.4（uvicorn）只在发送失败时发现，生成器会停在 `yield` 上，所以 `_EventStreamResponse` 在 `finally` 中 `aclose()` 生成器。测试对两条路径都断言计数归零、应用协程结束。
- 测试注入：`app.state.task_event_streams = TaskEventStreams(poll_seconds=…, heartbeat_seconds=…)`；未设置时路由依赖按默认值懒创建。

## 接口 / 数据变更

- 新增 `getTask`、`streamTaskEvents` 两个端点实现（契约 B10 已有；未改契约、生成物，无迁移）。
- 应用内 OpenAPI 中 `ticket` 查询参数为可选：缺失必须按契约回 401 而不是 FastAPI 的 422。契约真源仍为 `required: true`，未改。
- 回滚：删除 `main.py` 中两行路由注册即可下线；无持久结构变化。

## 验证（实际命令与结果）

均在 worktree 根目录。scratchpad 为多个并行子任务共享，C11 只用自有目录 `SC=<scratchpad>/c11`：私有 venv `$SC/venv`（`pip install -e "src/backend[test]" 'datamodel-code-generator==0.26.3'`，其 editable 映射指向本 worktree），脚本 `$SC/pt.sh` 每次运行都显式设置 `PYTHONPATH=<本 worktree>/src/backend`、新的 `PYTHONPYCACHEPREFIX=$SC/pyc-…`，并加 `-p no:cacheprovider`。（首次基线曾误用共享 venv，其 `app` 指向别的 worktree；已用私有 venv 重跑，下表均为重跑结果。）

| 命令 | 结果 |
| --- | --- |
| 基线：`$SC/pt.sh tests/backend -q --ignore=tests/backend/test_c11.py` | `2105 passed` |
| 红灯：`$SC/pt.sh tests/backend/test_c11.py -q`（仅有测试时） | 收集错误 `ImportError: cannot import name 'task_events' from 'app.services'` |
| 首次绿灯 | `1 failed, 45 passed`：测试驱动把 Starlette 的 `ClientDisconnect` 当成 `OSError` 捕获（它不是），改驱动后 `46 passed` |
| 加固测试驱动后（见「反向篡改」第 3、9 项）连跑 3 次 | 均 `46 passed`（约 5.3 秒） |
| `$SC/pt.sh tests/backend -q` | `2151 passed`（基线 2105 + 46） |
| `$SC/pt.sh tests/contracts tests/tooling -q` | `323 passed` |
| `PATH=$SC/venv/bin:$PATH PYTHONPATH=<worktree>/src/backend ./scripts/verify.sh`（脚本 `$SC/c11_verify.sh`） | 退出码 0，`PASS contracts gate`、`Scaffold verification passed.` |
| `git diff --check` | 无输出 |

## 反向篡改（脚本 `$SC/c11_tamper.py`：改前备份，跑 `test_c11.py`，改回后 `filecmp` 逐字节一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| 1 | SSE 核销后跳过重新授权（不查成员/角色） | 1 failed |
| 2 | GET 跳过授权（只认登录，按任务回查课程） | 1 failed |
| 3 | `awaiting_review` 不关流 | 9 failed |
| 4 | 结束事件发两条 | 7 failed |
| 5 | 断开不释放订阅（去掉 `finally`） | 4 failed |
| 6 | 票据可重用（核销失败时按哈希回查、忽略 `used_at`） | 1 failed |
| 7 | 进度回退也推送 | 2 failed |
| 8 | 去掉 `aclose` 包装（直接 `StreamingResponse`） | 1 failed（spec 2.4 断开路径） |
| 9 | 建连不补发非终态快照 | 11 failed |

第一轮篡改暴露测试驱动缺陷：第 3 项让 TestClient 永远等流结束（挂死而非失败），第 9 项让 `event()` 在心跳流上无限等待。已改为所有 SSE 请求走带总超时的 ASGI 驱动（`sse_get` / `Stream`），之后九项均在限时内判红。全部改回后复跑 `46 passed`。

## 风险

- 轮询粒度：两次轮询之间的多次变化合并为一条（例如一次轮询内 `parsing → merging` 只推 `merging`；置标志后立即 T8 只推 `cancelled`）。满足「进入新阶段推 stage」按观察到的状态成立，但中间阶段不回放。
- 每个连接每秒一次 `SELECT`（主键 + `course_id`），连接数大时 SQLite 读压力线性增长；WAL 下读不阻塞写。
- 流式测试依赖真实时间（轮询 5 ms、心跳 20～50 ms），在极慢机器上等待上限为 5 秒；未见抖动（多次连跑稳定）。
- 任务行在流中途消失（目前外键 `RESTRICT` 使其不可能）时直接关流、不发结束事件。

## 待决（未擅自拍板）

1. **SQL 所在层**：`load_task` 在 `services/task_events.py`，与 C10 `services/task_cancel.py::_read_task` 同法（`repositories/tasks.py` 不在文件锁内），行→`TaskSnapshot` 映射与 C10 重复。建议小任务把两者合并为 `repositories/tasks.py::get_task_snapshot(url, task_id, *, course_id)`（含 `error_*` 列），服务只保留判定/差分。
2. **响应模型位置**：`TaskSnapshotBody` 定义在 `api/tasks.py`（与 C10 `CancelledTaskSnapshot`、C16 `EventTicket` 同一先例）。建议 `app/schemas/contracts.py` 导出生成的 `Task`；改用前须先修 B10F-R01（生成的 `TaskCancelled.cancel_requested` 有默认值，配合 `exclude_unset`/`exclude_defaults` 会漏发）。本端点用 `response_model_exclude_none=True`，不受影响（测试断言 `cancel_requested` 必现并过 JSON Schema）。B10F-R02 与本任务无关。
3. **可选字段**：`counts`、`failed_chunks`、`timings_ms`、`elapsed_ms` 无存储列，GET 快照与事件均缺省（契约允许）。E12 落列后需在 `task_body` / 事件中补上，并决定 `counts` 变化是否单独触发 `stage` 推送（规格只列阶段、进度、取消标志三种触发）。
4. **轮询间隔配置**：默认 1 秒写在服务常量，未接环境变量（`config.py` 不在锁内）。若需可调，建议 C01/A07 增加 `TASK_EVENTS_POLL_SECONDS` 并写入 `.env.example`；心跳 15 秒是契约值，不建议可配。
5. **轮询错过 `awaiting_review`**：处理期连接直接看到 `completed` 时合成一条 `stage = awaiting_review, progress 0.95, cancel_requested = false` 收尾。规格未明写此情形，本实现按「处理期连接永远收不到 done」推导，请审查确认。
6. **C10 的 `CancelOutcome.sse_event`**：C11 以轮询数据库为唯一事件来源，未消费该提示字段（取消写入由轮询自然观察到）。可保留作文档用途，或在后续清理中删除。
7. **心跳节奏**：从建连起固定间隔，事件不重置心跳计时；若希望「空闲 15 秒才 ping」可改，属实现细节。

## 下一步

- C12（前端 SSE 客户端）：按 `events.v1.md` §4 出错即关、重新申领票据再连；收到任何结束事件后主动 `close()`。
- 待决 1、2 可合并为一个「任务读模型下沉仓储 + 导出生成 `Task`」的小任务，同时修 B10F-R01/R02。
