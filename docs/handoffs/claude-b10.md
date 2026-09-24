# Claude 交接：B10 任务与 SSE 契约

- `task_id`: B10
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a09-dev-environment-check-8e5e93`，分支 `claude/b10-task-sse-contract`
- `base_commit`: `9d2437e`（main，含 B08/B09）
- 负责人：ArvinHan（Claude 执行）
- 依据：`specs/task-processing.md`「交给后续任务的契约缺口」B10 各行、§1、§4、§5、§7、TASK-17（ADR-010）；`specs/identity-access.md` §5、§7 B10 行、访问矩阵任务行（ADR-013）。只落实这两份已签收规格列出的改动，没有新增需求。

## 交付物

- `src/contracts/api.v1.yaml`
  - `TaskEvent` 从宽松对象改为 `oneOf` 四种事件：`TaskStageEvent`、`TaskDoneEvent`、`TaskErrorEvent`、`TaskCancelledEvent`，`discriminator: stage`，九个阶段全部映射。四种事件都设 `additionalProperties: false`，因此事件不能带 `failed_chunks`，非 `failed` 的事件也不能带 `error`。
    - stage 事件：`stage` 取 `queued`～`awaiting_review`，`cancel_requested` 必填。
    - done：`stage = completed` 且 `progress = 1`。
    - error：`stage = failed`，`error` 必填且不为 null。
    - cancelled：`stage = cancelled` 且 `cancel_requested = true`。
  - `Task`：`cancel_requested` 必填；新增 `failed_chunks`（`FailedChunk`：`chunk_id`、`code`，`page` / `section_path` 至少一个）；用 `if/then/else` 约束 `stage = failed` ⇔ `error` 非 null（TASK-17）。
  - `TaskCounts.chunks_failed`。
  - `TaskStage` 描述改为只指向 `specs/task-processing.md` §1、§2，删掉「任意阶段可转」一类自写规则。
  - 新增 `POST /api/v1/tasks/{tid}/event-ticket`（`issueEventTicket`，沿用 Bearer）和 `EventTicket`（`ticket` 为 URL 安全字符串，至少 22 字符即 128 位；`expires_in` 固定为 60）。
  - `streamTaskEvents` 声明 `security: [{eventTicket: []}]` 覆盖全局，并加必填查询参数 `ticket`；描述写明只覆盖处理阶段、按连接收尾，以及票据失败 → 401。
  - `cancelTask` 的 200 改为「请求已受理，以 `stage` 与 `cancel_requested` 为准」；409 写明 `TASK_NOT_CANCELLABLE` 和三种 `reason`。
  - 四个任务类操作的 403 只表示 `ROLE_FORBIDDEN`；404 表示任务不存在或非成员，两者不可区分。
- `src/contracts/events.v1.md`
  - §1：`?token=` 改为票据流程，并指向 identity-access §5。
  - §2：删除「规范转换表」，改为指向规格；事件表列出各自 schema 与必填字段；顺序保证改为按连接收尾、`awaiting_review` 关流、`done` 只作发布后建连的快照；示例补上 `cancel_requested` 与 `chunks_failed`。
  - §4：不依赖 `EventSource` 自动重连，由客户端重新申领票据。
  - §5：丢弃其他任务的迟到事件。
  - §6：登记这次原地修改的例外依据。
- 重新生成 `src/contracts/v1/generated/`：`openapi.json`、`schemas/TaskEvent.schema.json`、`python/models.py`、`typescript/openapi.d.ts`。
- `tests/contracts/test_b10.py`（36 个用例），并接入 `scripts/verify/contracts.sh`（同 B08/B09 先例）。
- 状态标注：`specs/task-processing.md` 契约缺口表的 B10 行、`specs/identity-access.md` §7 B10 行、`src/contracts/README.md`（25 条路径）、`docs/tasks.md`。

## 决定与理由

- **按 `stage` 判别，不在 data 里加 `event` 字段**：四种事件的 `stage` 取值互不相交，按 `stage` 已能唯一判别，也不新增 wire 字段。架构表只规定问答流有 `data.event`。生成的 TypeScript 是按 `stage` 字面量可收窄的联合类型。
- **事件 schema 用 `additionalProperties: false`**：规格写明「SSE 事件只带计数」。只靠描述文字拦不住，按 R04 的教训写成结构约束。
- **`TaskCancelledEvent.cancel_requested` 固定为 true**：§4 的取消矩阵里，所有通往 `cancelled` 的路径都会先置标志（`queued` 走 T3 时也同时置标志），TASK-3 也要求 `cancel_requested = true`。
- **票据 401 的语义写在操作描述里，401 本身保持纯 `$ref`**：B08 的回归要求每个受保护操作的 401 严格等于共享响应；为了不改动 B08 的测试，把说明移到了操作描述。
- **原地修改 `events.v1.md` 而不升 v2**：依据 `specs/task-processing.md` §7（ADR-010）——v1 尚无消费者，C11/C12 还未实现。已在 §6 登记，此后再改必须升 v2。

## 实际验证（macOS）

| 命令 | 结果 |
| --- | --- |
| 改真源前 `python3 -m pytest tests/contracts/test_b10.py -q` | 27 failed / 9 passed。通过的 7 条是正例，旧宽松 schema 本来就接受；2 条是空载荷负例，旧 schema 本来就拒绝，作为回归保护保留 |
| 改真源并重新生成后 | 36 passed |
| `./scripts/gen-contracts.sh --check` | 生成物与真源一致 |
| `./scripts/verify.sh` | exit 0：命名基线、生成物一致、22 项门禁负例、B08 5、B09 5、B10 36 |
| 生成物可用性 | `python/models.py` 可解析，含 `TaskStageEvent` 等类；`tsc --noEmit --strict` 检查 `openapi.d.ts` exit 0 |
| 反向篡改（逐项改坏 YAML 后运行 B10，再恢复） | 去掉 Task 的 if/then/else → 6 failed；去掉 stage 事件的 `additionalProperties` → 2 failed；去掉 cancelled 的 `const true` → 1；去掉流的 `security` → 1；去掉 `FailedChunk.anyOf` → 1；去掉 done 的 `progress` 常量 → 1 |
| `git diff --check` | exit 0 |

过程中暂时出现过一次 B08 回归失败，原因是给 SSE 的 401 加了描述。已改为把说明放进操作描述，B08 测试未改动。

## 风险

- `TaskEvent` 与 `Task` 收紧属于结构上的破坏性变更。目前没有消费者（后端 C10/C11、前端 C12/H02 均未实现），生成类型的调用点为 0。
- `datamodel-codegen` 与 `openapi-typescript` 会忽略 `if/then/else`，`failed ⇔ error` 只由结构校验（jsonschema）和运行时实现保证。C10/C11 实现时应在服务端校验，或直接用 `TaskEvent` 联合类型构造事件。
  - **已由 REVIEW-B10-R01 解决**：`Task` 改为按 `stage` 判别的四个分支，生成的 Pydantic / TS 类型直接带上该约束，见 `docs/handoffs/claude-review-b10.md`。
- 后端运行时（票据表、核销、SSE 端点）归 C11/C16，本任务不含。

## 下一步

- 请 Codex 审查；之后继续 B11（图谱编辑和版本契约），叠在本分支上。

## 回滚

撤销本分支提交即可：契约真源、`events.v1.md`、生成物、`test_b10.py`、门禁接入行和状态标注。无数据库或外部状态。
