# Claude 交接：B13 问答与事件契约

- `task_id`: B13
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a09-dev-environment-check-8e5e93`，分支 `claude/b13-chat-contract`
- `base_commit`: 叠在 B10 `3771ae1`（PR #31）之上；B10 合入后以 main 为基线
- 负责人：ArvinHan（Claude 执行）
- 依据：`specs/grounded-qa.md` Q2、Q4、Q5、Q6、Q7、Q9、Q11 的 B13 行（ADR-015 及修订 1 已签收）。只落实规格列出的改动。
- 调度：原计划 B11 在前；B11 等 ADR-012 修订 3 签收，ArvinHan 2026-09-24 选定先做 B13。

## 交付物

- `src/contracts/api.v1.yaml`
  - `NotCoveredReason`：`out_of_course_scope` 改为 `insufficient_evidence`（ADR-015 决定 3）。
  - `ChatAnswered`、`ChatNotCovered` 的必填字段增加 `graph_version`（整数，最小 1）与 `request_id`。
  - `ChatMetaEvent`：`retrieved`、`graph_version`、`request_id` 均为必填；`status = not_covered` 时 `retrieved` 必须为 0。
  - 新增 `ChatError`：在 `Error` 基础上要求 `details.request_id`；`code = LLM_UNAVAILABLE` 时另须 `details.reason ∈ {upstream, stream_interrupted, timeout, auth}`。`ChatErrorEvent.error` 改为引用它。
  - `chat` 操作补上 404（`GRAPH_NOT_PUBLISHED`）与 500（`INTERNAL_ERROR`）；503、500 的描述写明 `details.reason` 与 `details.request_id`；操作描述改为指向 Q2、Q5、Q6、Q7。新增共享响应 `InternalError`。
- `src/contracts/events.v1.md` §3 改为指向规格：
  - 事件表按新的必填字段更新，加入 Q2 事件文法。
  - 「最终正文与撤回」按 Q6 与 I1 重写，含 O14、O15；删掉了与 I1 冲突的旧条文「两者可能不同，正文需相应改写」。
  - 示例补上 `graph_version`、`request_id`，并新增 `insufficient_evidence` 与出字后中断两例。
- 重新生成 `src/contracts/v1/generated/`（`openapi.json`、`schemas/ChatEvent.schema.json`、`python/models.py`、`typescript/openapi.d.ts`）。
- `tests/contracts/test_b13.py`（43 个用例），接入 `scripts/verify/contracts.sh`。
- 随附改动：
  - `docs/architecture.md` 的 `NotCoveredReason` 行（Q11 要求同一次提交更新）。
  - `src/contracts/errors.v1.md` 的 `RATE_LIMITED` 改为只指本服务限流。这是 Q11 交给 B08、但 B08 没做的遗留项。
  - `specs/grounded-qa.md` Q11 的 B13 行加上状态标注。
- `tests/contracts/test_contracts.py`：门禁的实例级夹具补上 `graph_version`、`request_id`，正负例都补，确保负例仍只因原本要测的缺陷被拒。用例的期望（接受或拒绝）一条未改。

## 决定与理由

- **`ChatError` 用 `allOf` 加 `if/then`，不改共享的 `Error`**：`details.request_id` 与 `reason` 闭集只适用于问答开流后的错误。其他接口的 `Error.details` 仍是开放对象，不受影响。
- **JSON 模式的 HTTP 错误不强制 `details.request_id`**：P2 之前的失败（401、403、404、422、429 `RATE_LIMITED`）没有请求 ID；503、429 也可能发生在 P2 之前或之后。因此 JSON 模式的这一约束只写在描述里，流内的 `error` 事件（一定在 P2 之后）则用结构强制。
- **`latency_ms` 仍为可选**：规格没有把它列为新必填项，按「不从零重写已有字段」保持原样。

## 实际验证（macOS）

| 命令 | 结果 |
| --- | --- |
| 改真源前 `python3 -m pytest tests/contracts/test_b13.py -q` | 17 failed / 26 passed。部分负例当时就「通过」，是因为夹具用了新的 reason 名；改后已用篡改确认它们是因为正确的原因被拒 |
| 改真源、`events.v1.md` 与文档后 | 43 passed |
| 反向篡改（逐项改坏后运行 B13，再恢复） | 去掉 `ChatError` 的 if/then → 1 failed；去掉 meta 的 if/then → 1；`ChatNotCovered` 去掉必填 `graph_version` → 1；`ChatAnswered` 去掉必填 `request_id` → 2；恢复旧 reason → 3；错误事件改回普通 `Error` → 4 |
| `./scripts/gen-contracts.sh --check` | 一致 |
| `./scripts/verify.sh` | exit 0：22 项门禁负例（实例级夹具已补齐），B08、B09、B10、B13 回归 |
| 生成物 | `tsc --noEmit --strict openapi.d.ts` exit 0；`models.py` 可解析 |
| `git diff --check` | exit 0 |

## 风险

- 问答事件与响应收紧属于结构上的破坏性变更。目前没有消费者（J07、J08、J09 均未实现）；依据与 B10 相同，已在 `events.v1.md` §6 登记。
- 代码生成器会忽略 `if/then`；J06/J07 实现时须在服务端保证同样的约束。

## 下一步

- 请 Codex 审查。B11 等 ADR-012 修订 3 签收后再做，之后是 B12、B14。

## 回滚

撤销本分支提交即可，无数据库或外部状态。
