# A09 开工前环境检查

- **task_id**：A09 开工前检查（A09 本身尚未认领，`docs/tasks.md` 未改）
- **状态**：DONE。结论：可以开工，无环境阻塞；开工时须处理下文「开工须知」四项
- **worktree**：`.claude/worktrees/a09-dev-environment-check-8e5e93`
- **分支 / base**：`claude/a09-dev-environment-check-8e5e93` / `1a47eb2`（= `origin/main`，2026-09-23 fetch 后核对）
- **类型**：只读检查。仓库内只新增本交接文件；未改其他文件，未安装依赖，未碰 main checkout 与其他 worktree

## 一、A09 定义（`docs/atomic-tasks.json`）

定义问答终态和引用撤回协议。依赖 A02、A04；输入 R03/R04 与 S2；写入 `specs/grounded-qa.md`；验收：answered 必有定位来源、临时正文失败后清除、空检索不调用生成、与未知引用区分；验证：`git diff --check` + 逐条核对验收矩阵，人工决策保留未签收标记。

## 二、检查结果

| 项 | 结果 |
| --- | --- |
| 依赖 A02 / A04 | 已在 `origin/main`：ADR-009；ADR-012 + 修订 1 |
| 输入 R03 / R04 | `docs/reviews/codex-claude-initial-2026-09-22.md` 第 23、33 行 |
| 输入 S2 | `/Users/arvinhan/Desktop/A10--数字马力杯--项目规划/智绘学途_S2解决方案.docx` 存在；`pandoc -t plain` 转出 1077 行，§6.4.6 智能问答、§7.1.6、§8.4 可读 |
| 契约真源（ADR-004） | `740adb` `978671e`（本地分支与 origin 一致）：`specs/grounded-qa.md` 桩 78 行；`api.v1.yaml` 含 `ChatAnswered`/`ChatNotCovered` 判别联合、`ChatEvent` 四事件、`NotCoveredReason` 四值；`events.v1.md` §3 已写 `done.final` 为唯一权威正文、delta 为临时态 |
| 目标文件占用 | main 无 `specs/grounded-qa.md`；所有 worktree、本地/远端分支、3 个 open PR 均无 A09 认领或对该文件的未合并改动 |
| 工具 | Python 3.13.5、PyYAML 6.0.2、jsonschema 4.26.0、pandoc、git、gh 可用；docker 未安装（A09 不需要） |
| 校验链冒烟 | jsonschema 对 `978671e` YAML：answered + 空引用、无页码/章节的引用、`{}` 事件、空 delta 均被拒；带页码引用通过 |
| `./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

## 三、开工须知

1. **在本 worktree 开发，不在 main checkout**。`atomic-tasks.json` 的 `allowed_files`、`verification_cwd` 写的是 `/Users/arvinhan/Desktop/SmartSketch`，但该 checkout 的 `main` 落后 `origin/main` 28 个提交，且有 Codex 未提交的 `docs/tasks.md`（REVIEW-03～09 行）、`claude-review-state.json` 与 7 份审查报告。按仓库相对路径 `specs/grounded-qa.md` 理解。
2. **文件范围需扩展**：清单只列 `specs/grounded-qa.md`；完成标准另需 `docs/tasks.md` 认领行与 `docs/handoffs/claude-a09.md`。若终态/撤回规则要签收成 ADR，还要写 `docs/decisions.md`；`docs/architecture.md` 的 SSE 事件表与「文档用语 → wire 值」表可能需同步。均需用户同意。
3. **ADR 编号用 ADR-015**：main 已到 ADR-013；Codex A08 引用的 ADR-014 在 `claude/codex-a08-check-ade85c@8901371`，尚未入 main。
4. **并发写入者**（都是追加，冲突可手工合并）：
   - PR #16（`claude/fix-r01-r02`，MERGEABLE）改 `docs/decisions.md`、`docs/tasks.md`、`docs/architecture.md`、`specs/teacher-review-publish.md` 等（ADR-011 修订 3、ADR-012 修订 2）。建议先合入再开 A09 分支，否则 `tasks.md`/`decisions.md` 会有文本冲突。
   - Codex A08（`codex-a08-learning-path`，未提交）改 `docs/tasks.md`、`docs/atomic-task-plan.md` B12 行。A09 不改 B13 行即可避开。

## 四、A09 内容上需保留「未签收」的事项（不阻塞开工）

检索相关度阈值（依赖 D-01 样例资料与标注集）、引用编号格式、`NOT_COVERED` 原因是否对学生区分、性能 3 s / 10 s / 15 s 的关系、预算耗尽的问答失败路径（`BUDGET_EXCEEDED` 取决于 D-02f）。另须对齐的已签收约束：ADR-012 修订 1（检索按 `revision_id`、只读已发布版本）、ADR-013（问答仅学生成员、SSE 一次性票据）、ADR-011 修订 2（问答调用以 `request_id` 归属）。

## 五、复现命令

```bash
git fetch origin && git rev-parse HEAD origin/main
./scripts/verify.sh
git diff --check
git show 978671e:specs/grounded-qa.md
gh pr list --state open
```

## 六、下一位的首个动作

确认 PR #16 是否先合入；随后在 `docs/tasks.md` 认领 A09（写 worktree、base HEAD、文件锁），以 `978671e` 的 `specs/grounded-qa.md` 桩为底稿新建 main 版本。
