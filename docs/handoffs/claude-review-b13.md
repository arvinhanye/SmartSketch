# 交接：审查 B13（PR #32）并修正 R01～R07

- `task_id`: REVIEW-B13
- `status`: 审查完成；按 ArvinHan 的决定修 R01～R07，R08 未改
- `审查目标`: `origin/claude/b13-chat-contract` @ `791b1d8`（已同步 main `bb48429`），修正前又同步 main `62cbbc7`（只有 PR #175 的文档）
- `依据`: `specs/grounded-qa.md` Q2、Q4、Q5、Q7、Q11（ADR-015 及修订 1）；`events.v1.md` §6

## 审查结论

B13 与 Q11 分配的改动逐项对上：`insufficient_evidence` 改名、`meta` / `final` 的版本绑定字段、`ChatError` 的 `request_id`、`events.v1.md` §3 指向规格。问题集中在「规格有闭集，契约没收紧，或写法让生成器看不到」。

| ID | 级别 | 问题 | 处理 |
| --- | --- | --- | --- |
| R01 | P2 | `ChatError.code` 仍是完整 `ErrorCode`；实测 `CYCLE_DETECTED` 能进问答流，Q5 只允许四个码 | 已修 |
| R02 | P2 | 「`LLM_UNAVAILABLE` 必带 `reason`」用 `if/then`，生成物里 `reason` 为可选（同 B10-R01） | 已修 |
| R03 | P2 | 非 `LLM_UNAVAILABLE` 也能带 `reason`；实测 `INTERNAL_ERROR` + `timeout` 通过 | 已修 |
| R04 | P2 | `meta.status = answered` 允许 `retrieved = 0`；按 Q2/P5，进入生成时 A 非空 | 已修 |
| R05 | P2 | 问答 503 的 `details.reason` 闭集只写在描述里（Q7） | 已修 |
| R06 | P2 | `events.v1.md` §6 未登记 B13 对 §3 的原地改写；`claude-b13.md` 称已登记 | 已修 |
| R07 | P3 | 内联 `details` 生成按出现顺序编号的 `Details`～`Details3`，类名随其他契约变化；同步 B10 时文本合并还留下两个同名类 | 已修 |
| R08 | P3 | `graph_version` / `request_id` 在三个 schema 中逐字重复 | 未改 |

## 修正内容

- `src/contracts/api.v1.yaml`
  - `ChatError` → `oneOf` + `discriminator: code`：`ChatLlmUnavailableError`（`details` 为 `ChatLlmUnavailableDetails`，`request_id`、`reason` 必填）与 `ChatServiceError`（`BUDGET_EXCEEDED` / `STORAGE_UNAVAILABLE` / `INTERNAL_ERROR`，`details` 为 `ChatErrorDetails`，只有 `request_id`）。两个 `details` 都是闭合对象（`additionalProperties: false`），因此其余三码不能带 `reason`，生成的 Pydantic 模型为 `extra='forbid'`。
  - `ChatLlmUnavailableReason`：`upstream`、`stream_interrupted`、`timeout`、`auth`，流内错误与 503 共用。
  - `ChatMetaEvent`：`allOf` 两条取值约束，`not_covered ⇒ retrieved = 0`（原有）、`answered ⇒ retrieved ≥ 1`（新增）。
  - `ChatUnavailableError` / `ChatUnavailableDetails`：问答 503 的码只取 `LLM_UNAVAILABLE`、`STORAGE_UNAVAILABLE`；`details` 闭合，`reason` 取闭集且只属于 `LLM_UNAVAILABLE`。`request_id` 与 `reason` 都可缺省：P2 之前没有请求 ID，Q2 的 P4 向量失败没有规定 `reason`，契约不替规格做这个决定。
  - B10 的 `TaskNotCancellableError.details` 三支改为具名 `TaskPersistingDetails`、`TaskProcessingFinishedDetails`、`TaskAlreadyTerminalDetails`，结构不变。
- `src/contracts/events.v1.md`：§3 事件表的 `error` 行写明码闭集与「其余三码不带 `reason`」；§6 补 B13 例外记录。
- `docs/handoffs/claude-b13.md`：更正「已在 §6 登记」的说法，并注明 `ChatError` 的决定已被取代。
- 重新生成 `src/contracts/v1/generated/`。生成物中不再有 `Details*` 类；内联枚举仍会生成未被引用的 `Stage*`、`Code*`，与 B10-R08 同类，未处理。
- `tests/contracts/test_b13.py`：43 → 52。

## 已运行命令与结果（macOS，Python 3.13.5，pydantic 2.11.7）

| 命令 | 结果 |
| --- | --- |
| 改真源前 `python3 -m pytest tests/contracts/test_b13.py -q` | 9 failed / 43 passed（新增测试全部为红） |
| 改真源后、重新生成前 | 3 failed（2 项需重新生成，1 项为 §6 登记） |
| 补 §6、`./scripts/gen-contracts.sh` 后 | 发现自己新增的 503 `details` 仍生成 `Details`，改为具名 `ChatUnavailableDetails` 后 52 passed |
| `python3 -m pytest tests/contracts/ -q` | 131 passed（B08、B09、B10 45、B13 52、门禁负例） |
| 反向篡改 6 处（码闭集放宽、LLM `reason` 改为可选、`ChatErrorDetails` 放开附加字段、去掉 `retrieved ≥ 1`、503 去掉「存储不带 reason」、503 改回 `Error`） | 每处 1～2 failed，恢复后 `cmp` 一致 |
| `tsc --noEmit --strict` 检查生成的 `openapi.d.ts` 与一段收窄用例 | exit 0：`code === "LLM_UNAVAILABLE"` 后 `details.reason` 为必填；闭集外的码与缺 `reason` 都被 `@ts-expect-error` 捕获 |
| `./scripts/gen-contracts.sh --check` | 生成物与真源一致 |
| `./scripts/verify.sh` | exit 0：85 个 schema / 274 处 `$ref`；命名基线 10 份、负例 24 项；B08、B09、B10、B13 回归通过 |
| `git diff --check` | exit 0 |

## 接口影响

- wire 形状不变，约束更严：此前合法、现在非法的只有违反 Q2/Q5/Q7 的载荷。
- 生成类型新增 `ChatLlmUnavailableError`、`ChatServiceError`、`ChatErrorDetails`、`ChatLlmUnavailableDetails`、`ChatLlmUnavailableReason`、`ChatUnavailableError`、`ChatUnavailableDetails`、`TaskPersistingDetails`、`TaskProcessingFinishedDetails`、`TaskAlreadyTerminalDetails`；`ChatError` 从单一对象变为两支联合。当前没有消费者（J05～J09、C10/H02 未实现）。

## 下一步

- ArvinHan 决定是否合并 PR #32；合并后 B11 仍阻塞，B12 可开工，B14 需等 B11、B12。
- R08 可在 B14（契约导出与漂移检查）时一并整理。

## 回滚

撤销本次提交即可：契约真源、`events.v1.md`、生成物、`test_b13.py` 与文档注记。无数据库或外部状态。
