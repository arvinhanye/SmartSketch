# Claude 交接：2026-09-24 集成结果、任务现状与交给 Codex 的工作

- `task_id`: HANDOFF-0924（协调交接，不对应单个原子任务）
- `review_status`: ready_for_review（第 3 节列出的固定范围）
- `base`: main @ `bb48429`（Merge PR #31）
- `作者`: Claude（ArvinHan 会话，负责人 ArvinHan）
- `读法`: 先看第 1 节了解今天 main 的变化，再按第 3 节审查、第 5 节认领。所有状态以 main 的 `docs/tasks.md` 为准，本文只是 2026-09-24 的快照。

## 1. 今天合入 main 的内容

合并由 ArvinHan 在会话中明确授权后执行（ADR-016：Agent 开 PR，由 ArvinHan 决定合并）。每次合并都用 `--match-head-commit` 锁定 PR 头提交；合并前在最新 main 上试合并并跑验证。

| 顺序 | PR | 任务 | 合并提交 | 审查范围（first-parent） | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | #27 | B02 前端 Vitest 测试配置 | `3fedd4e` | `9d2437e..3fedd4e` | 任务板 DONE（待 Codex 审查） |
| 2 | #28 | B03 路由壳与角色入口、B04 Pinia 课程上下文；补登 H13（D-09） | `06f33aa` | `3fedd4e..06f33aa` | 同上 |
| 3 | #29 | CI-02 前端与后端 job 接入 CI | `025cbee` | `06f33aa..025cbee` | 任务板 DONE（待审查） |
| 4 | #26 | A10 批 1 补：问答规格加回契约命名门禁 | `f00a3e8` | `025cbee..f00a3e8` | DONE |
| 5 | #31 | B10 任务与 SSE 契约，含 REVIEW-B10 修正 | `bb48429` | `f00a3e8..bb48429` | 任务板 DONE（待审查），Claude 已审查 |

- #27、#28、#29、#26 合并前各自同步过一次 main 或 B02 分支，冲突都只在 `docs/tasks.md`（两边在同一位置追加新节），按任务编号保留两边，内容不改。同步记录写在各自交接末尾：`claude-b02.md`、`claude-b03.md`、`claude-b04.md`、`claude-ci-02.md`、`claude-a10-batch1-supplement.md`。
- main @ `f00a3e8` 与 `bb48429` 的 GitHub CI 三个 job（Repository scaffold、Frontend、Backend）均通过。

### B10 的审查修正（已在 #31 内）

Claude 审查 B10 发现 P2×4、P3×4（`docs/handoffs/claude-review-b10.md`）。P2 已在提交 `21de627` 修正，先写测试、再改契约并重新生成：

- R01：`Task` 从 `if/then/else` 改为按 `stage` 判别的四个分支（`TaskActive`、`TaskCompleted`、`TaskFailed`、`TaskCancelled`，公共字段在 `TaskBase`），生成的 Pydantic / TS 类型直接带上 `failed ⇔ error`。
- R02：`FixedStageProgress`（`queued = 0`、`awaiting_review = 0.95`），`TaskStageEvent` 与 `TaskActive` 共用。
- R03：快照补 I5（`cancelled ⇒ cancel_requested = true`）与 `completed ⇒ progress = 1`。
- R04：新增 `TaskNotCancellableError`，409 的 `details.{stage, reason}` 为闭集。
- B10 测试 36 → 45，含直接导入生成的 Pydantic 模型的测试；7 处反向篡改均被检出。P3 四项（R05～R08）未改。

## 2. 任务现状（main @ `bb48429`）

| 类别 | 任务 |
| --- | --- |
| 已完成 | A01～A10；B01～B06、B08～B10；CI-01、CI-02；HOOK-01；A10 批 0 / 批 1 / 批 1 补 |
| 有 PR 待合并 | B13（PR #32，见第 4 节） |
| 阻塞 | B11：等 ADR-012 下一次修订签收（快照节点加 `merged_from` 并纳入摘要；版本提交取共享序列的提交序号，见 `docs/tasks.md` A08 行后续项）；另需并入 A02-R01（`Relation.required` 补 `status`、`source`、`source_refs`） |
| 依赖已满足、可开工 | 见第 5 节 |
| 其余 | 依赖未满足，状态为 pending |

原子清单共 141 项（主线 + H13 补登 + 8 项加分项 O01～O08）。

### GitHub issues 同步

- 新建标签 `status:in-review`（已有 PR）与 `status:blocked`。
- 已关闭：A01～A10、B01～B06、B08～B10，共 19 个；关闭时附合并提交与证据。
- #55 B13 为 `status:in-review`；#53 B11 为 `status:blocked`，附阻塞原因。
- 新建 #173 H13（前端登录页与会话存储，依赖 C13、B15、B03、B04）。
- #53 B11、#58 C01 已分配给协作者 539210，本次未改动负责人。

## 3. 请 Codex 审查的范围

按 `docs/claude-review-workflow.md` 的程序执行，报告写 `docs/reviews/codex-claude-<回合标识>.md`。建议顺序：

1. **B10（`f00a3e8..bb48429`）**：契约与 `specs/task-processing.md`（ADR-010）、`specs/identity-access.md` §5、§7（ADR-013）。重点看 REVIEW-B10 的修正：`Task` 分支后的生成物是否仍满足 C08/C10/C11 的使用方式；`FixedStageProgress` 只约束取值、生成器会忽略，是否可接受。
2. **B02（`9d2437e..3fedd4e`）**：`claude-b02.md`「未验证」一节——Windows 上的嵌套 `npm test` 运行只在 macOS 验证过，请实跑一次。
3. **B03/B04（`3fedd4e..06f33aa`）**：路由守卫只做界面引导、授权以后端为准（A05 §2.4）；B03-R01（P3）`App.vue` 用 `inject(routeLocationKey, null)` 兼容未装路由的挂载。
4. **CI-02（`06f33aa..025cbee`）**：前端与后端 job 是否失败即退出、没有静默跳过。
5. **B13（PR #32，`bb48429..791b1d8`）**：见第 4 节；建议等 ArvinHan 决定修正范围后再审，避免审到要改的版本。

## 4. PR #32（B13）的状态

- 已同步 main `bb48429`（提交 `791b1d8`），目标分支已改为 `main`，可合并。
- **同步时发现**：生成物不能用文本合并。自动合并会留下两个同名 `class Details`（B10 的取消 409 与 B13 的 `ChatError`），后者覆盖前者；已按真源重新生成。合并后 `verify.sh` 通过，B13 测试 43 passed。
- **Claude 审查发现 8 项，尚未修正，等待 ArvinHan 决定**（本次会话已列出，未写成报告）：
  1. `ChatError` 的错误码不是闭集：实测 `CYCLE_DETECTED` 能进问答流；Q5 只允许 `LLM_UNAVAILABLE`、`BUDGET_EXCEEDED`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`。
  2. 「`LLM_UNAVAILABLE` 必带 `details.reason`」用 `if/then`，生成物中 `reason` 为可选（与 B10-R01 同类）。建议按 `code` 拆 `oneOf`，与第 1、3 项一并解决。
  3. 非 `LLM_UNAVAILABLE` 也能带 `reason`：实测 `INTERNAL_ERROR` + `timeout` 通过。
  4. `meta.status = answered` 时允许 `retrieved = 0`；按 Q2/P5 应 ≥ 1。
  5. JSON 模式 503 的 `details.reason` 闭集只写在描述里（Q7）。
  6. `events.v1.md` §6 没有登记 B13 对 §3 的原地改写（B10 的例外记录写明「此后再改须升 v2」）；`claude-b13.md` 称已登记，实际没有。
  7. 内联 `details` 对象按出现顺序生成 `Details`～`Details3`，类名随其他契约变化而改变；建议给 `ChatError` 与 `TaskNotCancellableError` 的 `details` 起具名 schema。
  8. `graph_version` / `request_id` 定义在三个 schema 中逐字重复。
- Claude 的建议是修第 1～7 项后再合并。

## 5. 可开工的任务（依赖均已在 main 完成）

| 任务 | 后续直接依赖数 | 说明 |
| --- | --- | --- |
| **C01** SQLite 连接和迁移运行器 | 9 | 持久层起点；issue #58 已分配给 539210，开工前先确认对方进度。须接管 B06 的引导表 `embedding_space_state`（ADR-012 补注） |
| **C08** 状态迁移纯函数 | 3 | B10 合入后刚解锁；输入是 `specs/task-processing.md` §2 迁移事件表与 TASK-16 负例 |
| **D01** 解析输出与自编 fixture | 4 | 文档解析线起点 |
| **B12** 进度和推荐契约 | 3 | 与 B10/B13 同类契约迁移；A08 交出 `ProgressEntry` 新字段、GET/PUT 返回全部节点 |
| **E01** 版本化提示词装载器 | 3 | 抽取线起点，fake 模型可先行 |
| **F01** 复用本地 Neo4j 环境并验证 | 2 | 图存储线起点 |
| **B07** 修复校验缺依赖假绿 | 1 | 小任务，提高门禁可信度 |
| **C05** 文件落盘边界 | 1 | 依赖 B06 |

B14（契约导出与漂移检查）要等 B11、B12、B13；B15（前端 HTTP 客户端）要等 B14。

## 6. 待决策（不阻塞上面的可开工任务）

| ID | 事项 | 何时需要 |
| --- | --- | --- |
| ADR-012 下一次修订 | `merged_from` 与提交序号，解除 B11 | 越早越好，B11 → B14 → B15 串行 |
| D-01 | MVP 示例课程与脱敏资料来源 | M1 开始前 |
| D-02a～f | 模型供应商取值与预算 | 接入真实模型前（fake 可先行） |
| D-08 | 融合自动合并阈值与低置信度阈值 | E09/E10 开工前 |
| PLAN-D05 | 学习材料分支是否同步 main；目标路径是否纳入 | 主线验收后 |

## 7. 发现的小问题（未处理）

- `.gitignore` 没有忽略 `*.egg-info/`：`pip install -e './src/backend[test]'`（CI-02 与本地验证都会执行）会在 `src/backend/` 留下 `smartsketch_backend.egg-info/`。`git check-ignore` 实测未忽略；`a09-dev-environment-check-8e5e93` worktree 里已有一份未跟踪的残留。
- 生成物不要文本合并：凡是涉及 `src/contracts/v1/generated/` 的合并，先解决真源冲突，再执行 `./scripts/gen-contracts.sh` 并用 `--check` 确认。
- 叠加 PR（stacked PR）合并后要改目标分支，改完 diff 才只剩自身改动；任务板各节在同一位置追加，合并时几乎必然冲突，按任务编号排列即可。

## 8. 本交接的验证

| 命令 | 结果 |
| --- | --- |
| `git log --first-parent 9d2437e..bb48429` | 5 个合并提交，与第 1 节一致 |
| 依赖计算（读 `docs/atomic-tasks.json`，已完成集合按第 2 节） | 可开工 8 项，与第 5 节一致 |
| `gh issue list` / `gh pr list` | 已关闭 19；in-review 1（#55）；blocked 1（#53）；开放 PR 仅 #32 |
| `gh run`（main @ `bb48429`） | Repository scaffold、Frontend、Backend 均 success |
| `./scripts/verify.sh`（本分支，base `bb48429`） | exit 0 |
| `git diff --check` | exit 0 |

## 9. 下一位 Agent 的首个动作

- **Codex**：按第 3 节顺序审查 B10，报告写 `docs/reviews/`；需要修改时另开任务，不直接改 Claude 的分支。
- **认领新任务时**：在 `docs/tasks.md` 新增原子任务行，写明分支、base 与文件锁，并把对应 issue 改为 `status:in-review`（有 PR 时）。

## 回滚

本交接只新增本文件，并把任务板 CI-02 行的状态改为已合入；撤销该提交即可。
