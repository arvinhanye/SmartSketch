# OPT-06：依赖核查与拆分准备

- task_id：OPT-06；负责人：Codex；核查日期：2026-11-10（America/New_York）。
- 状态：**IN_PROGRESS**。用户已确认在隔离分支本地整合依赖后继续，暂不推送或合并远端 PR。当前整合基线 `ec92026`，全量基线门禁运行中。
- 用户范围：先确认 OPT-03/05 依赖，再按原交接分文件拆分并验证。
- 当前工作区：`/Users/arvinhan/.codex/worktrees/opt-06-responsibility-split/SmartSketch-main`，`codex/opt-06-base@ec92026`。原目录仅本任务文档已转移，既有改动保持不变。
- 原要求：审查分支 `claude/code-structure-review-handoff-49e73a` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md:86–90`，明确「只在 OPT-03/05 合入后做；每个文件一个 PR；对外导出名不变（旧模块保留再导出）；不改行为」。

## 依赖证据

| 依赖 | 已验证状态 | 当前缺口 |
| --- | --- | --- |
| OPT-03 | 本地 `codex/opt-03-test-fixtures@36c1f92`，工作区干净；交接记录 DONE，`verify.sh full` exit 0，4254 passed / 27 登记 skip，前端 1375 passed | GitHub 按 head 查询未找到 PR，按分支名查询未找到远端分支；当前 HEAD 不含此提交 |
| OPT-05 | 本地/远端 head 均为 `99c1f01`；[PR #339](https://github.com/arvinhanye/SmartSketch/pull/339) 实时元数据为 open、merged=false、merged_at=null，目标 `codex/opt-base-ad63341@ad63341` | 尚未合并；交接仍有原版个人模式 E2E 例外，不能称完整 integration 全绿 |
| 共用底座 | [PR #338](https://github.com/arvinhanye/SmartSketch/pull/338) 实时元数据为 open、merged=false；目标 `main@3f26766`，head `ad63341` | 底座尚未进入 main |

上述测试数字引用已读取的依赖交接记录，本轮未重新运行其 full/integration。PR 的 `mergeable=true` 仅表示可合并，不表示已合并；open PR 的 `merge_commit_sha` 不作为合入证据。

本地祖先检查：`git merge-base --is-ancestor 36c1f92 HEAD` exit 1；`99c1f01 HEAD` exit 0；两者对 `origin/main` 均 exit 1。远端状态以本轮 GitHub 实时查询为补充，不单凭旧 remote-tracking ref 下结论。

OPT-03 依赖的 OPT-02 提交 `eca579c` 包含个人模式高级选项展开修复；它目前未在 OPT-05 当前基线中。两条线整合后的结果需要实际重验，不能拼接旧测试记录作为综合通过。

只读 `git merge-tree ad63341 99c1f01 36c1f92` 预演：两条线的改动路径仅 `docs/tasks.md` 重叠，并产生文本冲突；产品/测试路径无交集。这只是冲突预览，尚未修改索引、分支或工作区，也不证明整合后运行通过。

## 拆分准备与风险

- 预备计划：`docs/superpowers/plans/2026-11-10-opt-06-responsibility-split.md`；四项分别对应 compatible、extract_task、useMaterials、StudentGraphView，不更改公开行为。
- 当前四文件行数依次为 1074 / 1020 / 843 / 789。关键检查为旧导入兼容、网络 deadline/资源释放、worker 租约和事务、资料 SSE/请求取消、图谱响应式和焦点/布局。
- `codex/extraction-perf` 对 `workers/extract_task.py` 相较 `ad63341` 有 78 行新增 / 57 行删除；本轮仅核对差异统计，不将该分支整合或回退。依赖合入后须重查此重叠。
- 已有 `docs/tasks.md` 的 EXTRACT-PERF-01 未提交追加及两份未跟踪 Claude 交接原样保留。
- 当前工具链：Python 3.11.9、Node v26.4.0、npm 11.17.0；未安装或升级依赖。

## 本轮改动与验证

- 仅新增本交接、预备计划，并在 `docs/tasks.md` 追加认领及阻塞记录。
- GitHub 查询：OPT-03 按任务/head 检索与分支名检索；OPT-05 与底座 PR 实时元数据读取。未执行远端写操作。
- `git status`、提交祖先检查、依赖交接与源代码职责核对已完成。
- 原目录准备阶段 `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` exit 0（25 项门禁负例及 B14/B08/B09/B10/B12/B13 通过）；`git diff --check` exit 0。隔离整合基线完整门禁另记。
- 未运行 OPT-06 后端/前端全量测试、构建和截图对比；尚无产品改动供此类验证。
- 无 API、数据、配置、依赖或架构实现变更；无迁移或破坏性操作。

## 下一步

用户已于本轮明确允许在隔离分支本地整合 `36c1f92` 与 `99c1f01`、验证后实施。按计划顺序执行，四项使用独立本地叠加分支与提交，未来 PR 各自以上一项为 base，保持每个原候选文件独立审查；暂不推送或合并远端 PR。
