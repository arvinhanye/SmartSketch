# 交接：审查 B10（PR #31）并修正四项契约约束

- `task_id`: REVIEW-B10
- `status`: 审查完成；R01～R04 已在本 PR 内修正，R05～R08 不阻塞、未改
- `审查目标`: `origin/claude/b10-task-sse-contract` @ `3771ae1`（base `9d2437e`）
- `依据`: `specs/task-processing.md` §1、§4、§7、I5、TASK-7/17（ADR-010）；`specs/identity-access.md` §5、§7（ADR-013）

## 审查结论

契约与两份已签收规格逐项对上：事件判别、票据申领与核销、任务类 403/404、取消 200/409 语义、`events.v1.md` 的关流与重连。没有会导致运行错误的问题。问题集中在「规格写了、契约只写在描述里或生成器看不到」的约束。

| ID | 级别 | 问题 | 处理 |
| --- | --- | --- | --- |
| R01 | P2 | `Task` 用 `if/then/else` 表达 `failed ⇔ error`，`datamodel-codegen` 与 `openapi-typescript` 都忽略；生成的 Pydantic `Task` 接受 `{stage: failed, error: null}` | 已修：`Task` 改为按 `stage` 判别的四个分支 |
| R02 | P2 | `TaskStageEvent` 未固定 §1 的进度：`queued = 0`、`awaiting_review = 0.95`（`done` 已固定为 1） | 已修：共享 `FixedStageProgress` |
| R03 | P2 | `Task` 快照未约束 I5（`cancelled ⇒ cancel_requested = true`）与 `completed ⇒ progress = 1`，只约束在事件上 | 已修：由对应分支的 `const` 表达 |
| R04 | P2 | 409 `TASK_NOT_CANCELLABLE` 的 `details.{stage, reason}` 只写在描述里，H02 依赖 `details.stage` | 已修：新增 `TaskNotCancellableError` |
| R05 | P3 | `ticket` 查询参数与 `EventTicket.ticket` 各写一份格式约束，参数缺 `pattern` | 未改，留给 C16 |
| R06 | P3 | 四个任务操作的 403/404 描述逐字重复 8 处 | 未改 |
| R07 | P3 | `done` / `error` 事件的 `cancel_requested` 可选，`Task` 中必填 | 未改 |
| R08 | P3 | 生成物有未被引用的 `Stage`（及本次新增的 `Stage1`）枚举，来自内联 `enum` | 未改 |

## 修正内容

- `src/contracts/api.v1.yaml`
  - `Task` → `oneOf` + `discriminator: stage`：`TaskActive`（`queued`～`awaiting_review`，`error` 为 null）、`TaskCompleted`（`progress` 固定 1）、`TaskFailed`（`error` 必填）、`TaskCancelled`（`cancel_requested` 固定 true）；公共字段移到 `TaskBase`。与 `TaskEvent` 同构。
  - `FixedStageProgress`：`queued → 0`、`awaiting_review → 0.95`，由 `TaskStageEvent` 与 `TaskActive` 共同引用。它只约束取值，生成器会忽略（TS 生成为 `unknown`，不影响交叉类型），运行时由 C08 保证。
  - `TaskNotCancellableError`：`code` 固定 `TASK_NOT_CANCELLABLE`；`details` 是三种 `{stage, reason}` 组合的闭集。`cancelTask` 的 409 改为引用它。
- `src/contracts/errors.v1.md`：`TASK_NOT_CANCELLABLE` 的触发条件原写「对已处于终态的任务调用取消」，按 §4 补上 `persisting`、`awaiting_review`，并指向新 schema。
- `specs/task-processing.md`：契约缺口表 TASK-17 行注明「按状态拆分」。
- 重新生成 `src/contracts/v1/generated/`。
- `tests/contracts/test_b10.py`：36 → 45 项。新增按阶段的自洽快照 `TASK_BY_STAGE`、快照不变量负例、`Task` 结构断言、409 闭集正负例，以及直接导入生成的 Pydantic 模型的测试（生成器丢约束时会失败）。

## 已运行命令与结果（macOS，Python 3.13.5，pydantic 2.11.7）

| 命令 | 结果 |
| --- | --- |
| 改真源前 `python3 -m pytest tests/contracts/test_b10.py -q` | 10 failed / 35 passed（新增测试全部为红） |
| 改真源后、重新生成前 | 1 failed（Pydantic 生成物仍为旧模型） |
| `./scripts/gen-contracts.sh` 后 | 45 passed |
| 反向篡改 7 处（去 `TaskFailed.required`、`TaskCancelled` 的 const、`TaskCompleted` 的 const、两处 `FixedStageProgress` 引用、放宽 409 终态分支、409 改回 `Error`） | 每处 1～2 failed，恢复后 `cmp` 一致 |
| 生成的 Pydantic `Task` | `progress` 为 `1` 与 `1.0` 都解析为 `TaskCompleted`；R01 的负例均被拒 |
| `tsc --noEmit --strict` 检查生成的 `openapi.d.ts` 与一段收窄用例 | exit 0：`stage === "failed"` 后 `error` 为非空 `Error`；非 failed 分支带 `error` 被 `@ts-expect-error` 捕获 |
| `./scripts/gen-contracts.sh --check` | 生成物与真源一致 |
| `./scripts/verify.sh` | exit 0（B08 5、B09 5、B10 45） |
| `git diff --check` | exit 0 |

## 接口影响

- `Task` 的 wire 形状不变，只是约束更严：此前合法、现在非法的只有违反规格的快照。
- 生成类型：`components["schemas"]["Task"]` 从单一对象变为四分支联合，新增 `TaskBase`、`TaskActive`、`TaskCompleted`、`TaskFailed`、`TaskCancelled`、`FixedStageProgress`、`TaskNotCancellableError`。目前没有消费者（C10/C11/C12/H02 未实现）。

## 下一步

- PR #32（B13）叠在本分支上，合并本 PR 前后需同步一次。
- R05～R08 可在 C16（票据运行时）或下一次契约整理时处理。

## 回滚

撤销本次提交即可：契约真源、`errors.v1.md`、规格注记、生成物与 `test_b10.py`。无数据库或外部状态。
