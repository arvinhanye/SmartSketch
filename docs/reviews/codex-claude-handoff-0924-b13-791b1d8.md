# HANDOFF-0924 固定提交审查：B13 PR #32

- 审查者：Codex；日期：2026-09-24；目标：`bb48429..791b1d8`（PR #32 的当前固定头提交）。该 PR 仍开放，本报告只对这一版有效。
- 依据：`specs/grounded-qa.md` Q2/Q5/Q6/Q7、ADR-015、`docs/handoffs/claude-b13.md`、`docs/handoffs/claude-handoff-codex-2026-09-24.md` §4。未改 PR 分支与契约真源；建议先处理 P2 再合并。

## 发现

| ID | 级别 | 文件与触发条件 | 影响及最小修复/回归 |
| --- | --- | --- | --- |
| B13-0924-R01 | P2 | `src/contracts/api.v1.yaml:2354-2382`：`ChatError` 继承全局 `ErrorCode`，无问答错误码闭集。`ChatEvent.error.code=CYCLE_DETECTED` 加 `request_id` 通过 JSON Schema。 | Q5 仅有 `LLM_UNAVAILABLE`、`BUDGET_EXCEEDED`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR` 四类流内错误；按 `code` 拆分问答专用分支，新增其他全局码被拒的负例。 |
| B13-0924-R02 | P2 | 同上：`LLM_UNAVAILABLE` 的必填 `details.reason` 只由 `if/then` 表达；生成的 Pydantic `ChatError` 把 `reason` 生成为可选，实测缺少 reason 仍被接受。 | 后续 J07 若只用生成模型校验会输出不符合 Q5 的错误；改成代码生成器可见的判别分支，测试直接导入生成模型的缺字段负例。 |
| B13-0924-R03 | P2 | 同上：`INTERNAL_ERROR` 加 `details.reason=timeout` 通过 JSON Schema 与 Pydantic。 | 前端可能把内部故障错当链路超时；非 `LLM_UNAVAILABLE` 分支排除 reason，并加负例。 |
| B13-0924-R04 | P2 | `src/contracts/api.v1.yaml:2291-2316`：只限制 `not_covered ⇒ retrieved=0`，`meta.status=answered,retrieved=0` 实测通过。 | Q2 的 `retrieved=|A|` 和 P5 语义下，零允许引用集合不能进入生成；`answered` 分支设 `minimum: 1`，JSON Schema 与生成模型分别验证。 |
| B13-0924-R05 | P2 | `src/contracts/api.v1.yaml:946-950,1052-1057`：JSON 模式 503 的 `details.reason` 闭集只在描述里，响应仍引用通用 `Error`；任意 reason 实测通过。 | Q7 的 O7～O10 无法结构校验；给 503 的 `LLM_UNAVAILABLE` 分支使用专用 schema，保留 `STORAGE_UNAVAILABLE` 分支并加负例。 |
| B13-0924-R06 | P2 | `src/contracts/events.v1.md:239-243`：B13 原地改写 §3 时未在 §6 追加例外记录；交接称已登记，但文件只记 B10，且写「此后再改须升 v2」。 | 版本政策与本次交付冲突；在合并前记录 B13 的无消费者前提和一次性例外，或依 §6 升 v2，不隐含豁免。 |
| B13-0924-R07 | P3 | `src/contracts/v1/generated/python/models.py:731-733,823-824`：内联 details 生成 `Details3`，依前面 schema 的出现顺序命名。 | 后续契约新增内联 details 可改变类名；把问答与取消错误 details 提为具名 schema，重生成并检查稳定名称。 |
| B13-0924-R08 | P3 | `src/contracts/api.v1.yaml` 的 `graph_version`/`request_id` 在 `ChatAnswered`、`ChatNotCovered`、`ChatMetaEvent` 重复。 | 未来约束演进易漂移；后续契约整理时抽共享字段。此项不单独阻塞当前 PR。 |
| B13-0924-R09 | P2 | `src/contracts/api.v1.yaml:2340-2345`：`ChatDoneEvent` 描述仍称 final 与 delta 拼接「可能不同」，而 Q6/I1 与更新后的 `events.v1.md` 指定 `answered` 时必须逐字相等。 | J08 可能把有差异的 answered 视为正常并掩盖异常；描述按 `answered`/`not_covered` 分开，增加规格一致性断言。 |

R01～R06 与交接稿 §4 所列问题相符；R07/R08 为其 P3；R09 为本轮额外发现。上述 P2 均为固定提交的文档或契约层问题，尚未声称有运行时服务已产生错误。

## 复现与验证

- 在 `/private/tmp/smartsketch-b13-review` 解出 `791b1d8` 的只读副本；`test_b13.py` 43 passed、完整 `./scripts/verify.sh` exit 0（24 项门禁负例、B08 5、B09 5、B10 45、B13 43）、`gen-contracts.sh --check` exit 0、`git diff bb48429..791b1d8 --check` exit 0。
- `jsonschema.Draft202012Validator` 针对 `ChatEvent`/`Error` 的四个负例：外部错误码、非 LLM 的 reason、answered 的零 retrieved、JSON 503 的任意 reason 均返回 `is_valid=True`。直接导入生成 Pydantic `ChatError`：`LLM_UNAVAILABLE` 缺 reason、`INTERNAL_ERROR` 带 timeout reason 均通过。
- 测试绿只说明现有测试覆盖的行为通过，不覆盖上述反例。建议在 PR #32 原分支按测试先行修复 R01～R06、R09，并在重新生成后重跑全套门禁；本轮不代改 Claude 文件。
