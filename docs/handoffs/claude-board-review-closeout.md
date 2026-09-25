# Claude 交接：任务板审查状态收尾（2026-09-25）

- 分支 / base：`claude/board-review-closeout` / `origin/main@36670a3`
- 角色：协调方，按 ArvinHan「检查未提交或未合并的 PR，关闭可以关闭的任务」执行

## 核对范围

1. 打开的 PR 与本地工作目录。
2. 逐个对照任务板状态和 issue 状态。
3. 任务板上写着「待审查」的行，逐一对照入库的 Codex 审查报告，并在 main 上复现报告里的问题。

## 改动（只改 `docs/tasks.md`）

| 行 | 原状态 | 新状态 | 依据 |
| --- | --- | --- | --- |
| C06 | READY FOR REVIEW（PR #209） | DONE（PR #209 `8309c03`） | PR 已合并，#63 已关闭 |
| B02 | DONE（待 Codex 审查） | DONE（REVIEW-18 已审，无问题） | 报告无 P1/P2/P3。当时唯一的缺口是审查机器缺依赖、`verify.sh` 没跑成，B07 之后 CI 已完整运行 |
| B03 | DONE（待 Codex 审查） | DONE（REVIEW-19 已审；B03-R01′ 未修） | 见下 |
| B04 | DONE（待 Codex 审查） | DONE（REVIEW-19 已审；B04-R01 未修） | 见下 |
| B10 | DONE（待审查） | DONE（REVIEW-20 已修；B10F-R01/R02 未修） | 见下 |

新增「审查遗留」一节，登记 4 项仍然存在的问题。B03-R01′ 加撇号，是为了和 B03 节里协调方自提的同名 P3 区分。

## 复现记录（`origin/main@36670a3`）

- **B03-R01′**：`src/frontend/src/main.ts:8` 为 `getAccountRole: () => null`。
- **B04-R01**：`src/frontend/src/stores/course.ts` 的 `selectCourse` 首行 `if (id === courseId.value) return`，没有会话重置入口。
- **B10F-R01**：生成的 `models.py` 中 `TaskCancelled.cancel_requested: Literal[True] = True`；`model_fields['cancel_requested'].is_required()` 为 `False`。
- **B10F-R02**：用 `openapi.json` 与 `jsonschema` 的 Draft 2020-12 校验 `{code: TASK_NOT_CANCELLABLE, details: {stage: completed, reason: already_terminal, secret: x}}`，结果为通过。

## 未处理（需人工决定）

- 打开的 PR #214（B14）、#215（D08）、#216（C03）、#217（E07）都是 Codex 在 2026-09-25 06:09～07:03（EDT）开的，CI 全绿、可以合并，但还没有审查。
- Codex 本地未提交的工作：
  - `codex-f02-neo4j`：F02，#94 已分配；
  - `codex-k07-dev-scripts`：K07，#146 已分配；
  - `codex-0925-task-claims`：1 个未推送的提交，内容是登记 B14、D08 认领，这两项已有 PR。
  - 三处最后一次改动都在 06:4x。
- `~/.codex/worktrees/b07-contract-gate`：ArvinHan 决定暂不删除。

## 验证

`./scripts/verify.sh` exit 0；`git diff --check` 通过（见 PR）。

## 回滚

还原本 PR 即可，只改了任务板。
